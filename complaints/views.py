import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, FileResponse, Http404
from django.core.cache import cache
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.conf import settings as django_settings
from django.views.decorators.http import require_POST
from .models import (
    Complaint, ComplaintFollow, ComplaintRating, ComplaintUpdate,
    ComplaintSupport, ComplaintEscalation, ComplaintPhoto, ComplaintStatusHistory,
)
from django.utils import timezone as tz
from core.utils import get_client_ip
from core.utils import MAX_AI_IMAGE_BYTES, valid_uploaded_image
from core.analytics import track

logger = logging.getLogger(__name__)


def _send_complaint_confirmation(complaint):
    if not complaint.submitter_email:
        return
    site = getattr(django_settings, 'SITE_URL', 'https://bhaktapur.gov.np')
    claim_section = ''
    if complaint.claim_token:
        claim_section = (
            f"\n--- Own This Complaint ---\n"
            f"Create a free account to track updates automatically, add photos,\n"
            f"and escalate if ignored — no need to remember the ID:\n\n"
            f"  {site}/complaint/claim/{complaint.claim_token}/\n\n"
            f"This link claims the complaint to your account once you register.\n"
        )
    body = (
        f"Dear {complaint.submitter_name},\n\n"
        f"Your complaint has been received by Bhaktapur Municipality.\n\n"
        f"Reference ID : {complaint.complaint_id}\n"
        f"Category     : {complaint.get_category_display()}\n"
        f"Title        : {complaint.title}\n"
        f"Status       : Pending Review\n\n"
        f"Track your complaint at:\n"
        f"{site}/complaint/status/{complaint.complaint_id}/\n"
        f"{claim_section}\n"
        f"We aim to respond within 5 working days.\n\n"
        f"Bhaktapur Municipality\n"
        f"Tel: +977-1-6610000"
    )
    send_mail(
        subject=f'[{complaint.complaint_id}] Complaint Received — Bhaktapur Municipality',
        message=body,
        from_email=django_settings.DEFAULT_FROM_EMAIL,
        recipient_list=[complaint.submitter_email],
        fail_silently=True,
    )


def _send_status_update_email(complaint, old_status, new_status):
    if not complaint.submitter_email:
        return
    status_labels = {
        'PENDING': 'Pending', 'IN_REVIEW': 'Under Review',
        'IN_PROGRESS': 'In Progress', 'RESOLVED': 'Resolved', 'REJECTED': 'Rejected',
    }
    body = (
        f"Dear {complaint.submitter_name},\n\n"
        f"Your complaint status has been updated.\n\n"
        f"Reference ID : {complaint.complaint_id}\n"
        f"Title        : {complaint.title}\n"
        f"Old Status   : {status_labels.get(old_status, old_status)}\n"
        f"New Status   : {status_labels.get(new_status, new_status)}\n"
    )
    if complaint.admin_notes:
        body += f"\nMunicipality Response:\n{complaint.admin_notes}\n"
    body += (
        f"\nTrack your complaint: https://bhaktapur.gov.np/complaint/track/\n\n"
        f"Bhaktapur Municipality\n"
        f"Tel: +977-1-6610000\n\n"
        f"---\n"
        f"You're receiving this because you submitted a complaint to Bhaktapur Municipality.\n"
        f"To opt out of status update emails, reply with 'UNSUBSCRIBE {complaint.complaint_id}'."
    )
    send_mail(
        subject=f'[{complaint.complaint_id}] Status Update: {status_labels.get(new_status, new_status)}',
        message=body,
        from_email=django_settings.DEFAULT_FROM_EMAIL,
        recipient_list=[complaint.submitter_email],
        fail_silently=True,
    )


def _ctx(prefill_name='', prefill_email='', prefill_category='', **kwargs):
    """Build a consistent submit template context."""
    return {
        'prefill_name': prefill_name,
        'prefill_email': prefill_email,
        'prefill_category': prefill_category,
        **kwargs,
    }


