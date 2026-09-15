import csv
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Count, Q, Avg, F, ExpressionWrapper, DurationField
from django.core.paginator import Paginator
from complaints.models import Complaint, ComplaintEscalation, ComplaintSupport
from accounts.models import User
from core.decorators import mayor_required
from core.models import Announcement, WardProject, WardBudget


WARD_COUNT = 17


@mayor_required
def mayor_dashboard(request):
    complaints = Complaint.objects.all()

    total       = complaints.count()
    pending     = complaints.filter(status='PENDING').count()
    in_review   = complaints.filter(status='IN_REVIEW').count()
    in_progress = complaints.filter(status='IN_PROGRESS').count()
    resolved    = complaints.filter(status='RESOLVED').count()
    rejected    = complaints.filter(status='REJECTED').count()
    unassigned  = complaints.filter(ward_number__isnull=True).count()

    chairpersons = User.objects.filter(role='chairperson').order_by('ward_number')
    chair_by_ward = {c.ward_number: c for c in chairpersons}

    ward_agg = {
        row['ward_number']: row
        for row in complaints.values('ward_number').annotate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='PENDING')),
            resolved=Count('id', filter=Q(status='RESOLVED')),
        )
    }
    ward_stats = [
        {
            'ward': w,
            'total':    ward_agg.get(w, {}).get('total', 0),
            'pending':  ward_agg.get(w, {}).get('pending', 0),
            'resolved': ward_agg.get(w, {}).get('resolved', 0),
            'chairperson': chair_by_ward.get(w),
        }
        for w in range(1, WARD_COUNT + 1)
    ]

    cat_label = dict(Complaint.CATEGORY_CHOICES)
    by_category = [
        {'label': cat_label.get(row['category'], row['category']), 'n': row['n']}
        for row in complaints.values('category').annotate(n=Count('id')).order_by('-n')
    ]

    # Daily trend — last 30 days
    import json as _json
    from datetime import timedelta, date as _date
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
    trend_labels = []
    trend_values = []
    for i in range(30):
        d = thirty_days_ago + timedelta(days=i)
        trend_labels.append(d.strftime('%b %d'))
        trend_values.append(daily_map.get(d, 0))

    recent = complaints.select_related('user').order_by('-created_at')[:10]

    # Citizen escalations — formal escalations submitted by logged-in citizens
    citizen_escalations = (
        ComplaintEscalation.objects
        .filter(is_reviewed=False)
        .select_related('complaint', 'escalated_by')
        .order_by('-escalated_at')[:10]
    )
    escalation_count = ComplaintEscalation.objects.filter(is_reviewed=False).count()

    # High-support complaints — most co-signers first (top 5 needing attention)
    high_support = (
        Complaint.objects
        .exclude(status__in=('RESOLVED', 'REJECTED'))
        .annotate(support_n=Count('supporters'))
        .filter(support_n__gte=1)
        .order_by('-support_n')[:5]
    )

    # Staff performance with citizen satisfaction scores
    from complaints.models import ComplaintRating
    staff_qs = (
        User.objects
        .filter(role__in=('staff', 'official'))
        .annotate(
            assigned_count=Count('assigned_complaints', distinct=True),
            resolved_count=Count(
                'assigned_complaints',
                filter=Q(assigned_complaints__status='RESOLVED'),
                distinct=True,
            ),
        )
        .filter(assigned_count__gt=0)
        .order_by('-resolved_count', '-assigned_count')[:10]
    )
    # Attach satisfaction %: avg rating score from citizens on their resolved complaints
    staff_perf = []
    for s in staff_qs:
        rated = ComplaintRating.objects.filter(
            complaint__assigned_to=s,
            complaint__status='RESOLVED',
        )
        total_ratings = rated.count()
        if total_ratings:
            avg_score = sum(r.score for r in rated) / total_ratings
            satisfaction = round((avg_score / 5) * 100)
            thumbsdown = rated.filter(score=1).count()
        else:
            satisfaction = None
            thumbsdown = 0
        s.satisfaction = satisfaction
        s.thumbsdown   = thumbsdown
        s.rated_count  = total_ratings
        staff_perf.append(s)

    ward_labels = [f'Ward {ws["ward"]}' for ws in ward_stats]
    ward_totals = [ws['total'] for ws in ward_stats]
    ward_resolved = [ws['resolved'] for ws in ward_stats]

    return render(request, 'mayor/dashboard.html', {
        'total': total,
        'pending': pending,
        'in_review': in_review,
        'in_progress': in_progress,
        'resolved': resolved,
        'rejected': rejected,
        'unassigned': unassigned,
        'chairpersons': chairpersons,
        'ward_stats': ward_stats,
        'by_category': by_category,
        'recent': recent,
        'trend_labels_json': _json.dumps(trend_labels),
        'trend_values_json': _json.dumps(trend_values),
        'cat_labels_json':   _json.dumps([r['label'] for r in by_category]),
        'cat_values_json':   _json.dumps([r['n'] for r in by_category]),
        'status_labels_json': _json.dumps(['Pending','In Review','In Progress','Resolved','Rejected']),
        'status_values_json': _json.dumps([pending, in_review, in_progress, resolved, rejected]),
        'ward_labels_json':   _json.dumps(ward_labels),
        'ward_totals_json':   _json.dumps(ward_totals),
        'ward_resolved_json': _json.dumps(ward_resolved),
        'staff_perf': staff_perf,
        'citizen_escalations': citizen_escalations,
        'escalation_count': escalation_count,
        'high_support': high_support,
    })


