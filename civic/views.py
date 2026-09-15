import logging

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponseForbidden
from django.core.exceptions import PermissionDenied
from django.db.models import F, Q
from django.utils import timezone
from django.contrib import messages

from core.decorators import chairperson_required, mayor_required
from .models import (Proposal, ProposalSupport, WardMeeting, MeetingRSVP,
                     MeetingQuestion, CivicPoll, PollOption, PollVote,
                     Petition, PetitionSignature)

logger = logging.getLogger(__name__)


# ── Citizen: Proposals ──────────────────────────────────────────────────────

def proposal_list(request):
    qs = Proposal.objects.select_related('submitted_by').order_by('-created_at')
    ward = request.GET.get('ward')
    status = request.GET.get('status')
    category = request.GET.get('category')
    if ward:
        qs = qs.filter(ward_number=ward)
    if status:
        qs = qs.filter(status=status)
    if category:
        qs = qs.filter(category=category)

    supported_ids = set()
    if request.user.is_authenticated:
        supported_ids = set(
            ProposalSupport.objects.filter(user=request.user).values_list('proposal_id', flat=True)
        )

    return render(request, 'civic/proposal_list.html', {
        'proposals': qs[:50],
        'supported_ids': supported_ids,
        'ward_filter': ward,
        'status_filter': status,
        'category_filter': category,
        'status_choices': Proposal.STATUS_CHOICES,
        'category_choices': Proposal.CATEGORY_CHOICES,
    })


def proposal_detail(request, pk):
    proposal = get_object_or_404(Proposal.objects.select_related('submitted_by', 'reviewed_by'), pk=pk)
    user_supported = (
        request.user.is_authenticated and
        ProposalSupport.objects.filter(proposal=proposal, user=request.user).exists()
    )
    return render(request, 'civic/proposal_detail.html', {
        'proposal': proposal,
        'user_supported': user_supported,
    })


@login_required
def proposal_submit(request):
    if request.method == 'POST':
        ward = request.user.ward_number
        if not ward:
            messages.error(request, 'Your account does not have a ward assigned.')
            return redirect('civic:proposal_list')

        proposal = Proposal.objects.create(
            ward_number=ward,
            submitted_by=request.user,
            category=request.POST.get('category', 'OTHER'),
            title=request.POST.get('title', '').strip(),
            description=request.POST.get('description', '').strip(),
            expected_benefit=request.POST.get('expected_benefit', '').strip(),
            estimated_cost=request.POST.get('estimated_cost') or None,
        )

        # Notify ward chairperson
        try:
            from accounts.models import Notification
            from django.contrib.auth import get_user_model
            User = get_user_model()
            chair = User.objects.filter(role='chairperson', ward_number=ward).first()
            if chair:
                Notification.objects.create(
                    user=chair,
                    message=f'New proposal submitted: "{proposal.title}" by {request.user.get_full_name() or request.user.username}',
                    url=f'/civic/manage/proposals/{proposal.pk}/',
                )
        except Exception:
            logger.exception("Failed to notify chairperson of new proposal")

        messages.success(request, 'Your proposal has been submitted successfully.')
        return redirect('civic:proposal_detail', pk=proposal.pk)

    return render(request, 'civic/proposal_submit.html', {
        'category_choices': Proposal.CATEGORY_CHOICES,
    })


@login_required
@require_POST
def proposal_support(request, pk):
    proposal = get_object_or_404(Proposal, pk=pk)
    obj, created = ProposalSupport.objects.get_or_create(proposal=proposal, user=request.user)
    if created:
        Proposal.objects.filter(pk=pk).update(support_count=F('support_count') + 1)
        proposal.refresh_from_db()
        return JsonResponse({'supported': True, 'count': proposal.support_count})
    return JsonResponse({'supported': False, 'count': proposal.support_count})


# ── Citizen: Meetings ────────────────────────────────────────────────────────

def meeting_list(request):
    now = timezone.now()
    upcoming = WardMeeting.objects.filter(
        status='SCHEDULED', meeting_date__gte=now
    ).order_by('meeting_date')
    past = WardMeeting.objects.filter(
        Q(status='COMPLETED') | Q(meeting_date__lt=now)
    ).order_by('-meeting_date')[:10]

    rsvp_ids = set()
    if request.user.is_authenticated:
        rsvp_ids = set(
            MeetingRSVP.objects.filter(user=request.user).values_list('meeting_id', flat=True)
        )

    ward = request.GET.get('ward')
    if ward:
        upcoming = upcoming.filter(ward_number=ward)

    return render(request, 'civic/meeting_list.html', {
        'upcoming': upcoming,
        'past': past,
        'rsvp_ids': rsvp_ids,
        'ward_filter': ward,
    })


