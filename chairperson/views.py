import csv
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from complaints.models import Complaint
from core.decorators import chairperson_required


@chairperson_required
def chairperson_dashboard(request):
    ward = request.user.ward_number
    if not ward:
        return render(request, 'chairperson/no_ward.html', {})

    complaints = Complaint.objects.filter(ward_number=ward)

    total       = complaints.count()
    pending     = complaints.filter(status='PENDING').count()
    in_review   = complaints.filter(status='IN_REVIEW').count()
    in_progress = complaints.filter(status='IN_PROGRESS').count()
    resolved    = complaints.filter(status='RESOLVED').count()
    rejected    = complaints.filter(status='REJECTED').count()

    cat_label = dict(Complaint.CATEGORY_CHOICES)
    by_category = [
        {'label': cat_label.get(row['category'], row['category']), 'n': row['n']}
        for row in complaints.values('category').annotate(n=Count('id')).order_by('-n')
    ]

    recent = complaints.order_by('-created_at')[:8]

    import json as _json
    from datetime import timedelta
    today = timezone.now().date()
    thirty_days_ago = today - timedelta(days=29)
    daily_raw = (
        complaints
        .filter(created_at__date__gte=thirty_days_ago)
        .values('created_at__date')
        .annotate(n=Count('id'))
        .order_by('created_at__date')
    )
    daily_map = {row['created_at__date']: row['n'] for row in daily_raw}
    trend_labels, trend_values = [], []
    for i in range(30):
        d = thirty_days_ago + timedelta(days=i)
        trend_labels.append(d.strftime('%b %d'))
        trend_values.append(daily_map.get(d, 0))

    return render(request, 'chairperson/dashboard.html', {
        'ward': ward,
        'total': total,
        'pending': pending,
        'in_review': in_review,
        'in_progress': in_progress,
        'resolved': resolved,
        'rejected': rejected,
        'by_category': by_category,
        'recent': recent,
        'trend_labels_json': _json.dumps(trend_labels),
        'trend_values_json': _json.dumps(trend_values),
        'status_labels_json': _json.dumps(['Pending','In Review','In Progress','Resolved','Rejected']),
        'status_values_json': _json.dumps([pending, in_review, in_progress, resolved, rejected]),
    })


@chairperson_required
def chairperson_complaints(request):
    ward = request.user.ward_number
    if not ward:
        return render(request, 'chairperson/no_ward.html', {})

    qs = Complaint.objects.filter(ward_number=ward)

    q          = request.GET.get('q', '').strip()
    status_f   = request.GET.get('status', '')
    category_f = request.GET.get('category', '')

    if q:
        qs = qs.filter(
            Q(complaint_id__icontains=q) |
            Q(title__icontains=q) |
            Q(location__icontains=q)
        )
    if status_f:
        qs = qs.filter(status=status_f)
    if category_f:
        qs = qs.filter(category=category_f)

    paginator = Paginator(qs.order_by('-created_at'), 20)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'chairperson/complaints.html', {
        'page': page,
        'q': q,
        'status_f': status_f,
        'category_f': category_f,
        'status_choices': Complaint.STATUS_CHOICES,
        'category_choices': Complaint.CATEGORY_CHOICES,
        'ward': ward,
        'total': qs.count(),
    })