@mayor_required
def mayor_complaints(request):
    from django.db.models import Count as _Count
    qs = Complaint.objects.select_related('user').annotate(vote_count=_Count('votes', distinct=True))

    q          = request.GET.get('q', '').strip()
    status_f   = request.GET.get('status', '')
    ward_f     = request.GET.get('ward', '')
    category_f = request.GET.get('category', '')
    sort_f     = request.GET.get('sort', '')

    if q:
        qs = qs.filter(
            Q(complaint_id__icontains=q) |
            Q(title__icontains=q) |
            Q(submitter_name__icontains=q) |
            Q(location__icontains=q)
        )
    if status_f:
        qs = qs.filter(status=status_f)
    if ward_f:
        try:
            qs = qs.filter(ward_number=int(ward_f))
        except ValueError:
            pass
    if category_f:
        qs = qs.filter(category=category_f)

    if sort_f == 'votes':
        qs = qs.order_by('-vote_count', '-created_at')
    else:
        qs = qs.order_by('-created_at')

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))
    chairpersons = User.objects.filter(role='chairperson').order_by('ward_number')

    return render(request, 'mayor/complaints.html', {
        'page': page,
        'q': q,
        'status_f': status_f,
        'ward_f': ward_f,
        'category_f': category_f,
        'sort_f': sort_f,
        'status_choices': Complaint.STATUS_CHOICES,
        'category_choices': Complaint.CATEGORY_CHOICES,
        'wards': range(1, WARD_COUNT + 1),
        'chairpersons': chairpersons,
        'total': qs.count(),
    })


