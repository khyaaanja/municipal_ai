import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from complaints.models import Complaint
from complaints.views import _send_status_update_email
from core.decorators import staff_required, official_required
from .models import ComplaintLog


@staff_required
def dashboard_home(request):
    from datetime import timedelta
    week_ago = timezone.now() - timedelta(days=7)

    import json as _json
    total       = Complaint.objects.count()
    pending     = Complaint.objects.filter(status='PENDING').count()
    in_review   = Complaint.objects.filter(status='IN_REVIEW').count()
    in_progress = Complaint.objects.filter(status='IN_PROGRESS').count()
    resolved    = Complaint.objects.filter(status='RESOLVED').count()
    rejected    = Complaint.objects.filter(status='REJECTED').count()
    resolved_wk = Complaint.objects.filter(status='RESOLVED', resolved_at__gte=week_ago).count()
    recent      = Complaint.objects.select_related('user').order_by('-created_at')[:10]

    # Category counts for bar chart
    cat_counts = (
        Complaint.objects
        .values('category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    cat_data = [(row['category'], row['count'], round(row['count'] / total * 100) if total else 0)
                for row in cat_counts]

    return render(request, 'dashboard/home.html', {
        'total': total, 'pending': pending,
        'in_review': in_review, 'in_progress': in_progress,
        'resolved': resolved, 'rejected': rejected,
        'resolved_wk': resolved_wk,
        'recent': recent, 'cat_data': cat_data,
        'status_labels_json': _json.dumps(['Pending', 'In Review', 'In Progress', 'Resolved', 'Rejected']),
        'status_values_json': _json.dumps([pending, in_review, in_progress, resolved, rejected]),
    })


@staff_required
def complaint_list_staff(request):
    qs = Complaint.objects.select_related('user', 'assigned_to').order_by('-created_at')

    status_filter   = request.GET.get('status', '')
    category_filter = request.GET.get('category', '')
    priority_filter = request.GET.get('priority', '')
    search          = request.GET.get('q', '').strip()
    assigned_filter = request.GET.get('assigned', '')

    if status_filter:
        qs = qs.filter(status=status_filter)
    if category_filter:
        qs = qs.filter(category=category_filter)
    if priority_filter:
        qs = qs.filter(priority=priority_filter)
    if search:
        qs = qs.filter(
            Q(complaint_id__icontains=search) |
            Q(title__icontains=search) |
            Q(submitter_name__icontains=search)
        )
    if assigned_filter == 'me':
        qs = qs.filter(assigned_to=request.user)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))

    my_assigned_count = Complaint.objects.filter(assigned_to=request.user).count()

    return render(request, 'dashboard/complaints.html', {
        'page': page,
        'status_filter': status_filter,
        'category_filter': category_filter,
        'priority_filter': priority_filter,
        'search': search,
        'assigned_filter': assigned_filter,
        'my_assigned_count': my_assigned_count,
        'status_choices': Complaint.STATUS_CHOICES,
        'category_choices': Complaint.CATEGORY_CHOICES,
        'priority_choices': Complaint.PRIORITY_CHOICES,
    })


@staff_required
def complaint_detail_staff(request, complaint_id):
    complaint = get_object_or_404(Complaint, complaint_id=complaint_id)
    role = request.user.role

    if request.method == 'POST':
        new_status = request.POST.get('status', complaint.status)
        new_notes  = request.POST.get('admin_notes', complaint.admin_notes or '')
        new_priority = request.POST.get('priority', complaint.priority)

        old_status = complaint.status

        # Role-based field permissions
        if role in ('staff', 'official', 'admin'):
            complaint.admin_notes = new_notes
            if new_status != old_status:
                complaint.status = new_status
                if new_status == 'RESOLVED':
                    complaint.resolved_at = timezone.now()
                ComplaintLog.objects.create(
                    complaint=complaint,
                    changed_by=request.user,
                    old_status=old_status,
                    new_status=new_status,
                    note=new_notes,
                )
                _send_status_update_email(complaint, old_status, new_status)

        if role in ('official', 'admin'):
            complaint.priority = new_priority

        complaint.save()
        return redirect('dashboard:complaint_detail', complaint_id=complaint.complaint_id)

    logs = complaint.logs.select_related('changed_by').order_by('-changed_at')
    return render(request, 'dashboard/complaint_detail.html', {
        'complaint': complaint,
        'logs': logs,
        'role': role,
        'status_choices': Complaint.STATUS_CHOICES,
        'priority_choices': Complaint.PRIORITY_CHOICES,
    })


@official_required
def export_complaints(request):
    qs = Complaint.objects.all().order_by('-created_at')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="complaints_export.csv"'
    w = csv.writer(response)
    w.writerow(['ID', 'Category', 'Title', 'Status', 'Priority', 'Submitter', 'Location', 'Created', 'Updated'])
    for c in qs:
        w.writerow([c.complaint_id, c.category, c.title, c.status, c.priority,
                    c.submitter_name, c.location,
                    c.created_at.strftime('%Y-%m-%d %H:%M'),
                    c.updated_at.strftime('%Y-%m-%d %H:%M')])
    return response
