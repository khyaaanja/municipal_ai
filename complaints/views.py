from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.cache import cache
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.conf import settings as django_settings
from .models import Complaint
from core.utils import get_client_ip
from core.analytics import track


def _send_complaint_confirmation(complaint):
    if not complaint.submitter_email:
        return
    body = (
        f"Dear {complaint.submitter_name},\n\n"
        f"Your complaint has been received by Bhaktapur Municipality.\n\n"
        f"Reference ID : {complaint.complaint_id}\n"
        f"Category     : {complaint.get_category_display()}\n"
        f"Title        : {complaint.title}\n"
        f"Status       : Pending Review\n\n"
        f"You can track your complaint at:\n"
        f"https://bhaktapur.gov.np/complaint/track/\n\n"
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
        f"Tel: +977-1-6610000"
    )
    send_mail(
        subject=f'[{complaint.complaint_id}] Status Update: {status_labels.get(new_status, new_status)}',
        message=body,
        from_email=django_settings.DEFAULT_FROM_EMAIL,
        recipient_list=[complaint.submitter_email],
        fail_silently=True,
    )


def _ctx(prefill_name='', prefill_email='', **kwargs):
    """Build a consistent submit template context."""
    return {'prefill_name': prefill_name, 'prefill_email': prefill_email, **kwargs}


def submit_complaint(request):
    prefill_name  = ''
    prefill_email = ''
    if request.user.is_authenticated:
        prefill_name  = request.user.get_full_name() or request.user.username
        prefill_email = request.user.email

    if request.method == 'POST':
        ip = get_client_ip(request)
        rate_key = f'complaint_submit_{ip}'
        cache.add(rate_key, 0, 60 * 60)
        attempts = cache.incr(rate_key)

        if attempts > 3:
            return render(request, 'complaints/submit.html', _ctx(
                prefill_name=prefill_name, prefill_email=prefill_email,
                error='Too many submissions. Try again in an hour.',
            ))

        category       = request.POST.get('category', '').strip()
        title          = request.POST.get('title', '').strip()
        description    = request.POST.get('description', '').strip()
        location       = request.POST.get('location', '').strip()
        submitter_name = request.POST.get('name', '').strip()
        phone          = request.POST.get('phone', '').strip()
        email          = request.POST.get('email', '').strip()

        errors = []
        if not category:
            errors.append('Please select a category.')
        if not title:
            errors.append('Title is required.')
        if not description:
            errors.append('Description is required.')
        if not location:
            errors.append('Location is required.')
        if not submitter_name:
            errors.append('Your name is required.')

        if errors:
            return render(request, 'complaints/submit.html', _ctx(
                prefill_name=prefill_name, prefill_email=prefill_email,
                errors=errors, post=request.POST,
            ))

        complaint = Complaint.objects.create(
            category=category,
            title=title,
            description=description,
            location=location,
            submitter_name=submitter_name,
            submitter_phone=phone,
            submitter_email=email,
            user=request.user if request.user.is_authenticated else None,
        )

        track(request, 'complaint_submit', object_type='complaint', object_id=complaint.pk)
        _send_complaint_confirmation(complaint)
        request.session['last_complaint_id'] = complaint.complaint_id
        return redirect('complaints:complaint_success')

    return render(request, 'complaints/submit.html', _ctx(
        prefill_name=prefill_name, prefill_email=prefill_email,
    ))


def complaint_success(request):
    cid = request.session.pop('last_complaint_id', None)
    if not cid:
        return redirect('complaints:complaint_submit')
    return render(request, 'complaints/submit.html', _ctx(success_id=cid))


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


def complaint_status(request, complaint_id):
    complaint = get_object_or_404(Complaint, complaint_id__iexact=complaint_id)

    # admin_notes are the municipality's public response — always show them
    show_notes = complaint.status in ('RESOLVED', 'REJECTED') and bool(complaint.admin_notes)

    # Submitter contact details (PII) only shown to the complaint owner or staff
    is_staff_user = request.user.is_authenticated and request.user.role in ('staff', 'official', 'admin')
    is_owner = request.user.is_authenticated and complaint.user == request.user
    show_sensitive = is_owner or is_staff_user

    return render(request, 'complaints/status.html', {
        'complaint': complaint,
        'show_notes': show_notes,
        'show_sensitive': show_sensitive,
    })


@login_required
def my_complaints(request):
    qs = Complaint.objects.filter(user=request.user).select_related('user')
    paginator = Paginator(qs, 10)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'complaints/my_complaints.html', {'page': page})