@mayor_required
def mayor_complaint_detail(request, complaint_id):
    complaint    = get_object_or_404(Complaint, complaint_id=complaint_id)
    chairpersons = User.objects.filter(role='chairperson').order_by('ward_number')

    staff_users = User.objects.filter(role__in=('staff', 'official')).order_by('first_name', 'last_name')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update':
            old_status            = complaint.status
            complaint.status      = request.POST.get('status', complaint.status)
            complaint.priority    = request.POST.get('priority', complaint.priority)
            complaint.admin_notes = request.POST.get('admin_notes', complaint.admin_notes)
            ward_raw              = request.POST.get('ward_number', '').strip()
            complaint.ward_number = int(ward_raw) if ward_raw else None
            assigned_raw = request.POST.get('assigned_to', '').strip()
            if assigned_raw:
                try:
                    assigned_user = User.objects.get(pk=int(assigned_raw), role__in=('staff', 'official'))
                    if complaint.assigned_to_id != assigned_user.pk:
                        complaint.assigned_to = assigned_user
                        from accounts.models import Notification
                        Notification.objects.create(
                            user=assigned_user,
                            message=f'Complaint {complaint.complaint_id} has been assigned to you: {complaint.title[:60]}',
                            url=f'/dashboard/complaints/{complaint.complaint_id}/',
                        )
                except (User.DoesNotExist, ValueError):
                    pass
            else:
                complaint.assigned_to = None
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
            messages.success(request, 'Complaint updated successfully.')

        elif action == 'escalate':
            ward_raw = request.POST.get('ward_number', '').strip()
            if ward_raw:
                complaint.ward_number = int(ward_raw)
                complaint.status      = 'IN_REVIEW'
                note = f'\n[Mayor forwarded to Ward {ward_raw} on {timezone.now().date()}]'
                complaint.admin_notes = (complaint.admin_notes or '') + note
                complaint.save()
                messages.success(request, f'Complaint forwarded to Ward {ward_raw} chairperson.')

        return redirect('mayor:complaint_detail', complaint_id=complaint.complaint_id)

    return render(request, 'mayor/complaint_detail.html', {
        'complaint':    complaint,
        'chairpersons': chairpersons,
        'staff_users':  staff_users,
        'status_choices':   Complaint.STATUS_CHOICES,
        'priority_choices': Complaint.PRIORITY_CHOICES,
        'wards': range(1, WARD_COUNT + 1),
    })


@mayor_required
def mayor_chairpersons(request):
    chairpersons = User.objects.filter(role='chairperson').order_by('ward_number')
    assigned_wards = set(chairpersons.values_list('ward_number', flat=True))
    chairs_data = []
    for chair in chairpersons:
        wc = Complaint.objects.filter(ward_number=chair.ward_number)
        chairs_data.append({
            'user':     chair,
            'total':    wc.count(),
            'pending':  wc.filter(status='PENDING').count(),
            'resolved': wc.filter(status='RESOLVED').count(),
        })
    unassigned_wards = [w for w in range(1, WARD_COUNT + 1) if w not in assigned_wards]
    return render(request, 'mayor/chairpersons.html', {
        'chairs_data': chairs_data,
        'wards': range(1, WARD_COUNT + 1),
        'unassigned_wards': unassigned_wards,
    })


@mayor_required
def export_complaints_csv(request):
    qs = Complaint.objects.all().order_by('-created_at')
    status_f   = request.GET.get('status', '')
    ward_f     = request.GET.get('ward', '')
    category_f = request.GET.get('category', '')
    if status_f:   qs = qs.filter(status=status_f)
    if ward_f:     qs = qs.filter(ward_number=ward_f)
    if category_f: qs = qs.filter(category=category_f)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="complaints_export.csv"'
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


