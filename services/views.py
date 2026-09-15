from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.utils import timezone

from core.decorators import chairperson_required, mayor_required, role_required
from .models import ServiceRequest, ServiceRequestStatusHistory, PublicNotice

SERVICES_CATALOG = {
    'BIRTH_CERT': {
        'label': 'Birth Certificate',
        'days': 3,
        'fee': 'NPR 50',
        'docs': ['Hospital birth letter', "Father's citizenship copy", "Mother's citizenship copy"],
    },
    'DEATH_CERT': {
        'label': 'Death Certificate',
        'days': 3,
        'fee': 'NPR 50',
        'docs': ['Hospital death notice', 'Family ID / citizenship copy'],
    },
    'MARRIAGE_REG': {
        'label': 'Marriage Registration',
        'days': 7,
        'fee': 'NPR 200',
        'docs': ['Citizenship copies of both parties', 'Witness ID', 'Wedding photo'],
    },
    'PROPERTY_TAX': {
        'label': 'Property Tax Clearance',
        'days': 5,
        'fee': 'NPR 100',
        'docs': ['Land ownership certificate (Lalpurja)', 'Previous tax receipts'],
    },
    'BUILDING_PERMIT': {
        'label': 'Building Permit',
        'days': 21,
        'fee': 'NPR 500',
        'docs': ['Site map / blueprint', 'Land ownership certificate', 'Citizenship copy'],
    },
    'WATER_CONN': {
        'label': 'Water Connection',
        'days': 14,
        'fee': 'NPR 1500',
        'docs': ['Property ownership proof', 'Citizenship copy', 'Ward recommendation letter'],
    },
}


# ── Citizen ──────────────────────────────────────────────────────────────────

def service_list(request):
    return render(request, 'services/service_list.html', {
        'catalog': SERVICES_CATALOG.items(),
    })


@login_required
def service_apply(request, service_type):
    if service_type not in SERVICES_CATALOG:
        from django.http import Http404
        raise Http404
    service_info = SERVICES_CATALOG[service_type]

    if request.method == 'POST':
        ward = request.user.ward_number or request.POST.get('ward_number')
        sr = ServiceRequest.objects.create(
            service_type=service_type,
            ward_number=ward or 0,
            applicant=request.user,
            applicant_name=request.POST.get('applicant_name', '').strip(),
            applicant_phone=request.POST.get('applicant_phone', '').strip(),
            applicant_address=request.POST.get('applicant_address', '').strip(),
            details=request.POST.get('details', '').strip(),
            document_1=request.FILES.get('document_1'),
            document_2=request.FILES.get('document_2'),
            document_3=request.FILES.get('document_3'),
        )
        ServiceRequestStatusHistory.objects.create(
            request=sr,
            old_status='',
            new_status='SUBMITTED',
            changed_by=request.user,
            note='Application submitted by citizen.',
        )

        # Notify chairperson
        try:
            from accounts.models import Notification
            from django.contrib.auth import get_user_model
            User = get_user_model()
            chair = User.objects.filter(role='chairperson', ward_number=ward).first()
            if chair:
                Notification.objects.create(
                    user=chair,
                    message=f'New {service_info["label"]} application #{sr.reference_number}',
                    url=f'/services/manage/requests/{sr.reference_number}/',
                )
        except Exception:
            pass

        return redirect('services:request_success', ref=sr.reference_number)

    return render(request, 'services/service_apply.html', {
        'service_type': service_type,
        'service_info': service_info,
    })


@login_required
def my_requests(request):
    requests_qs = ServiceRequest.objects.filter(applicant=request.user).order_by('-created_at')
    return render(request, 'services/my_requests.html', {'service_requests': requests_qs})


@login_required
def request_detail(request, ref):
    sr = get_object_or_404(ServiceRequest, reference_number=ref)
    if sr.applicant != request.user:
        raise PermissionDenied
    history = sr.history.all()
    return render(request, 'services/request_detail.html', {
        'sr': sr,
        'history': history,
        'service_info': SERVICES_CATALOG.get(sr.service_type, {}),
    })


@login_required
def request_success(request, ref):
    sr = get_object_or_404(ServiceRequest, reference_number=ref, applicant=request.user)
    service_info = SERVICES_CATALOG.get(sr.service_type, {})
    return render(request, 'services/request_success.html', {
        'sr': sr,
        'service_info': service_info,
    })


def notice_list(request):
    qs = PublicNotice.objects.filter(is_active=True).order_by('-created_at')
    notice_type = request.GET.get('type')
    if notice_type:
        qs = qs.filter(notice_type=notice_type)
    return render(request, 'services/notice_list.html', {
        'notices': qs,
        'type_filter': notice_type,
        'type_choices': PublicNotice.TYPE_CHOICES,
    })


def notice_detail(request, pk):
    notice = get_object_or_404(PublicNotice, pk=pk)
    return render(request, 'services/notice_detail.html', {'notice': notice})


# ── Chairperson ───────────────────────────────────────────────────────────────

