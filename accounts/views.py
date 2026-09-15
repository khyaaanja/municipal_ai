import logging
import re

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.cache import cache
from django.core.mail import send_mail
from django.conf import settings
from django.http import HttpResponseNotAllowed
from django.utils import timezone
from .models import User, Role, Profile, encrypt_otp_secret, decrypt_otp_secret
from core.utils import get_client_ip
from core.analytics import track

logger = logging.getLogger(__name__)


def _send_verification_email(user, request=None):
    site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
    verify_url = f"{site_url}/accounts/verify-email/{user.email_verification_token}/"
    send_mail(
        subject='Verify your Bhaktapur AI account',
        message=(
            f"Hi {user.first_name or user.username},\n\n"
            f"Please verify your email address by clicking the link below:\n\n"
            f"{verify_url}\n\n"
            f"If you did not register, you can ignore this email.\n\n"
            f"— Bhaktapur Municipal AI"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )


def _safe_next(next_url):
    """Return next_url only if it's a relative same-host URL."""
    if next_url and next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return '/'


def _password_strong(password):
    return (
        len(password) >= 8
        and any(c.isupper() for c in password)
        and any(c.isdigit() for c in password)
        and any(not c.isalnum() for c in password)
    )


def login_page(request):
    if request.user.is_authenticated:
        return redirect('/')

    if request.method == 'POST':
        ip = get_client_ip(request)
        lock_key = f'login_lock_{ip}'
        attempts_key = f'login_attempts_{ip}'

        if cache.get(lock_key):
            return render(request, 'accounts/login.html', {
                'error': 'Too many attempts. Try again in 15 minutes.'
            })

        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        # User model uses USERNAME_FIELD='email', but tests and older templates may
        # still supply username=email local-part. Try email-first auth.
        user = authenticate(request, email=email, password=password)
        if not user:
            username = email.split('@', 1)[0]
            user = authenticate(request, username=username, password=password)

        if user:
            cache.delete(attempts_key)
            # Enforce email verification for citizen accounts
            if not user.is_email_verified and user.role == 'citizen':
                # The message stays plain text and the template renders the
                # link. Markup here is escaped on output — correctly — so the
                # citizen saw the raw <a> tag instead of something clickable.
                return render(request, 'accounts/login.html', {
                    'error': 'Please verify your email before logging in.',
                    'show_resend_verification': True,
                    'next': request.POST.get('next', ''),
                })
            login(request, user)
            track(request, 'login')
            next_url = request.POST.get('next') or request.GET.get('next', '')
            if next_url:
                return redirect(_safe_next(next_url))
            # Role-based post-login redirect
            if user.role == 'mayor':
                return redirect('/mayor/')
            elif user.role == 'chairperson':
                return redirect('/chairperson/')
            elif user.role == 'admin':
                return redirect('/admin/dashboard/')
            elif user.role in ('staff', 'official'):
                return redirect('/dashboard/')
            return redirect('/my/')

        cache.add(attempts_key, 0, 15 * 60)
        attempts = cache.incr(attempts_key)
        if attempts >= 5:
            cache.set(lock_key, True, 15 * 60)

        return render(request, 'accounts/login.html', {
            'error': 'Invalid credentials. Please try again.',
            'next': request.POST.get('next', ''),
        })

    return render(request, 'accounts/login.html', {
        'next': request.GET.get('next', ''),
    })


def register_page(request):
    if request.user.is_authenticated:
        return redirect('/')

    if request.method == 'POST':
        ip = get_client_ip(request)
        reg_key = f'reg_attempts_{ip}'
        cache.add(reg_key, 0, 60 * 60)
        attempts = cache.incr(reg_key)

        if attempts > 5:
            return render(request, 'accounts/register.html', {
                'error': 'Too many registration attempts. Try again in an hour.'
            })

        full_name  = request.POST.get('full_name', '').strip()
        email      = request.POST.get('email', '').strip()
        password   = request.POST.get('password', '')
        confirm    = request.POST.get('confirm_password', '')
        ward_raw   = request.POST.get('ward_number', '').strip()

        # Derive username from email local part
        username_base = re.sub(r'[^a-zA-Z0-9_]', '_', email.split('@')[0])
        username = username_base
        suffix = 1
        while User.objects.filter(username=username).exists():
            username = f'{username_base}_{suffix}'
            suffix += 1

        errors = []
        if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
            errors.append('Please enter a valid email address.')
        if not _password_strong(password):
            errors.append('Password must be at least 8 characters with 1 uppercase, 1 digit, and 1 special character.')
        if password != confirm:
            errors.append('Passwords do not match.')

        if errors:
            return render(request, 'accounts/register.html', {'errors': errors, 'full_name': full_name, 'email': email, 'ward_number': ward_raw, 'wards': range(1, 18)})

        if User.objects.filter(email=email).exists():
            # Generic message — never reveal whether email is registered
            return render(request, 'accounts/register.html', {
                'error': 'Registration failed. Please check your details.',
                'full_name': full_name,
            })

        name_parts = full_name.split(' ', 1)
        first_name = name_parts[0]
        last_name  = name_parts[1] if len(name_parts) > 1 else ''

        ward_number = None
        if ward_raw:
            try:
                w = int(ward_raw)
                if 1 <= w <= 17:
                    ward_number = w
            except ValueError:
                pass

        # Capture session key BEFORE login() rotates it
        pre_login_session_key = request.session.session_key

        user = User.objects.create_user(
            email=email,
            password=password,
            username=username,
            first_name=first_name,
            last_name=last_name,
            role='citizen',
            ward_number=ward_number,
        )
        Profile.objects.get_or_create(user=user)

        # Migrate guest chatbot conversations (existing behaviour)
        if pre_login_session_key:
            try:
                from chatbot.models import Conversation
                Conversation.objects.filter(
                    session_key=pre_login_session_key, user__isnull=True
                ).update(user=user)
            except Exception:
                logger.exception("Failed to migrate guest chatbot conversations on register")

        login(
            request,
            user,
            backend='django.contrib.auth.backends.ModelBackend',
        )
        track(request, 'register')
        _send_verification_email(user)


        claimed_count = 0

        # Layer 1: session migration — same browser, any prior anonymous complaint
        if pre_login_session_key:
            try:
                from complaints.models import Complaint as _C
                claimed_count += _C.objects.filter(
                    session_key=pre_login_session_key, user__isnull=True
                ).update(user=user, claim_token=None, session_key='')
            except Exception:
                logger.exception("Failed to migrate session complaints on register")

        # Layer 2: UUID claim token from ?claim= param (email link, cross-session)
        raw_token = request.GET.get('claim', '') or request.POST.get('claim', '')
        if raw_token:
            try:
                import uuid as _uuid
                from complaints.models import Complaint as _C
                claimed_count += _C.objects.filter(
                    claim_token=_uuid.UUID(raw_token), user__isnull=True
                ).update(user=user, claim_token=None, session_key='')
            except Exception:
                logger.exception("Failed to claim complaint via token on register")

        if claimed_count:
            try:
                from .models import Notification
                Notification.objects.create(
                    user=user,
                    message=f'{claimed_count} complaint(s) you filed are now saved to your account.',
                    url='/complaint/my/',
                )
            except Exception:
                logger.exception("Failed to create complaint-claimed notification")

        explicit_next = _safe_next(request.GET.get('next', '') or request.POST.get('next', ''))
        return redirect(explicit_next if explicit_next and explicit_next != '/' else '/my/?welcome=1')

    return render(request, 'accounts/register.html', {
        'wards': range(1, 18),
        'next':  request.GET.get('next', ''),
        'claim': request.GET.get('claim', ''),
    })


def logout_view(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    logout(request)
    return redirect('/')


def tourist_pass(request):
    """One-click tourist session — no account needed."""
    if request.user.is_authenticated:
        return redirect('/')
    name = (request.POST.get('name', '') or '').strip()
    import time as _time
    request.session['tourist_pass'] = True
    request.session['tourist_name'] = name or 'Traveller'
    request.session['tourist_created'] = _time.time()
    track(request, 'tourist_pass', object_type='session')
    next_url = request.GET.get('next', '') or request.POST.get('next', '')
    from django.http import HttpResponseNotAllowed as _405
    if request.method not in ('GET', 'POST'):
        return _405(['GET', 'POST'])
    dest = next_url if next_url and next_url.startswith('/') else '/attractions/'
    return redirect(dest)


def clear_tourist_pass(request):
    """Exit tourist mode."""
    request.session.pop('tourist_pass', None)
    request.session.pop('tourist_name', None)
    request.session.pop('tourist_created', None)
    return redirect('/login/')


def _civic_score(user):
    """Compute citizen reputation score: 10 pts per complaint, 50 pts per resolved, 2 pts per vote."""
    try:
        from complaints.models import Complaint, ComplaintVote
        filed    = Complaint.objects.filter(user=user).count()
        resolved = Complaint.objects.filter(user=user, status='RESOLVED').count()
        votes    = ComplaintVote.objects.filter(user=user).count()
        return filed * 10 + resolved * 50 + votes * 2
    except Exception:
        logger.exception("Failed to compute civic score for user %s", user.pk)
        return 0


def _civic_badge(score):
    if score >= 500:
        return ('Platinum Civic Champion', '#4A7AB5')
    if score >= 200:
        return ('Gold Civic Leader', '#C9A227')
    if score >= 80:
        return ('Silver Activist', '#888')
    if score >= 20:
        return ('Bronze Citizen', '#CD7F32')
    return ('New Citizen', '#aaa')


@login_required
def profile_page(request):
    try:
        from complaints.models import Complaint
        complaint_count = Complaint.objects.filter(user=request.user).count()
    except Exception:
        logger.exception("Failed to fetch complaint count for profile page")
        complaint_count = 0

    if request.method == 'POST':
        request.user.first_name = request.POST.get('first_name', '').strip()
        request.user.last_name  = request.POST.get('last_name', '').strip()
        ward_raw = request.POST.get('ward_number', '').strip()
        if ward_raw:
            try:
                w = int(ward_raw)
                request.user.ward_number = w if 1 <= w <= 17 else None
            except ValueError:
                request.user.ward_number = None
        else:
            request.user.ward_number = None
        request.user.save(update_fields=['first_name', 'last_name', 'ward_number'])
        messages.success(request, 'Profile updated.')
        return redirect('accounts:profile')

    oauth_providers = []
    try:
        oauth_providers = list(request.user.social_auth.values_list('provider', flat=True))
    except Exception:
        logger.exception("Failed to fetch OAuth providers for profile page")

    score = _civic_score(request.user)
    badge_label, badge_color = _civic_badge(score)

    # Followed complaints
    followed_complaints = []
    voted_complaints = []
    try:
        from complaints.models import ComplaintFollow, ComplaintVote
        followed_complaints = list(
            ComplaintFollow.objects.filter(user=request.user)
            .select_related('complaint')
            .order_by('-created_at')[:10]
        )
        voted_complaints = list(
            ComplaintVote.objects.filter(user=request.user)
            .select_related('complaint')
            .order_by('-created_at')[:10]
        )
    except Exception:
        logger.exception("Failed to fetch followed/voted complaints for profile page")

    return render(request, 'accounts/profile.html', {
        'complaint_count':   complaint_count,
        'oauth_providers':   oauth_providers,
        'civic_score':       score,
        'civic_badge':       badge_label,
        'civic_badge_color': badge_color,
        'followed_complaints': followed_complaints,
        'voted_complaints':    voted_complaints,
        'wards':             range(1, 18),
    })


@login_required
def change_password(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    current  = request.POST.get('current_password', '')
    new_pass = request.POST.get('new_password', '')
    confirm  = request.POST.get('confirm_password', '')

    if not request.user.check_password(current):
        return render(request, 'accounts/profile.html', {
            'pw_error': 'Current password is incorrect.',
        })

    if not _password_strong(new_pass):
        return render(request, 'accounts/profile.html', {
            'pw_error': 'New password must be at least 8 characters with 1 uppercase and 1 digit.',
        })

    if new_pass != confirm:
        return render(request, 'accounts/profile.html', {
            'pw_error': 'Passwords do not match.',
        })

    request.user.set_password(new_pass)
    request.user.save()
    update_session_auth_hash(request, request.user)
    messages.success(request, 'Password changed successfully.')
    return redirect('accounts:profile')


@login_required
def notifications_page(request):
    from .models import Notification
    if request.method == 'POST' and request.POST.get('action') == 'mark_read':
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return redirect('accounts:notifications')
    notifications = Notification.objects.filter(user=request.user)[:50]
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return render(request, 'accounts/notifications.html', {'notifications': notifications})


# ── Two-Factor Authentication (TOTP via pyotp) ────────────────────────────────

_2FA_ROLES = ('staff', 'official', 'admin', 'mayor', 'chairperson')


@login_required
def totp_setup(request):
    import pyotp, urllib.parse
    user = request.user
    if user.role not in _2FA_ROLES:
        messages.error(request, '2FA is only available for staff and governance accounts.')
        return redirect('accounts:profile')

    if request.method == 'POST':
        code = request.POST.get('code', '').strip().replace(' ', '')
        secret = request.session.get('totp_pending_secret', '')
        if not secret:
            return redirect('accounts:totp_setup')
        totp = pyotp.TOTP(secret)
        if totp.verify(code, valid_window=1):
            user.otp_secret  = encrypt_otp_secret(secret)
            user.otp_enabled = True
            user.save(update_fields=['otp_secret', 'otp_enabled'])
            request.session.pop('totp_pending_secret', None)
            request.session['otp_verified'] = True
            messages.success(request, '2FA enabled successfully. Your account is now more secure.')
            return redirect('accounts:profile')
        else:
            messages.error(request, 'Invalid code — please try again.')

    # Decrypt stored secret for display; generate new one for fresh setup
    stored_plaintext = decrypt_otp_secret(user.otp_secret) if user.otp_enabled else ''
    secret = request.session.get('totp_pending_secret') or (
        stored_plaintext if user.otp_enabled else pyotp.random_base32()
    )
    request.session['totp_pending_secret'] = secret

    issuer = 'BhaktapurAI'
    label  = urllib.parse.quote(f'{issuer}:{user.email}')
    otp_url = f'otpauth://totp/{label}?secret={secret}&issuer={urllib.parse.quote(issuer)}'

    return render(request, 'accounts/totp_setup.html', {
        'secret':  secret,
        'otp_url': otp_url,
        'already_enabled': user.otp_enabled,
    })


@login_required
def totp_verify(request):
    import pyotp
    from django.utils.http import url_has_allowed_host_and_scheme
    user = request.user
    if not user.otp_enabled:
        return redirect('accounts:profile')

    if request.method == 'POST':
        code = request.POST.get('code', '').strip().replace(' ', '')
        plaintext_secret = decrypt_otp_secret(user.otp_secret)
        totp = pyotp.TOTP(plaintext_secret)
        if totp.verify(code, valid_window=1):
            request.session['otp_verified'] = True
            next_url = request.POST.get('next') or request.GET.get('next') or '/'
            if not url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                next_url = '/'
            return redirect(next_url)
        else:
            return render(request, 'accounts/totp_verify.html', {
                'error': 'Invalid code. Please try again.',
                'next': request.GET.get('next', '/'),
            })

    return render(request, 'accounts/totp_verify.html', {'next': request.GET.get('next', '/')})


@login_required
def totp_disable(request):
    import pyotp
    user = request.user
    if not user.otp_enabled:
        return redirect('accounts:profile')
    if request.method == 'POST':
        code = request.POST.get('code', '').strip().replace(' ', '')
        plaintext_secret = decrypt_otp_secret(user.otp_secret)
        totp = pyotp.TOTP(plaintext_secret)
        if totp.verify(code, valid_window=1):
            user.otp_enabled = False
            user.otp_secret  = ''
            user.save(update_fields=['otp_enabled', 'otp_secret'])
            request.session.pop('otp_verified', None)
            messages.success(request, '2FA has been disabled for your account.')
            return redirect('accounts:profile')
        messages.error(request, 'Invalid code — 2FA not disabled.')
    return render(request, 'accounts/totp_disable.html', {})


# ── Email Verification ─────────────────────────────────────────────────────────

def verify_email(request, token):
    from django.db import transaction
    try:
        import uuid as _uuid
        user = User.objects.get(email_verification_token=_uuid.UUID(str(token)))
    except (User.DoesNotExist, ValueError):
        return render(request, 'accounts/email_verified.html', {'success': False})

    if not user.is_email_verified:
        user.is_email_verified = True
        user.save(update_fields=['is_email_verified'])

    return render(request, 'accounts/email_verified.html', {'success': True, 'user': user})


@login_required
def resend_verification(request):
    user = request.user
    if user.is_email_verified:
        messages.info(request, 'Your email is already verified.')
        return redirect('accounts:profile')

    rate_key = f'resend_verify_{user.pk}'
    if cache.get(rate_key):
        messages.warning(request, 'Please wait before requesting another verification email.')
        return redirect('accounts:profile')

    _send_verification_email(user)
    cache.set(rate_key, True, 120)
    messages.success(request, f'Verification email sent to {user.email}.')
    return redirect('accounts:profile')