def submit_complaint(request):
    prefill_name  = ''
    prefill_email = ''
    if request.user.is_authenticated:
        prefill_name  = request.user.get_full_name() or request.user.username
        prefill_email = request.user.email

    _valid_cats = {c[0] for c in Complaint.CATEGORY_CHOICES}
    prefill_category = request.GET.get('category', '').strip().upper()
    if prefill_category not in _valid_cats:
        prefill_category = ''

    if request.method == 'POST':
        ip = get_client_ip(request)
        rate_key = f'complaint_submit_{ip}'
        cache.add(rate_key, 0, 60 * 60)
        attempts = cache.incr(rate_key)

        if attempts > 3:
            return render(request, 'complaints/submit.html', _ctx(
                prefill_name=prefill_name, prefill_email=prefill_email,
                prefill_category=prefill_category,
                error='Too many submissions. Try again in an hour.',
            ))

        from .services import clean_coord, clean_ward, create_complaint

        if not request.session.session_key:
            request.session.create()

        try:
            complaint = create_complaint(
                category=request.POST.get('category', ''),
                title=request.POST.get('title', ''),
                description=request.POST.get('description', ''),
                location=request.POST.get('location', ''),
                submitter_name=request.POST.get('name', ''),
                phone=request.POST.get('phone', ''),
                email=request.POST.get('email', ''),
                priority=request.POST.get('priority', 'MEDIUM').strip(),
                ward_number=clean_ward(request.POST.get('ward_number', '')),
                latitude=clean_coord(request.POST.get('latitude', '')),
                longitude=clean_coord(request.POST.get('longitude', '')),
                user=request.user,
                session_key=request.session.session_key,
                photos=request.FILES.getlist('photos'),
            )
        except DjangoValidationError as exc:
            return render(request, 'complaints/submit.html', _ctx(
                prefill_name=prefill_name, prefill_email=prefill_email,
                prefill_category=prefill_category,
                errors=exc.messages, post=request.POST,
            ))

        ward_number = complaint.ward_number
        is_anon = complaint.user_id is None

        # Notify ward chairperson of new complaint
        if ward_number:
            try:
                from accounts.models import Notification, User as UserModel
                chair = UserModel.objects.filter(role='chairperson', ward_number=ward_number).first()
                if chair:
                    Notification.objects.create(
                        user=chair,
                        message=f'New complaint {complaint.complaint_id} filed in Ward {ward_number}: {complaint.title[:60]}',
                        url=f'/chairperson/complaints/{complaint.complaint_id}/',
                    )
            except Exception:
                logger.exception("Failed to notify chairperson of new complaint %s", complaint.complaint_id)

        # AI auto-categorization: dispatched as a background Celery task so it
        # never blocks the HTTP response. If Celery is unavailable the task is
        # skipped silently — the complaint is still saved with the user-supplied values.
        if complaint.category == 'OTHER' or complaint.priority == 'MEDIUM':
            try:
                from chatbot.tasks import categorize_complaint_async
                categorize_complaint_async.delay(complaint.pk)
            except Exception:
                logger.warning(
                    "Could not dispatch AI categorization for complaint %s (Celery unavailable)",
                    complaint.complaint_id,
                )

        track(request, 'complaint_submit', object_type='complaint', object_id=complaint.pk)
        try:
            _send_complaint_confirmation(complaint)
        except Exception:
            logger.exception("Failed to send confirmation email for complaint %s", complaint.complaint_id)
        request.session['last_complaint_id'] = complaint.complaint_id
        if is_anon and complaint.claim_token:
            request.session['last_claim_token'] = str(complaint.claim_token)
        return redirect('complaints:complaint_success')

    return render(request, 'complaints/submit.html', _ctx(
        prefill_name=prefill_name, prefill_email=prefill_email,
        prefill_category=prefill_category,
    ))


def complaint_success(request):
    cid = request.session.pop('last_complaint_id', None)
    if not cid:
        return redirect('complaints:complaint_submit')
    claim_token = request.session.pop('last_claim_token', None)
    return render(request, 'complaints/submit.html', _ctx(success_id=cid, claim_token=claim_token))


def track_complaint(request):
    if request.method == 'POST':
        raw = request.POST.get('complaint_id', '').strip()
        try:
            complaint = Complaint.objects.get(complaint_id__iexact=raw)
            return redirect('complaints:complaint_status', complaint_id=complaint.complaint_id)
        except Complaint.DoesNotExist:
            return render(request, 'complaints/track.html', {
                'error': 'No complaint found with that ID.',
                'query': raw,
            })
    return render(request, 'complaints/track.html')