@chairperson_required
def chairperson_complaint_detail(request, complaint_id):
    ward = request.user.ward_number
    complaint = get_object_or_404(Complaint, complaint_id=complaint_id)

    # Mayor can see all; chairperson only sees their own ward
    if request.user.role == 'chairperson' and complaint.ward_number != ward:
        raise PermissionDenied

    if request.method == 'POST':
        old_status            = complaint.status
        complaint.status      = request.POST.get('status', complaint.status)
        complaint.priority    = request.POST.get('priority', complaint.priority)
        complaint.admin_notes = request.POST.get('admin_notes', complaint.admin_notes)
        if complaint.status == 'RESOLVED' and not complaint.resolved_at:
            complaint.resolved_at = timezone.now()
        complaint._changed_by  = request.user
        complaint._change_note = request.POST.get('change_note', '')
        complaint.save()
        if old_status != complaint.status:
            try:
                from complaints.views import _send_status_update_email
                _send_status_update_email(complaint, old_status, complaint.status)
            except Exception:
                pass
        messages.success(request, 'Complaint updated.')
        return redirect('chairperson:complaint_detail', complaint_id=complaint.complaint_id)

    return render(request, 'chairperson/complaint_detail.html', {
        'complaint': complaint,
        'ward': ward,
        'status_choices': Complaint.STATUS_CHOICES,
        'priority_choices': Complaint.PRIORITY_CHOICES,
    })


@chairperson_required
def chairperson_report(request):
    ward = request.user.ward_number
    if not ward:
        return render(request, 'chairperson/no_ward.html', {})

    complaints = Complaint.objects.filter(ward_number=ward)
    total       = complaints.count()
    pending     = complaints.filter(status='PENDING').count()
    in_review   = complaints.filter(status='IN_REVIEW').count()
    in_progress = complaints.filter(status='IN_PROGRESS').count()
    resolved    = complaints.filter(status='RESOLVED').count()
    rejected    = complaints.filter(status='REJECTED').count()
    resolution_rate = round(resolved / total * 100) if total else 0

    cat_label = dict(Complaint.CATEGORY_CHOICES)
    by_category = [
        {'label': cat_label.get(row['category'], row['category']), 'n': row['n']}
        for row in complaints.values('category').annotate(n=Count('id')).order_by('-n')
    ]

    sla_map = {'CRITICAL': 1, 'HIGH': 3, 'MEDIUM': 7, 'LOW': 14}
    now = timezone.now()
    open_qs = complaints.exclude(status__in=('RESOLVED', 'REJECTED')).only('priority', 'created_at')
    overdue_count = sum(
        1 for c in open_qs
        if now > c.created_at + timezone.timedelta(days=sla_map.get(c.priority, 7))
    )

    recent = complaints.order_by('-created_at')[:20]

    return render(request, 'chairperson/report.html', {
        'ward':            ward,
        'chairperson':     request.user,
        'generated_at':    timezone.now().date(),
        'total':           total,
        'pending':         pending,
        'in_review':       in_review,
        'in_progress':     in_progress,
        'resolved':        resolved,
        'rejected':        rejected,
        'resolution_rate': resolution_rate,
        'overdue_count':   overdue_count,
        'by_category':     by_category,
        'recent':          recent,
    })


@chairperson_required
def export_complaints_csv(request):
    ward = request.user.ward_number
    if not ward:
        return HttpResponse('No ward assigned.', status=403)
    qs = Complaint.objects.filter(ward_number=ward).order_by('-created_at')
    status_f   = request.GET.get('status', '')
    category_f = request.GET.get('category', '')
    if status_f:   qs = qs.filter(status=status_f)
    if category_f: qs = qs.filter(category=category_f)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="ward{ward}_complaints.csv"'
    writer = csv.writer(response)
    writer.writerow(['ID', 'Category', 'Title', 'Status', 'Priority', 'Ward', 'Submitter', 'Filed', 'Resolved'])
    for c in qs[:5000]:
        writer.writerow([
            c.complaint_id, c.category, c.title, c.status, c.priority,
            c.ward_number or '', c.submitter_name,
            c.created_at.strftime('%Y-%m-%d'),
            c.resolved_at.strftime('%Y-%m-%d') if c.resolved_at else '',
        ])
    return response


# ── Announcements ─────────────────────────────────────────────────────────────

from core.models import Announcement, WardProject, WardBudget


