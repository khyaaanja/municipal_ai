import re
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponseNotAllowed
from django.utils import timezone
from .models import User, Role, Profile
from core.utils import get_client_ip
from core.analytics import track


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
        user = authenticate(request, username=email, password=password)

        if user:
            cache.delete(attempts_key)
            login(request, user)
            track(request, 'login')
            next_url = _safe_next(request.POST.get('next') or request.GET.get('next', '/'))
            return redirect(next_url)

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
            errors.append('Password must be at least 8 characters with 1 uppercase and 1 digit.')
        if password != confirm:
            errors.append('Passwords do not match.')

        if errors:
            return render(request, 'accounts/register.html', {'errors': errors, 'full_name': full_name, 'email': email})

        if User.objects.filter(email=email).exists():
            # Generic message — never reveal whether email is registered
            return render(request, 'accounts/register.html', {
                'error': 'Registration failed. Please check your details.',
                'full_name': full_name,
            })

        name_parts = full_name.split(' ', 1)
        first_name = name_parts[0]
        last_name  = name_parts[1] if len(name_parts) > 1 else ''

        user = User.objects.create_user(
            email=email,
            password=password,
            username=username,
            first_name=first_name,
            last_name=last_name,
            role='citizen',
        )
        Profile.objects.get_or_create(user=user)

        # Migrate any guest chatbot conversations to the new user
        session_key = request.session.session_key
        if session_key:
            try:
                from chatbot.models import Conversation
                Conversation.objects.filter(
                    session_key=session_key, user__isnull=True
                ).update(user=user)
            except Exception:
                pass

        login(request, user)
        track(request, 'register')
        return redirect('/')

    return render(request, 'accounts/register.html')


def logout_view(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    logout(request)
    return redirect('/')


@login_required
def profile_page(request):
    try:
        from complaints.models import Complaint
        complaint_count = Complaint.objects.filter(user=request.user).count()
    except Exception:
        complaint_count = 0

    if request.method == 'POST':
        request.user.first_name = request.POST.get('first_name', '').strip()
        request.user.last_name  = request.POST.get('last_name', '').strip()
        request.user.save(update_fields=['first_name', 'last_name'])
        messages.success(request, 'Profile updated.')
        return redirect('accounts:profile')

    oauth_providers = []
    try:
        oauth_providers = list(request.user.social_auth.values_list('provider', flat=True))
    except Exception:
        pass

    return render(request, 'accounts/profile.html', {
        'complaint_count': complaint_count,
        'oauth_providers': oauth_providers,
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