_IMPACT_COEFF = {
    'ROAD':           0.40,
    'WATER':          0.30,
    'ELECTRICITY':    0.25,
    'SANITATION':     0.35,
    'INFRASTRUCTURE': 0.20,
    'NOISE':          0.10,
    'OTHER':          0.10,
}
_WARD_AVG_POP = 5000  # Bhaktapur ~85,000 / 17 wards


def _calc_impact(complaint):
    """Estimated residents benefited by this complaint's resolution."""
    coeff = _IMPACT_COEFF.get(complaint.category, 0.10)
    base  = _WARD_AVG_POP if complaint.ward_number else _WARD_AVG_POP
    return round(base * coeff / 50) * 50  # round to nearest 50


def complaint_status(request, complaint_id):
    complaint = get_object_or_404(Complaint, complaint_id__iexact=complaint_id)

    # Submitter contact details (PII) only shown to the complaint owner or staff
    is_staff_user = request.user.is_authenticated and (
        request.user.is_staff or request.user.role in ('staff', 'official', 'admin')
    )
    is_owner = request.user.is_authenticated and complaint.user == request.user
    show_sensitive = is_owner or is_staff_user
    show_notes = show_sensitive and bool(complaint.admin_notes)

    # Find the chairperson assigned to this ward
    ward_chairperson = None
    if complaint.ward_number:
        try:
            from accounts.models import User
            ward_chairperson = User.objects.filter(
                role='chairperson', ward_number=complaint.ward_number
            ).first()
        except Exception:
            pass

    from .models import ComplaintVote
    history = (
        ComplaintStatusHistory.objects.filter(complaint=complaint).order_by('changed_at')
        if show_sensitive else ComplaintStatusHistory.objects.none()
    )
    vote_count = ComplaintVote.objects.filter(complaint=complaint).count()
    follow_count = complaint.followers.count()

    # Check if current visitor already voted
    session_key = request.session.session_key or ''
    has_voted = ComplaintVote.objects.filter(
        complaint=complaint,
        session_key=session_key,
    ).exists()
    if not has_voted and request.user.is_authenticated:
        has_voted = ComplaintVote.objects.filter(complaint=complaint, user=request.user).exists()

    # Follow / rating / updates for authenticated owner
    is_following = False
    existing_rating = None
    citizen_updates = (
        complaint.updates.select_related('user').all()
        if show_sensitive else ComplaintUpdate.objects.none()
    )
    if request.user.is_authenticated:
        is_following = ComplaintFollow.objects.filter(complaint=complaint, user=request.user).exists()
        if is_owner and complaint.status == 'RESOLVED':
            try:
                existing_rating = complaint.rating
            except Exception:
                pass

    # Community support (logged-in only)
    support_count = complaint.supporters.count()
    is_supporting = (
        request.user.is_authenticated
        and ComplaintSupport.objects.filter(complaint=complaint, user=request.user).exists()
    )
    # Top 3 supporter names (first name only, for social proof)
    supporter_names = list(
        complaint.supporters.select_related('user')
        .order_by('supported_at')[:3]
        .values_list('user__first_name', flat=True)
    )

    # Escalation context
    pending_escalation = None
    can_escalate = False
    escalation_history = []
    if request.user.is_authenticated and (is_owner or is_supporting):
        pending_escalation = complaint.escalations.filter(is_reviewed=False).first()
        escalation_history = list(complaint.escalations.select_related('escalated_by', 'reviewed_by').all()[:5])
        # Can escalate if: complaint is active, SLA breached OR overdue, no unreviewed escalation
        sla_breached = complaint.is_overdue
        already_escalated = pending_escalation is not None
        active = complaint.status not in ('RESOLVED', 'REJECTED')
        can_escalate = active and sla_breached and not already_escalated

    # Resolution intelligence — avg days for same category from historical data
    resolution_intel = None
    if complaint.status not in ('RESOLVED', 'REJECTED'):
        from django.db.models import Avg, F, ExpressionWrapper, DurationField
        cutoff = tz.now() - tz.timedelta(days=180)
        resolved_same_cat = Complaint.objects.filter(
            category=complaint.category,
            status='RESOLVED',
            resolved_at__isnull=False,
            created_at__gte=cutoff,
        ).exclude(pk=complaint.pk)
        count_resolved = resolved_same_cat.count()
        if count_resolved >= 3:
            durations = [
                (c.resolved_at - c.created_at).days
                for c in resolved_same_cat.only('created_at', 'resolved_at')
                if c.resolved_at and c.created_at
            ]
            if durations:
                avg_days = sum(durations) / len(durations)
                days_open = (tz.now() - complaint.created_at).days
                resolution_intel = {
                    'avg_days': round(avg_days),
                    'sample_size': count_resolved,
                    'days_open': days_open,
                    'on_track': days_open <= avg_days,
                    'overdue_by': max(0, days_open - round(avg_days)),
                }

    # Resolution impact (shown when resolved)
    impact_residents = None
    if complaint.status == 'RESOLVED':
        impact_residents = _calc_impact(complaint)

    # Smart action nudge for stuck complaints (logged-in owner only)
    action_nudge = None
    if is_owner and complaint.status not in ('RESOLVED', 'REJECTED'):
        days_open = (tz.now() - complaint.created_at).days
        sla_days  = complaint.SLA_DAYS.get(complaint.priority, 7)
        if days_open >= max(3, sla_days - 1):
            action_nudge = {
                'days_open': days_open,
                'sla_days': sla_days,
                'overdue': days_open > sla_days,
                'support_count': support_count,
                'updates_count': complaint.updates.count(),
                'can_escalate': can_escalate,
            }

    return render(request, 'complaints/status.html', {
        'complaint': complaint,
        'show_notes': show_notes,
        'show_sensitive': show_sensitive,
        'ward_chairperson': ward_chairperson,
        'history': history,
        'vote_count': vote_count,
        'has_voted': has_voted,
        'follow_count': follow_count,
        'is_following': is_following,
        'is_owner': is_owner,
        'existing_rating': existing_rating,
        'citizen_updates': citizen_updates,
        'support_count': support_count,
        'is_supporting': is_supporting,
        'supporter_names': supporter_names,
        'can_escalate': can_escalate,
        'pending_escalation': pending_escalation,
        'escalation_history': escalation_history,
        'resolution_intel': resolution_intel,
        'impact_residents': impact_residents,
        'action_nudge': action_nudge,
    })