def meeting_detail(request, pk):
    meeting = get_object_or_404(WardMeeting, pk=pk)
    rsvp_count = meeting.rsvps.count()
    user_rsvped = (
        request.user.is_authenticated and
        MeetingRSVP.objects.filter(meeting=meeting, user=request.user).exists()
    )
    user_asked = (
        request.user.is_authenticated and
        MeetingQuestion.objects.filter(meeting=meeting, asked_by=request.user).exists()
    )
    questions = meeting.questions.select_related('asked_by').order_by('-created_at')
    return render(request, 'civic/meeting_detail.html', {
        'meeting': meeting,
        'rsvp_count': rsvp_count,
        'user_rsvped': user_rsvped,
        'user_asked': user_asked,
        'questions': questions,
    })


@login_required
@require_POST
def meeting_rsvp(request, pk):
    meeting = get_object_or_404(WardMeeting, pk=pk, status='SCHEDULED')
    rsvp_count = meeting.rsvps.count()
    if meeting.max_rsvp and rsvp_count >= meeting.max_rsvp:
        return JsonResponse({'error': 'Meeting is full', 'full': True}, status=400)
    obj, created = MeetingRSVP.objects.get_or_create(meeting=meeting, user=request.user)
    return JsonResponse({'rsvped': created, 'count': meeting.rsvps.count()})


@login_required
@require_POST
def meeting_question(request, pk):
    meeting = get_object_or_404(WardMeeting, pk=pk, status='SCHEDULED')
    if MeetingQuestion.objects.filter(meeting=meeting, asked_by=request.user).exists():
        return JsonResponse({'error': 'You have already submitted a question.'}, status=400)

    text = request.POST.get('question', '').strip()
    if not text:
        return JsonResponse({'error': 'Question cannot be empty.'}, status=400)

    MeetingQuestion.objects.create(meeting=meeting, asked_by=request.user, question=text)

    try:
        from accounts.models import Notification
        from django.contrib.auth import get_user_model
        User = get_user_model()
        chair = User.objects.filter(role='chairperson', ward_number=meeting.ward_number).first()
        if chair:
            Notification.objects.create(
                user=chair,
                message=f'New question for meeting "{meeting.title}" from {request.user.get_full_name() or request.user.username}',
                url=f'/civic/manage/meetings/{meeting.pk}/',
            )
    except Exception:
        logger.exception("Failed to notify chairperson of new meeting question")

    return JsonResponse({'success': True})


# ── Citizen: Polls ───────────────────────────────────────────────────────────

def poll_list(request):
    active = CivicPoll.objects.filter(status='ACTIVE').order_by('-created_at')
    closed = CivicPoll.objects.filter(status='CLOSED').order_by('-created_at')[:10]
    voted_ids = set()
    if request.user.is_authenticated:
        voted_ids = set(
            PollVote.objects.filter(user=request.user).values_list('poll_id', flat=True)
        )
    return render(request, 'civic/poll_list.html', {
        'active_polls': active,
        'closed_polls': closed,
        'voted_ids': voted_ids,
    })


def poll_detail(request, pk):
    poll = get_object_or_404(CivicPoll, pk=pk)
    options = poll.options.all()
    total_votes = sum(o.vote_count for o in options)
    user_voted = (
        request.user.is_authenticated and
        PollVote.objects.filter(poll=poll, user=request.user).exists()
    )
    options_with_pct = []
    for opt in options:
        pct = int(opt.vote_count * 100 / total_votes) if total_votes else 0
        options_with_pct.append({'option': opt, 'pct': pct})

    return render(request, 'civic/poll_detail.html', {
        'poll': poll,
        'options_with_pct': options_with_pct,
        'total_votes': total_votes,
        'user_voted': user_voted,
    })


@login_required
@require_POST
def poll_vote(request, pk):
    poll = get_object_or_404(CivicPoll, pk=pk, status='ACTIVE')
    if PollVote.objects.filter(poll=poll, user=request.user).exists():
        return JsonResponse({'error': 'Already voted'}, status=400)

    option_id = request.POST.get('option_id')
    option = get_object_or_404(PollOption, pk=option_id, poll=poll)

    PollVote.objects.create(poll=poll, option=option, user=request.user)
    PollOption.objects.filter(pk=option_id).update(vote_count=F('vote_count') + 1)

    options = poll.options.all()
    total = sum(o.vote_count for o in options)
    results = [{'id': o.pk, 'text': o.text,
                'count': o.vote_count,
                'pct': int(o.vote_count * 100 / total) if total else 0}
               for o in options]
    return JsonResponse({'success': True, 'results': results, 'total': total})