@mayor_required
def mayor_report(request):
    import json as _json
    from datetime import timedelta, date as _date

    complaints = Complaint.objects.all()
    total       = complaints.count()
    pending     = complaints.filter(status='PENDING').count()
    in_review   = complaints.filter(status='IN_REVIEW').count()
    in_progress = complaints.filter(status='IN_PROGRESS').count()
    resolved    = complaints.filter(status='RESOLVED').count()
    rejected    = complaints.filter(status='REJECTED').count()

    resolution_rate = round(resolved / total * 100) if total else 0

    ward_stats = []
    for ward in range(1, WARD_COUNT + 1):
        wc    = complaints.filter(ward_number=ward)
        chair = User.objects.filter(role='chairperson', ward_number=ward).first()
        wt    = wc.count()
        wr    = wc.filter(status='RESOLVED').count()
        ward_stats.append({
            'ward':        ward,
            'total':       wt,
            'pending':     wc.filter(status='PENDING').count(),
            'resolved':    wr,
            'chairperson': chair,
            'rate':        round(wr / wt * 100) if wt else 0,
        })

    cat_label  = dict(Complaint.CATEGORY_CHOICES)
    by_category = [
        {'label': cat_label.get(row['category'], row['category']), 'n': row['n']}
        for row in complaints.values('category').annotate(n=Count('id')).order_by('-n')
    ]

    staff_perf = (
        User.objects
        .filter(role__in=('staff', 'official'))
        .annotate(
            assigned_count=Count('assigned_complaints', distinct=True),
            resolved_count=Count(
                'assigned_complaints',
                filter=Q(assigned_complaints__status='RESOLVED'),
                distinct=True,
            ),
        )
        .filter(assigned_count__gt=0)
        .order_by('-resolved_count')[:15]
    )

    today = timezone.now().date()
    sla_map = {'CRITICAL': 1, 'HIGH': 3, 'MEDIUM': 7, 'LOW': 14}
    now = timezone.now()
    open_qs = complaints.exclude(status__in=('RESOLVED', 'REJECTED')).only('priority', 'created_at')
    overdue_total = sum(
        1 for c in open_qs
        if now > c.created_at + timezone.timedelta(days=sla_map.get(c.priority, 7))
    )

    return render(request, 'mayor/report.html', {
        'generated_at':    today,
        'total':           total,
        'pending':         pending,
        'in_review':       in_review,
        'in_progress':     in_progress,
        'resolved':        resolved,
        'rejected':        rejected,
        'resolution_rate': resolution_rate,
        'overdue_total':   overdue_total,
        'ward_stats':      ward_stats,
        'by_category':     by_category,
        'staff_perf':      staff_perf,
    })


@mayor_required
def mayor_escalations(request):
    """Critical/overdue complaints + citizen-submitted formal escalations."""
    from django.http import JsonResponse as _JR
    from django.views.decorators.http import require_POST as _rp

    # Handle AJAX escalation acknowledge
    if request.method == 'POST' and request.POST.get('action') == 'ack_escalation':
        esc_id = request.POST.get('escalation_id')
        note   = request.POST.get('note', '').strip()
        try:
            esc = ComplaintEscalation.objects.get(pk=esc_id, is_reviewed=False)
            esc.is_reviewed  = True
            esc.reviewed_at  = timezone.now()
            esc.reviewed_by  = request.user
            esc.mayor_note   = note
            esc.save()
            # Notify citizen
            try:
                from accounts.models import Notification
                Notification.objects.create(
                    user=esc.escalated_by,
                    message=f"Mayor's office reviewed your escalation for {esc.complaint.complaint_id}.",
                    url=f"/complaint/status/{esc.complaint.complaint_id}/",
                )
            except Exception:
                pass
            return _JR({'ok': True})
        except ComplaintEscalation.DoesNotExist:
            return _JR({'error': 'Not found'}, status=404)

    sla_map = {'CRITICAL': 1, 'HIGH': 3, 'MEDIUM': 7, 'LOW': 14}
    now = timezone.now()

    open_qs = Complaint.objects.exclude(status__in=('RESOLVED', 'REJECTED'))

    # CRITICAL priority first, then filter overdue
    critical_ids = list(
        open_qs.filter(priority='CRITICAL').values_list('id', flat=True)
    )
    overdue_ids = []
    for c in open_qs.exclude(priority='CRITICAL').only('id', 'priority', 'created_at'):
        days = sla_map.get(c.priority, 7)
        if now > c.created_at + timezone.timedelta(days=days):
            overdue_ids.append(c.id)

    qs = Complaint.objects.filter(
        id__in=critical_ids + overdue_ids
    ).select_related('user').annotate(support_n=Count('supporters')).order_by('-created_at')

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))

    # Citizen escalations (formal)
    citizen_escalations = (
        ComplaintEscalation.objects
        .filter(is_reviewed=False)
        .select_related('complaint', 'escalated_by')
        .order_by('-escalated_at')
    )

    return render(request, 'mayor/escalations.html', {
        'page': page,
        'total': qs.count(),
        'critical_count': len(critical_ids),
        'overdue_count': len(overdue_ids),
        'status_choices': Complaint.STATUS_CHOICES,
        'citizen_escalations': citizen_escalations,
        'citizen_esc_count': citizen_escalations.count(),
    })