@login_required
def my_complaints(request):
    qs = Complaint.objects.filter(user=request.user)

    status_filter   = request.GET.get('status', '').strip().upper()
    category_filter = request.GET.get('category', '').strip().upper()

    if status_filter in ('PENDING', 'IN_REVIEW', 'IN_PROGRESS', 'RESOLVED', 'REJECTED'):
        qs = qs.filter(status=status_filter)
    if category_filter in ('INFRASTRUCTURE', 'SANITATION', 'WATER', 'ELECTRICITY', 'ROAD', 'NOISE', 'OTHER'):
        qs = qs.filter(category=category_filter)

    total   = Complaint.objects.filter(user=request.user).count()
    open_count = Complaint.objects.filter(
        user=request.user, status__in=('PENDING', 'IN_REVIEW', 'IN_PROGRESS')
    ).count()

    paginator = Paginator(qs, 10)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'complaints/my_complaints.html', {
        'page': page,
        'status_filter': status_filter,
        'category_filter': category_filter,
        'category_choices': Complaint.CATEGORY_CHOICES,
        'total': total,
        'open_count': open_count,
    })


def vote_complaint(request, complaint_id):
    from .models import ComplaintVote
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    complaint = get_object_or_404(Complaint, complaint_id=complaint_id)
    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key

    # Prevent duplicate votes
    already = ComplaintVote.objects.filter(complaint=complaint, session_key=session_key).exists()
    if not already and request.user.is_authenticated:
        already = ComplaintVote.objects.filter(complaint=complaint, user=request.user).exists()

    if already:
        return JsonResponse({'voted': False, 'count': ComplaintVote.objects.filter(complaint=complaint).count()})

    ComplaintVote.objects.create(
        complaint=complaint,
        session_key=session_key,
        user=request.user if request.user.is_authenticated else None,
    )
    count = ComplaintVote.objects.filter(complaint=complaint).count()
    return JsonResponse({'voted': True, 'count': count})


