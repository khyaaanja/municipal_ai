"""Phase 6 read-only tools.

Public tools serve the same corpus to everyone and may be cached. The
get_my_* tools filter on the authenticated user at the queryset level, so
another citizen's record is never retrieved rather than retrieved and
then discarded.
"""
import re
from hmac import compare_digest

from .base import (
    AUTH_NONE, AUTH_OPTIONAL, AUTH_REQUIRED,
    ToolInputError, tool,
)

COMPLAINT_REF = re.compile(r'^BK-[A-Z0-9]{6}$')
NOT_FOUND = 'No complaint exists with that reference.'
MAX_ROWS = 10


def _limit(value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return MAX_ROWS
    return max(1, min(n, MAX_ROWS))


def _clean(text, max_len):
    if not isinstance(text, str):
        raise ToolInputError('That input was not valid text.')
    text = ''.join(c for c in text if c.isprintable()).strip()
    if not text:
        raise ToolInputError('That looks empty — what would you like to know?')
    return text[:max_len]


def _owns(request, complaint, claim_token=''):
    """Ownership for a complaint, including the two anonymous routes.

    A complaint filed without an account is reachable by the session that
    filed it, or by the claim token printed on the confirmation. The token
    is a bearer credential, so it is compared in constant time.
    """
    user = request.user
    if user.is_authenticated:
        return complaint.user_id == user.pk

    session = getattr(request, 'session', None)
    session_key = getattr(session, 'session_key', '') or ''
    if session_key and complaint.user_id is None and complaint.session_key:
        if compare_digest(str(complaint.session_key), str(session_key)):
            return True

    if claim_token and complaint.claim_token:
        return compare_digest(str(complaint.claim_token), str(claim_token))

    return False


# --------------------------------------------------------------------------
# Public
# --------------------------------------------------------------------------

@tool('search_municipal_knowledge', auth=AUTH_NONE,
      rate_ip=60, rate_user=30, cacheable=True)
def search_municipal_knowledge(request, query='', lang='en'):
    from chatbot.models import KnowledgeChunk

    query = _clean(query, 300)
    if lang not in ('en', 'ne', 'new'):
        lang = 'en'

    rows = list(
        KnowledgeChunk.objects
        .filter(is_active=True, content__icontains=query)
        .values('title', 'content', 'source_type')[:5]
    )
    return {
        'passages': [{'title': r['title'], 'text': r['content']} for r in rows],
        'sources': sorted({r['source_type'] for r in rows if r['source_type']}),
        'found': bool(rows),
    }


@tool('get_complaint_status', auth=AUTH_OPTIONAL,
      rate_ip=20, rate_user=20, audit=True, cacheable=False)
def get_complaint_status(request, complaint_id='', claim_token=''):
    from complaints.models import Complaint, ComplaintStatusHistory

    ref = _clean(complaint_id, 12).upper()
    if not COMPLAINT_REF.match(ref):
        raise ToolInputError(NOT_FOUND)

    complaint = Complaint.objects.filter(complaint_id__iexact=ref).first()
    if complaint is None:
        # Every failure mode gives this same answer, so a malformed reference
        # and an unissued one leak nothing about the reference space. Status
        # itself is public by reference, matching the existing public tracking
        # page; the entropy of BK-XXXXXX plus a 20/hour ceiling is what makes
        # enumeration impractical. Contact details stay behind ownership.
        raise ToolInputError(NOT_FOUND)

    user = request.user
    is_staff_user = user.is_authenticated and (
        user.is_staff or user.role in ('staff', 'official', 'admin')
    )
    is_owner = _owns(request, complaint, claim_token)
    show_sensitive = is_owner or is_staff_user

    data = {
        'complaint_id': complaint.complaint_id,
        'title': complaint.title,
        'category': complaint.get_category_display(),
        'status': complaint.get_status_display(),
        'ward_number': complaint.ward_number,
        'created_at': complaint.created_at.isoformat(),
        'timeline': [
            {'status': h.new_status, 'at': h.changed_at.isoformat()}
            for h in ComplaintStatusHistory.objects
            .filter(complaint=complaint).order_by('changed_at')[:20]
        ],
    }
    if show_sensitive:
        data['submitter_name'] = complaint.submitter_name
        data['submitter_phone'] = complaint.submitter_phone
        data['submitter_email'] = complaint.submitter_email
    return data


@tool('find_attractions', auth=AUTH_NONE, rate_ip=120, rate_user=60, cacheable=True)
def find_attractions(request, query='', limit=MAX_ROWS):
    from tourism.models import Attraction

    qs = Attraction.objects.filter(is_active=True)
    if query:
        qs = qs.filter(name__icontains=_clean(query, 120))

    return [{
        'name': a.name,
        'category': a.category.name if a.category else None,
        'address': a.address,
        # Returned as stored or omitted — never inferred.
        'opening_hours': a.opening_hours or None,
        'entry_fee': None if a.is_free else (
            str(a.entry_fee) if a.entry_fee is not None else None
        ),
        'is_free': a.is_free,
    } for a in qs.select_related('category')[:_limit(limit)]]


@tool('find_businesses', auth=AUTH_NONE, rate_ip=120, rate_user=60, cacheable=True)
def find_businesses(request, query='', category='', limit=MAX_ROWS):
    from businesses.models import Business

    qs = Business.objects.filter(is_active=True)
    if query:
        qs = qs.filter(name__icontains=_clean(query, 120))
    if category:
        valid = {c[0] for c in Business.CATEGORY_CHOICES}
        cat = _clean(category, 30).lower()
        if cat not in valid:
            raise ToolInputError('I don\'t recognise that kind of business.')
        qs = qs.filter(category=cat)

    return [{
        'name': b.name,
        'category': b.get_category_display(),
        'address': b.address,
        'phone': b.phone,
        'opening_hours': b.opening_hours or None,
        'rating': b.avg_rating,
    } for b in qs[:_limit(limit)]]


@tool('list_events', auth=AUTH_NONE, rate_ip=120, rate_user=60, cacheable=True)
def list_events(request, limit=MAX_ROWS):
    from django.utils import timezone
    from events.models import Event

    qs = (Event.objects
          .filter(is_active=True, start_date__gte=timezone.now())
          .order_by('start_date'))

    return [{
        'name': e.name,
        'venue': e.venue,
        'starts': e.start_date.isoformat(),
        'is_free': e.is_free,
        'entry_fee': str(e.entry_fee) if e.entry_fee is not None else None,
    } for e in qs[:_limit(limit)]]


@tool('list_public_notices', auth=AUTH_NONE, rate_ip=120, rate_user=60, cacheable=True)
def list_public_notices(request, notice_type='', limit=MAX_ROWS):
    from services.models import PublicNotice

    qs = PublicNotice.objects.filter(is_active=True).order_by('-created_at')
    if notice_type:
        valid = {c[0] for c in PublicNotice.TYPE_CHOICES}
        nt = _clean(notice_type, 12).upper()
        if nt not in valid:
            raise ToolInputError('I don\'t recognise that kind of notice.')
        qs = qs.filter(notice_type=nt)

    return [{
        'title': n.title,
        'type': n.get_notice_type_display(),
        'reference_no': n.reference_no,
        'ward_number': n.ward_number,
        'deadline': n.deadline.isoformat() if n.deadline else None,
    } for n in qs[:_limit(limit)]]


# --------------------------------------------------------------------------
# The citizen's own records
# --------------------------------------------------------------------------

@tool('get_my_complaints', auth=AUTH_REQUIRED, rate_user=20, cacheable=False)
def get_my_complaints(request, limit=MAX_ROWS):
    from complaints.models import Complaint

    qs = Complaint.objects.filter(user=request.user).order_by('-created_at')
    return [{
        'complaint_id': c.complaint_id,
        'title': c.title,
        'category': c.get_category_display(),
        'status': c.get_status_display(),
        'ward_number': c.ward_number,
        'created_at': c.created_at.isoformat(),
    } for c in qs[:_limit(limit)]]


@tool('get_my_service_requests', auth=AUTH_REQUIRED, rate_user=20, cacheable=False)
def get_my_service_requests(request, limit=MAX_ROWS):
    from services.models import ServiceRequest

    qs = ServiceRequest.objects.filter(applicant=request.user).order_by('-created_at')
    return [{
        'reference_number': s.reference_number,
        'service_type': s.get_service_type_display(),
        'status': s.get_status_display(),
        'ward_number': s.ward_number,
        # Read from the record, never computed.
        'fee_amount': str(s.fee_amount) if s.fee_amount is not None else None,
        'fee_paid': s.fee_paid,
    } for s in qs[:_limit(limit)]]


@tool('get_my_proposals', auth=AUTH_REQUIRED, rate_user=20, cacheable=False)
def get_my_proposals(request, limit=MAX_ROWS):
    from civic.models import Proposal

    qs = Proposal.objects.filter(submitted_by=request.user).order_by('-created_at')
    return [{
        'title': p.title,
        'category': p.get_category_display(),
        'status': p.get_status_display(),
        'ward_number': p.ward_number,
        'support_count': p.support_count,
    } for p in qs[:_limit(limit)]]


@tool('get_my_notifications', auth=AUTH_REQUIRED, rate_user=30, cacheable=False)
def get_my_notifications(request, unread_only=False, limit=MAX_ROWS):
    from accounts.models import Notification

    qs = Notification.objects.filter(user=request.user)
    if unread_only:
        qs = qs.filter(is_read=False)

    return [{
        'message': n.message,
        'url': n.url,
        'is_read': n.is_read,
        'created_at': n.created_at.isoformat(),
    } for n in qs[:_limit(limit)]]