@chairperson_required
def chairperson_announcements(request):
    ward = request.user.ward_number
    if not ward:
        return render(request, 'chairperson/no_ward.html', {})

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        body  = request.POST.get('body', '').strip()
        if title and body:
            Announcement.objects.create(
                title=title, body=body,
                ward_number=ward,
                posted_by=request.user,
            )
            messages.success(request, 'Announcement posted for Ward ' + str(ward))
        else:
            messages.error(request, 'Title and body are required.')
        return redirect('chairperson:announcements')

    announcements = Announcement.objects.filter(
        Q(ward_number=ward) | Q(ward_number__isnull=True)
    ).select_related('posted_by').order_by('-created_at')[:50]
    return render(request, 'chairperson/announcements.html', {
        'announcements': announcements,
        'ward': ward,
    })


@chairperson_required
def chairperson_announcement_delete(request, pk):
    ann = get_object_or_404(Announcement, pk=pk, ward_number=request.user.ward_number)
    if request.method == 'POST':
        ann.delete()
        messages.success(request, 'Announcement deleted.')
    return redirect('chairperson:announcements')


# ── Ward Projects ─────────────────────────────────────────────────────────────

@chairperson_required
def chairperson_projects(request):
    ward = request.user.ward_number
    if not ward:
        return render(request, 'chairperson/no_ward.html', {})

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            title       = request.POST.get('title', '').strip()
            description = request.POST.get('description', '').strip()
            status      = request.POST.get('status', 'PLANNED')
            progress    = int(request.POST.get('progress_pct', 0))
            budget_raw  = request.POST.get('budget', '').strip()
            start_raw   = request.POST.get('start_date', '').strip()
            end_raw     = request.POST.get('end_date', '').strip()
            if title:
                from datetime import date as _d
                WardProject.objects.create(
                    ward_number=ward,
                    title=title,
                    description=description,
                    status=status,
                    progress_pct=min(100, max(0, progress)),
                    budget=budget_raw if budget_raw else None,
                    start_date=start_raw if start_raw else None,
                    end_date=end_raw if end_raw else None,
                    created_by=request.user,
                )
                messages.success(request, 'Project added.')
        elif action == 'update':
            pk = request.POST.get('pk')
            project = get_object_or_404(WardProject, pk=pk, ward_number=ward)
            project.status = request.POST.get('status', project.status)
            project.progress_pct = int(request.POST.get('progress_pct', project.progress_pct))
            project.save(update_fields=['status', 'progress_pct', 'updated_at'])
            messages.success(request, 'Project updated.')
        elif action == 'delete':
            pk = request.POST.get('pk')
            WardProject.objects.filter(pk=pk, ward_number=ward).delete()
            messages.success(request, 'Project deleted.')
        return redirect('chairperson:projects')

    projects = WardProject.objects.filter(ward_number=ward)
    return render(request, 'chairperson/projects.html', {
        'projects': projects,
        'ward': ward,
        'status_choices': WardProject.STATUS_CHOICES,
    })


# ── Ward Budget ───────────────────────────────────────────────────────────────

@chairperson_required
def chairperson_budget(request):
    ward = request.user.ward_number
    if not ward:
        return render(request, 'chairperson/no_ward.html', {})

    fiscal_year = request.GET.get('fy', '2081-82')
    budget, _ = WardBudget.objects.get_or_create(
        ward_number=ward, fiscal_year=fiscal_year,
        defaults={'total_allocation': 0, 'spent': 0}
    )

    if request.method == 'POST':
        alloc_raw = request.POST.get('total_allocation', '').strip()
        spent_raw = request.POST.get('spent', '').strip()
        notes     = request.POST.get('notes', '').strip()
        try:
            if alloc_raw:
                budget.total_allocation = float(alloc_raw)
            if spent_raw:
                budget.spent = float(spent_raw)
            budget.notes = notes
            budget.updated_by = request.user
            budget.save()
            messages.success(request, 'Budget updated.')
        except ValueError:
            messages.error(request, 'Invalid numbers.')
        return redirect('chairperson:budget')

    return render(request, 'chairperson/budget.html', {
        'budget': budget,
        'ward': ward,
        'fiscal_year': fiscal_year,
    })