@login_required
@require_POST
def follow_complaint(request, complaint_id):
    complaint = get_object_or_404(Complaint, complaint_id=complaint_id)
    obj, created = ComplaintFollow.objects.get_or_create(complaint=complaint, user=request.user)
    if not created:
        obj.delete()
        following = False
    else:
        following = True
    count = complaint.followers.count()
    return JsonResponse({'following': following, 'count': count})


@login_required
def rate_complaint(request, complaint_id):
    complaint = get_object_or_404(Complaint, complaint_id=complaint_id)
    # Only submitter can rate; only resolved complaints
    if complaint.user != request.user or complaint.status != 'RESOLVED':
        return JsonResponse({'error': 'Not allowed'}, status=403)
    if request.method == 'POST':
        score = int(request.POST.get('score', 0))
        comment = request.POST.get('comment', '').strip()
        if score not in (1, 5):
            return JsonResponse({'error': 'Invalid score'}, status=400)
        ComplaintRating.objects.update_or_create(
            complaint=complaint,
            defaults={'user': request.user, 'score': score, 'comment': comment},
        )
        return JsonResponse({'ok': True})
    return JsonResponse({'error': 'POST required'}, status=405)


@login_required
@require_POST
def add_complaint_update(request, complaint_id):
    complaint = get_object_or_404(Complaint, complaint_id=complaint_id)
    if complaint.user != request.user:
        return JsonResponse({'error': 'Not allowed'}, status=403)
    message = request.POST.get('message', '').strip()
    if not message:
        return JsonResponse({'error': 'Message required'}, status=400)
    photo = request.FILES.get('photo')
    if photo and not valid_uploaded_image(photo, MAX_AI_IMAGE_BYTES):
        return JsonResponse({'error': 'Invalid image upload'}, status=400)
    update = ComplaintUpdate.objects.create(
        complaint=complaint,
        user=request.user,
        message=message,
        photo=photo,
    )
    return JsonResponse({
        'ok': True,
        'message': update.message,
        'created_at': update.created_at.strftime('%d %b %Y, %H:%M'),
        'has_photo': bool(update.photo),
    })


def complaint_pdf(request, complaint_id):
    """Printable HTML complaint summary (browser Print → PDF)."""
    complaint = get_object_or_404(Complaint, complaint_id=complaint_id)
    # Public access only if they know the ID; PII stripped for non-owners
    is_owner = request.user.is_authenticated and complaint.user == request.user
    is_staff_user = request.user.is_authenticated and (
        request.user.is_staff or request.user.role in ('staff', 'official', 'admin')
    )
    show_private = is_owner or is_staff_user
    return render(request, 'complaints/complaint_pdf.html', {
        'complaint': complaint,
        'is_owner': is_owner,
        'show_private': show_private,
        'history': complaint.history.all() if show_private else ComplaintStatusHistory.objects.none(),
        'photos': complaint.photos.all() if show_private else ComplaintPhoto.objects.none(),
    })


@login_required
def complaint_photo(request, complaint_id, photo_id):
    """Serve complaint photos only to the complainant or authorized staff."""
    complaint = get_object_or_404(Complaint, complaint_id=complaint_id)
    is_staff_user = request.user.is_staff or request.user.role in ('staff', 'official', 'admin')
    if complaint.user_id != request.user.pk and not is_staff_user:
        raise Http404
    photo = get_object_or_404(ComplaintPhoto, pk=photo_id, complaint=complaint)
    try:
        photo.image.open('rb')
        return FileResponse(photo.image.file, content_type='image/*')
    except (FileNotFoundError, OSError):
        raise Http404