@chairperson_required
def cp_request_list(request):
    ward = request.user.ward_number
    if not ward:
        return render(request, 'chairperson/no_ward.html', {})
    qs = ServiceRequest.objects.filter(ward_number=ward).order_by('-created_at')
    status_filter = request.GET.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)
    return render(request, 'chairperson/service_requests.html', {
        'service_requests': qs,
        'status_filter': status_filter,
        'status_choices': ServiceRequest.STATUS_CHOICES,
        'pending_count': ServiceRequest.objects.filter(ward_number=ward, status='SUBMITTED').count(),
    })


@chairperson_required
def cp_request_detail(request, ref):
    ward = request.user.ward_number
    sr = get_object_or_404(ServiceRequest, reference_number=ref)
    if sr.ward_number != ward:
        raise PermissionDenied

    if request.method == 'POST':
        old_status = sr.status
        new_status = request.POST.get('status', sr.status)
        note = request.POST.get('note', '').strip()
        documents_requested = request.POST.get('documents_requested', '').strip()

        sr.status = new_status
        if documents_requested:
            sr.documents_requested = documents_requested
        if new_status == 'COMPLETED':
            sr.completed_at = timezone.now()
        sr.save()

        ServiceRequestStatusHistory.objects.create(
            request=sr,
            old_status=old_status,
            new_status=new_status,
            changed_by=request.user,
            note=note,
        )

        try:
            from accounts.models import Notification
            Notification.objects.create(
                user=sr.applicant,
                message=f'Your {sr.get_service_type_display()} application #{sr.reference_number} is now {sr.get_status_display()}.',
                url=f'/services/my/{sr.reference_number}/',
            )
        except Exception:
            pass

        messages.success(request, 'Application updated.')
        return redirect('services:cp_request_detail', ref=ref)

    history = sr.history.all()
    service_info = SERVICES_CATALOG.get(sr.service_type, {})
    return render(request, 'chairperson/service_request_detail.html', {
        'sr': sr,
        'history': history,
        'service_info': service_info,
        'status_choices': ServiceRequest.STATUS_CHOICES,
    })


# ── Mayor ─────────────────────────────────────────────────────────────────────

@mayor_required
def mayor_request_list(request):
    qs = ServiceRequest.objects.select_related('applicant').order_by('-created_at')
    status_filter = request.GET.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)
    return render(request, 'mayor/service_requests.html', {
        'service_requests': qs[:100],
        'status_filter': status_filter,
        'status_choices': ServiceRequest.STATUS_CHOICES,
    })


@role_required('chairperson', 'mayor', 'admin')
def mayor_notice_list(request):
    qs = PublicNotice.objects.order_by('-created_at')
    return render(request, 'mayor/notices.html', {'notices': qs})


@role_required('chairperson', 'mayor', 'admin')
def mayor_notice_create(request):
    if request.method == 'POST':
        ward = None
        if request.user.role == 'chairperson':
            ward = request.user.ward_number
        else:
            w = request.POST.get('ward_number')
            ward = int(w) if w else None

        PublicNotice.objects.create(
            ward_number=ward,
            notice_type=request.POST.get('notice_type', 'NOTICE'),
            title=request.POST.get('title', '').strip(),
            body=request.POST.get('body', '').strip(),
            reference_no=request.POST.get('reference_no', '').strip(),
            deadline=request.POST.get('deadline') or None,
            attachment=request.FILES.get('attachment'),
            published_by=request.user,
        )
        messages.success(request, 'Notice published.')
        return redirect('services:mayor_notice_list')

    return render(request, 'mayor/notice_form.html', {
        'type_choices': PublicNotice.TYPE_CHOICES,
    })


@role_required('chairperson', 'mayor', 'admin')
def mayor_notice_edit(request, pk):
    notice = get_object_or_404(PublicNotice, pk=pk)
    if request.user.role == 'chairperson' and notice.ward_number != request.user.ward_number:
        raise PermissionDenied

    if request.method == 'POST':
        notice.notice_type = request.POST.get('notice_type', notice.notice_type)
        notice.title = request.POST.get('title', notice.title).strip()
        notice.body = request.POST.get('body', notice.body).strip()
        notice.reference_no = request.POST.get('reference_no', notice.reference_no).strip()
        notice.deadline = request.POST.get('deadline') or None
        if request.FILES.get('attachment'):
            notice.attachment = request.FILES['attachment']
        notice.save()
        messages.success(request, 'Notice updated.')
        return redirect('services:mayor_notice_list')

    return render(request, 'mayor/notice_form.html', {
        'notice': notice,
        'type_choices': PublicNotice.TYPE_CHOICES,
    })


@role_required('chairperson', 'mayor', 'admin')
@require_POST
def mayor_notice_delete(request, pk):
    notice = get_object_or_404(PublicNotice, pk=pk)
    if request.user.role == 'chairperson' and notice.ward_number != request.user.ward_number:
        raise PermissionDenied
    notice.delete()
    messages.success(request, 'Notice deleted.')
    return redirect('services:mayor_notice_list')