# ── Citizen: Petitions ───────────────────────────────────────────────────────

def petition_list(request):
    qs = Petition.objects.order_by('-signature_count')
    ward = request.GET.get('ward')
    status = request.GET.get('status')
    if ward:
        qs = qs.filter(ward_number=ward)
    if status:
        qs = qs.filter(status=status)

    signed_ids = set()
    if request.user.is_authenticated:
        signed_ids = set(
            PetitionSignature.objects.filter(user=request.user).values_list('petition_id', flat=True)
        )

    return render(request, 'civic/petition_list.html', {
        'petitions': qs[:50],
        'signed_ids': signed_ids,
        'ward_filter': ward,
        'status_filter': status,
        'status_choices': Petition.STATUS_CHOICES,
    })


def petition_detail(request, pk):
    petition = get_object_or_404(Petition.objects.select_related('created_by'), pk=pk)
    recent_sigs = petition.signatures.select_related('user').order_by('-signed_at')[:10]
    user_signed = (
        request.user.is_authenticated and
        PetitionSignature.objects.filter(petition=petition, user=request.user).exists()
    )
    return render(request, 'civic/petition_detail.html', {
        'petition': petition,
        'recent_sigs': recent_sigs,
        'user_signed': user_signed,
    })


@login_required
def petition_submit(request):
    if request.method == 'POST':
        goal = request.POST.get('goal_signatures', '100')
        try:
            goal = int(goal)
            if not (10 <= goal <= 10000):
                raise ValueError
        except ValueError:
            messages.error(request, 'Goal must be between 10 and 10,000 signatures.')
            return render(request, 'civic/petition_submit.html')

        ward = request.POST.get('ward_number') or None
        petition = Petition.objects.create(
            ward_number=ward,
            created_by=request.user,
            title=request.POST.get('title', '').strip(),
            body=request.POST.get('body', '').strip(),
            target=request.POST.get('target', '').strip(),
            goal_signatures=goal,
        )

        try:
            from accounts.models import Notification
            from django.contrib.auth import get_user_model
            User = get_user_model()
            if ward:
                chair = User.objects.filter(role='chairperson', ward_number=ward).first()
                if chair:
                    Notification.objects.create(
                        user=chair,
                        message=f'New petition: "{petition.title}" targeting {petition.target}',
                        url=f'/civic/petitions/{petition.pk}/',
                    )
        except Exception:
            logger.exception("Failed to notify chairperson of new petition")

        messages.success(request, 'Petition created successfully.')
        return redirect('civic:petition_detail', pk=petition.pk)

    return render(request, 'civic/petition_submit.html')


@login_required
@require_POST
def petition_sign(request, pk):
    petition = get_object_or_404(Petition, pk=pk)
    if petition.status != 'OPEN':
        return JsonResponse({'error': 'This petition is closed.'}, status=400)

    comment = request.POST.get('comment', '').strip()[:300]
    obj, created = PetitionSignature.objects.get_or_create(
        petition=petition, user=request.user,
        defaults={'comment': comment}
    )
    if created:
        Petition.objects.filter(pk=pk).update(signature_count=F('signature_count') + 1)
        petition.refresh_from_db()
        return JsonResponse({'signed': True, 'count': petition.signature_count})
    return JsonResponse({'signed': False, 'count': petition.signature_count})


# ── Chairperson: Proposals ───────────────────────────────────────────────────

@chairperson_required
def cp_proposal_list(request):
    ward = request.user.ward_number
    if not ward:
        return render(request, 'chairperson/no_ward.html', {})
    qs = Proposal.objects.filter(ward_number=ward).select_related('submitted_by').order_by('-created_at')
    status = request.GET.get('status')
    if status:
        qs = qs.filter(status=status)
    return render(request, 'chairperson/proposals.html', {
        'proposals': qs,
        'status_filter': status,
        'status_choices': Proposal.STATUS_CHOICES,
        'pending_count': qs.filter(status='PENDING').count(),
    })


@chairperson_required
def cp_proposal_detail(request, pk):
    ward = request.user.ward_number
    proposal = get_object_or_404(Proposal, pk=pk)
    if proposal.ward_number != ward:
        raise PermissionDenied

    if request.method == 'POST':
        new_status = request.POST.get('status')
        note = request.POST.get('chairperson_note', '').strip()
        proposal.status = new_status
        proposal.chairperson_note = note
        proposal.reviewed_by = request.user
        proposal.reviewed_at = timezone.now()
        proposal.save()

        try:
            from accounts.models import Notification
            Notification.objects.create(
                user=proposal.submitted_by,
                message=f'Your proposal "{proposal.title}" has been updated to {proposal.get_status_display()}.',
                url=f'/civic/proposals/{proposal.pk}/',
            )
        except Exception:
            logger.exception("Failed to notify user of proposal status update")

        messages.success(request, 'Proposal updated.')
        return redirect('civic:cp_proposal_detail', pk=pk)

    return render(request, 'chairperson/proposal_detail.html', {
        'proposal': proposal,
        'status_choices': Proposal.STATUS_CHOICES,
    })