@login_required
def complaint_update_photo(request, complaint_id, update_id):
    """Serve complaint update photos only to the complainant or authorized staff."""
    complaint = get_object_or_404(Complaint, complaint_id=complaint_id)
    is_staff_user = request.user.is_staff or request.user.role in ('staff', 'official', 'admin')
    if complaint.user_id != request.user.pk and not is_staff_user:
        raise Http404
    update = get_object_or_404(ComplaintUpdate, pk=update_id, complaint=complaint)
    if not update.photo:
        raise Http404
    try:
        update.photo.open('rb')
        return FileResponse(update.photo.file, content_type='image/*')
    except (FileNotFoundError, OSError):
        raise Http404


@login_required
@require_POST
def support_complaint(request, complaint_id):
    """Toggle 'I'm Affected Too' — citizen co-signs a complaint they're affected by."""
    complaint = get_object_or_404(Complaint, complaint_id=complaint_id)
    obj, created = ComplaintSupport.objects.get_or_create(complaint=complaint, user=request.user)
    if not created:
        obj.delete()
        supporting = False
    else:
        supporting = True
    count = complaint.supporters.count()
    return JsonResponse({'supporting': supporting, 'count': count})


@login_required
@require_POST
def escalate_complaint(request, complaint_id):
    """Citizen formally escalates a stalled complaint to the Mayor."""
    complaint = get_object_or_404(Complaint, complaint_id=complaint_id)

    # Must be owner or supporter
    is_owner = complaint.user == request.user
    is_supporter = ComplaintSupport.objects.filter(complaint=complaint, user=request.user).exists()
    if not (is_owner or is_supporter):
        return JsonResponse({'error': 'You must be the filer or a co-signer to escalate.'}, status=403)

    # Must be overdue / SLA breached
    if not complaint.is_overdue and complaint.status not in ('PENDING',):
        return JsonResponse({'error': 'Complaint is not yet eligible for escalation.'}, status=400)

    # Must not already have a pending escalation
    if complaint.escalations.filter(is_reviewed=False).exists():
        return JsonResponse({'error': 'An escalation is already pending review by the Mayor.'}, status=400)

    reason = request.POST.get('reason', '').strip()
    note   = request.POST.get('note', '').strip()
    valid_reasons = [r[0] for r in ComplaintEscalation.REASON_CHOICES]
    if reason not in valid_reasons:
        return JsonResponse({'error': 'Please select a reason.'}, status=400)

    ComplaintEscalation.objects.create(
        complaint=complaint,
        escalated_by=request.user,
        reason=reason,
        note=note,
    )

    # Notify all mayor-role users
    try:
        from accounts.models import User as AccountUser
        from accounts.models import Notification
        mayors = AccountUser.objects.filter(role='mayor')
        for mayor in mayors:
            Notification.objects.create(
                user=mayor,
                message=f"Complaint {complaint.complaint_id} escalated by citizen: {complaint.title}",
                url=f"/complaint/status/{complaint.complaint_id}/",
            )
    except Exception:
        pass

    return JsonResponse({'ok': True, 'message': 'Escalation submitted to the Mayor\'s office.'})


@login_required
@require_POST
def acknowledge_escalation(request, escalation_id):
    """Mayor/admin acknowledges and closes an escalation."""
    from accounts.models import User as AccountUser
    if request.user.role not in ('mayor', 'admin'):
        return JsonResponse({'error': 'Not authorised'}, status=403)

    esc = get_object_or_404(ComplaintEscalation, pk=escalation_id)
    mayor_note = request.POST.get('note', '').strip()
    esc.is_reviewed = True
    esc.reviewed_at = tz.now()
    esc.reviewed_by = request.user
    esc.mayor_note  = mayor_note
    esc.save()

    # Notify the citizen who escalated
    try:
        from accounts.models import Notification
        Notification.objects.create(
            user=esc.escalated_by,
            message=f"Mayor's office has reviewed your escalation for {esc.complaint.complaint_id}.",
            url=f"/complaint/status/{esc.complaint.complaint_id}/",
        )
    except Exception:
        pass

    return JsonResponse({'ok': True})