@mayor_required
def mayor_announcements(request):
    """Mayor posts city-wide or ward-scoped announcements."""
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        body  = request.POST.get('body', '').strip()
        ward_raw = request.POST.get('ward_number', '').strip()
        if title and body:
            ward = int(ward_raw) if ward_raw else None
            Announcement.objects.create(
                title=title, body=body,
                ward_number=ward,
                posted_by=request.user,
            )
            messages.success(request, 'Announcement posted successfully.')
        else:
            messages.error(request, 'Title and body are required.')
        return redirect('mayor:announcements')

    announcements = Announcement.objects.select_related('posted_by').order_by('-created_at')[:50]
    return render(request, 'mayor/announcements.html', {
        'announcements': announcements,
        'wards': range(1, WARD_COUNT + 1),
    })


@mayor_required
def mayor_announcement_delete(request, pk):
    ann = get_object_or_404(Announcement, pk=pk)
    if request.method == 'POST':
        ann.delete()
        messages.success(request, 'Announcement deleted.')
    return redirect('mayor:announcements')


@mayor_required
def mayor_briefing(request):
    """AI-generated weekly briefing via Groq."""
    from django.utils import timezone as tz
    from datetime import timedelta

    now = tz.now()
    week_ago = now - timedelta(days=7)
    complaints = Complaint.objects.all()
    new_this_week = complaints.filter(created_at__gte=week_ago).count()
    resolved_this_week = complaints.filter(status='RESOLVED', resolved_at__gte=week_ago).count()
    total_open = complaints.exclude(status__in=('RESOLVED', 'REJECTED')).count()

    sla_map = {'CRITICAL': 1, 'HIGH': 3, 'MEDIUM': 7, 'LOW': 14}
    overdue = sum(
        1 for c in complaints.exclude(status__in=('RESOLVED', 'REJECTED')).only('priority', 'created_at')
        if now > c.created_at + timedelta(days=sla_map.get(c.priority, 7))
    )

    cat_label = dict(Complaint.CATEGORY_CHOICES)
    top_cats = [
        f"{cat_label.get(r['category'], r['category'])} ({r['n']})"
        for r in complaints.filter(created_at__gte=week_ago)
            .values('category').annotate(n=Count('id')).order_by('-n')[:3]
    ]

    briefing_text = ''
    try:
        from chatbot.ai_engine import MunicipalAIEngine
        engine = MunicipalAIEngine()
        prompt = (
            f"You are the AI governance assistant for Bhaktapur Municipality, Nepal.\n"
            f"Generate a concise executive weekly briefing for the Mayor with these stats:\n"
            f"- New complaints this week: {new_this_week}\n"
            f"- Resolved this week: {resolved_this_week}\n"
            f"- Total open complaints: {total_open}\n"
            f"- Overdue complaints (SLA breached): {overdue}\n"
            f"- Top complaint categories this week: {', '.join(top_cats) if top_cats else 'N/A'}\n\n"
            f"Write 3-4 bullet points highlighting key issues, trends, and one strategic recommendation. "
            f"Be specific and use the numbers. Keep it under 200 words. Format as plain bullet points starting with •"
        )
        result = engine.chat(prompt)
        briefing_text = result.get('response', '')
    except Exception as e:
        briefing_text = (
            f"• {new_this_week} new complaints filed this week, {resolved_this_week} resolved.\n"
            f"• {total_open} complaints currently open across all wards.\n"
            f"• {overdue} complaints have breached SLA deadlines and require immediate attention.\n"
            f"• Top categories: {', '.join(top_cats) if top_cats else 'N/A'}."
        )

    return render(request, 'mayor/briefing.html', {
        'briefing_text': briefing_text,
        'new_this_week': new_this_week,
        'resolved_this_week': resolved_this_week,
        'total_open': total_open,
        'overdue': overdue,
        'top_cats': top_cats,
        'generated_at': now,
    })