# ── Chairperson: Meetings ────────────────────────────────────────────────────

@chairperson_required
def cp_meeting_list(request):
    ward = request.user.ward_number
    if not ward:
        return render(request, 'chairperson/no_ward.html', {})
    meetings = WardMeeting.objects.filter(ward_number=ward).order_by('-meeting_date')
    return render(request, 'chairperson/meetings.html', {'meetings': meetings})


@chairperson_required
def cp_meeting_create(request):
    ward = request.user.ward_number
    if not ward:
        return render(request, 'chairperson/no_ward.html', {})

    if request.method == 'POST':
        from core.models import Announcement
        meeting = WardMeeting.objects.create(
            ward_number=ward,
            title=request.POST.get('title', '').strip(),
            description=request.POST.get('description', '').strip(),
            venue=request.POST.get('venue', '').strip(),
            meeting_date=request.POST.get('meeting_date'),
            agenda=request.POST.get('agenda', '').strip(),
            max_rsvp=request.POST.get('max_rsvp') or None,
            created_by=request.user,
        )
        # Surface in existing announcement feed
        try:
            Announcement.objects.create(
                ward_number=ward,
                title=f'Ward Meeting: {meeting.title}',
                body=f'Meeting scheduled at {meeting.venue} on {meeting.meeting_date.strftime("%b %d, %Y %H:%M")}.',
                posted_by=request.user,
            )
        except Exception:
            logger.exception("Failed to create announcement for new ward meeting")

        messages.success(request, 'Meeting created.')
        return redirect('civic:cp_meeting_detail', pk=meeting.pk)

    return render(request, 'chairperson/meeting_form.html', {})


@chairperson_required
def cp_meeting_detail(request, pk):
    ward = request.user.ward_number
    meeting = get_object_or_404(WardMeeting, pk=pk)
    if meeting.ward_number != ward:
        raise PermissionDenied

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'status':
            meeting.status = request.POST.get('status', meeting.status)
            meeting.minutes = request.POST.get('minutes', meeting.minutes)
            meeting.save()
            messages.success(request, 'Meeting updated.')
        elif action == 'reply':
            q_id = request.POST.get('question_id')
            reply = request.POST.get('reply', '').strip()
            MeetingQuestion.objects.filter(pk=q_id, meeting=meeting).update(
                chairperson_reply=reply,
                status='ADDRESSED',
            )
            messages.success(request, 'Reply saved.')
        return redirect('civic:cp_meeting_detail', pk=pk)

    questions = meeting.questions.select_related('asked_by').order_by('created_at')
    return render(request, 'chairperson/meeting_detail.html', {
        'meeting': meeting,
        'rsvp_count': meeting.rsvps.count(),
        'questions': questions,
        'status_choices': WardMeeting.STATUS_CHOICES,
    })


# ── Mayor: Polls ─────────────────────────────────────────────────────────────

@mayor_required
def mayor_poll_list(request):
    polls = CivicPoll.objects.order_by('-created_at')
    return render(request, 'mayor/polls.html', {'polls': polls})


@mayor_required
def mayor_poll_create(request):
    if request.method == 'POST':
        options_text = request.POST.getlist('options')
        options_text = [o.strip() for o in options_text if o.strip()]
        if len(options_text) < 2:
            messages.error(request, 'Please provide at least 2 options.')
            return render(request, 'mayor/poll_form.html')

        poll = CivicPoll.objects.create(
            ward_number=request.POST.get('ward_number') or None,
            question=request.POST.get('question', '').strip(),
            description=request.POST.get('description', '').strip(),
            closes_at=request.POST.get('closes_at') or None,
            created_by=request.user,
            status='ACTIVE',
        )
        for i, text in enumerate(options_text):
            PollOption.objects.create(poll=poll, text=text, order=i)

        messages.success(request, 'Poll created and activated.')
        return redirect('civic:mayor_poll_list')

    return render(request, 'mayor/poll_form.html')


@mayor_required
@require_POST
def mayor_poll_close(request, pk):
    poll = get_object_or_404(CivicPoll, pk=pk)
    poll.status = 'CLOSED'
    poll.save()
    messages.success(request, f'Poll "{poll.question}" has been closed.')
    return redirect('civic:mayor_poll_list')