@login_required
@require_POST
def ai_assist_complaint(request):
    """AI writing assistant for complaint submission.
    Analyses draft description and returns targeted improvement suggestions."""
    title       = request.POST.get('title', '').strip()
    description = request.POST.get('description', '').strip()
    category    = request.POST.get('category', '').strip()
    ward_raw    = request.POST.get('ward_number', '').strip()

    if len(description) < 20:
        return JsonResponse({'suggestions': [], 'quality': 'too_short'})

    suggestions = []
    quality = 'ok'

    # --- Rule-based checks (fast, no API cost) ---
    if len(description) < 60:
        suggestions.append({'type': 'warn', 'text': 'Too brief — add specific details: which street/area, how long the problem has existed, how it affects people.'})
        quality = 'weak'

    location_words = ['street', 'road', 'ward', 'near', 'opposite', 'behind', 'chowk', 'tole', 'marg', 'lane', 'sadak']
    if not any(w in description.lower() for w in location_words):
        suggestions.append({'type': 'warn', 'text': 'No location mentioned in description. Name the street, landmark, or area to help officials find the issue.'})
        quality = 'weak'

    # Category mismatch hints
    cat_hints = {
        'water': 'WATER', 'pipe': 'WATER', 'supply': 'WATER', 'tap': 'WATER',
        'electricity': 'ELECTRICITY', 'power': 'ELECTRICITY', 'light': 'ELECTRICITY', 'wire': 'ELECTRICITY',
        'garbage': 'SANITATION', 'waste': 'SANITATION', 'trash': 'SANITATION', 'sewage': 'SANITATION',
        'pothole': 'ROAD', 'traffic': 'ROAD', 'pavement': 'ROAD', 'footpath': 'ROAD',
        'noise': 'NOISE', 'loud': 'NOISE', 'sound': 'NOISE',
        'building': 'INFRASTRUCTURE', 'bridge': 'INFRASTRUCTURE', 'drain': 'INFRASTRUCTURE',
    }
    desc_lower = description.lower()
    suggested_cat = None
    for keyword, cat in cat_hints.items():
        if keyword in desc_lower:
            suggested_cat = cat
            break
    if suggested_cat and suggested_cat != category:
        cat_display = dict(Complaint.CATEGORY_CHOICES).get(suggested_cat, suggested_cat)
        suggestions.append({'type': 'category', 'text': f'This sounds like a "{cat_display}" complaint — check your category selection.', 'category': suggested_cat})

    # Check for similar open complaints in same ward
    if ward_raw:
        try:
            ward_num = int(ward_raw)
            keywords = [w for w in title.split() if len(w) > 3][:4]
            if keywords:
                from django.db.models import Q as _Q
                q = _Q()
                for kw in keywords:
                    q |= _Q(title__icontains=kw) | _Q(description__icontains=kw)
                similar_qs = Complaint.objects.filter(q, ward_number=ward_num).exclude(
                    status__in=('RESOLVED', 'REJECTED')
                ).values('complaint_id', 'title', 'status')[:3]
                similar_list = [
                    {'id': c['complaint_id'], 'title': c['title'][:60], 'status': c['status']}
                    for c in similar_qs
                ]
                if similar_list:
                    suggestions.append({
                        'type': 'duplicate',
                        'text': f'{len(similar_list)} similar open complaint(s) in your ward — consider co-signing instead.',
                        'complaints': similar_list,
                    })
        except (ValueError, TypeError):
            pass

    # --- Groq AI check (only for longer descriptions) ---
    if len(description) >= 60:
        try:
            from chatbot.ai_engine import _get_groq_client
            from django.conf import settings as _s
            api_key = getattr(_s, 'GROQ_API_KEY', '')
            if api_key:
                client = _get_groq_client(api_key)
                model  = getattr(_s, 'GROQ_MODEL', 'llama-3.3-70b-versatile')
                prompt = (
                    "You are a municipal complaint quality checker for Bhaktapur Municipality, Nepal. "
                    "A citizen is submitting a complaint. Give 1-2 SHORT, specific suggestions to improve it. "
                    "Be direct. Each suggestion max 20 words. If it's already good, say 'Good detail — ready to submit.'\n\n"
                    f"Title: {title}\nCategory: {category}\nDescription: {description}\n\n"
                    'Respond ONLY in JSON: {"ai_suggestions": ["suggestion1", "suggestion2"]}'
                )
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{'role': 'user', 'content': prompt}],
                    max_tokens=120,
                    temperature=0.3,
                    timeout=5,
                )
                import json as _json
                ai_text = resp.choices[0].message.content.strip()
                start = ai_text.find('{')
                end   = ai_text.rfind('}') + 1
                if start >= 0 and end > start:
                    data = _json.loads(ai_text[start:end])
                    for s in data.get('ai_suggestions', []):
                        if s and 'good detail' not in s.lower():
                            suggestions.append({'type': 'ai', 'text': s})
        except Exception:
            pass

    if not suggestions:
        suggestions.append({'type': 'ok', 'text': 'Looks good — ready to submit.'})
        quality = 'good'

    return JsonResponse({'suggestions': suggestions, 'quality': quality})


@login_required
def similar_complaints(request):
    """Quick similarity check — used by submission form for duplicate detection."""
    q    = request.GET.get('q', '').strip()
    ward = request.GET.get('ward', '').strip()
    if len(q) < 8:
        return JsonResponse({'results': []})
    keywords = [w for w in q.split() if len(w) > 3][:5]
    if not keywords:
        return JsonResponse({'results': []})
    from django.db.models import Q as _Q, Count as _Count
    qobj = _Q()
    for kw in keywords:
        qobj |= _Q(title__icontains=kw) | _Q(description__icontains=kw)
    qs = Complaint.objects.filter(qobj).exclude(status__in=('RESOLVED', 'REJECTED'))
    if ward:
        try:
            qs = qs.filter(ward_number=int(ward))
        except ValueError:
            pass
    results = list(
        qs.annotate(s_count=_Count('supporters'))
        .values('complaint_id', 'title', 'status', 'category', 's_count')
        .order_by('-s_count')[:5]
    )
    return JsonResponse({'results': results})


@login_required
def rate_service(request, complaint_id):
    """Citizens rate the service quality after their complaint is resolved (1-5 stars)."""
    from .models import ServiceRating
    complaint = get_object_or_404(Complaint, complaint_id=complaint_id)

    # Only the filing citizen may rate; only when resolved
    if complaint.user != request.user or complaint.status != 'RESOLVED':
        return redirect('complaints:complaint_status', complaint_id=complaint_id)

    existing = ServiceRating.objects.filter(complaint=complaint).first()

    if request.method == 'POST':
        if existing:
            return redirect('complaints:complaint_status', complaint_id=complaint_id)
        try:
            rating = int(request.POST.get('rating', 0))
            if not 1 <= rating <= 5:
                raise ValueError
        except (ValueError, TypeError):
            return render(request, 'complaints/rate_service.html', {
                'complaint': complaint,
                'error': 'Please select a rating between 1 and 5.',
            })
        feedback = request.POST.get('feedback', '').strip()[:500]
        ServiceRating.objects.create(
            complaint=complaint,
            user=request.user,
            rating=rating,
            feedback=feedback,
        )
        from accounts.models import Notification
        Notification.objects.create(
            user=request.user,
            message=f'Thank you for rating the service on complaint {complaint_id}.',
            url=f'/complaint/status/{complaint_id}/',
        )
        return redirect('complaints:complaint_status', complaint_id=complaint_id)

    return render(request, 'complaints/rate_service.html', {
        'complaint': complaint,
        'existing':  existing,
    })


def claim_complaint(request, token):
    """Claim an anonymous complaint by UUID token.
    If authenticated: link immediately.
    If not: redirect to register preserving next + claim params.
    """
    complaint = get_object_or_404(Complaint, claim_token=token, user__isnull=True)

    if not request.user.is_authenticated:
        return redirect(
            f"/register/?next=/complaint/status/{complaint.complaint_id}/&claim={token}"
        )

    complaint.user        = request.user
    complaint.claim_token = None
    complaint.session_key = ''
    complaint.save(update_fields=['user', 'claim_token', 'session_key'])

    try:
        from accounts.models import Notification
        Notification.objects.create(
            user=request.user,
            message=f'Complaint {complaint.complaint_id} is now linked to your account.',
            url=f'/complaint/status/{complaint.complaint_id}/',
        )
    except Exception:
        pass

    return redirect('complaints:complaint_status', complaint_id=complaint.complaint_id)
