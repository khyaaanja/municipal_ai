"""Phase 7 write tools.

Two steps, never one. draft_complaint validates and stages a payload;
confirm_complaint executes the payload the server stored. The model can
influence what is drafted, never what is executed.
"""
from django.core.exceptions import ValidationError

from .base import AUTH_OPTIONAL, ToolInputError, audit_log, tool
from .pending import PendingError, consume, create

ACTION = 'create_complaint'

TITLE_MAX = 200
DESC_MIN, DESC_MAX = 20, 2000
LOCATION_MAX = 300


def _require(value, field, minimum=1, maximum=2000):
    text = (value or '').strip()
    if len(text) < minimum:
        raise ToolInputError(
            f'I need a bit more for the {field} — at least {minimum} characters.'
            if minimum > 1 else f'The {field} is required.'
        )
    return text[:maximum]


@tool('draft_complaint', auth=AUTH_OPTIONAL, rate_user=5, rate_ip=5,
      audit=True, cacheable=False)
def draft_complaint(request, category='', title='', description='',
                    location='', ward_number=None, submitter_name='',
                    phone='', email=''):
    from complaints.services import VALID_CATEGORIES, clean_ward

    category = (category or '').strip().upper()
    if category not in VALID_CATEGORIES:
        raise ToolInputError(
            'I need to know what kind of issue this is — roads, sanitation, '
            'water, electricity, noise or infrastructure.'
        )

    title = _require(title, 'title', 1, TITLE_MAX)
    description = _require(description, 'description', DESC_MIN, DESC_MAX)
    location = _require(location, 'location', 1, LOCATION_MAX)

    if request.user.is_authenticated:
        submitter_name = (submitter_name
                          or request.user.get_full_name()
                          or request.user.username)
        email = email or request.user.email
    submitter_name = _require(submitter_name, 'name', 1, 100)

    if getattr(request, 'session', None) is not None \
            and not request.session.session_key:
        request.session.create()

    payload = {
        'category': category,
        'title': title,
        'description': description,
        'location': location,
        'ward_number': clean_ward(ward_number),
        'submitter_name': submitter_name,
        'phone': (phone or '').strip()[:20],
        'email': (email or '').strip(),
    }
    token = create(request, ACTION, payload)

    return {'stage': 'awaiting_confirmation', 'token': token, 'draft': payload}


@tool('confirm_complaint', auth=AUTH_OPTIONAL, rate_user=5, rate_ip=5,
      audit=True, cacheable=False)
def confirm_complaint(request, token=''):
    from complaints.services import create_complaint

    try:
        payload = consume(request, ACTION, token)
    except PendingError as exc:
        audit_log.info('tool=confirm_complaint outcome=rejected reason=%s', exc)
        raise ToolInputError(
            "That confirmation has expired or was already used — nothing was "
            "filed. Tell me the issue again and I'll prepare a fresh draft."
        )

    session = getattr(request, 'session', None)
    session_key = getattr(session, 'session_key', '') or ''

    try:
        complaint = create_complaint(
            category=payload['category'],
            title=payload['title'],
            description=payload['description'],
            location=payload['location'],
            submitter_name=payload['submitter_name'],
            phone=payload['phone'],
            email=payload['email'],
            ward_number=payload['ward_number'],
            user=request.user if request.user.is_authenticated else None,
            session_key=session_key,
        )
    except ValidationError as exc:
        # Re-validated server-side; the stored payload is still refused if the
        # rules changed between drafting and confirming.
        raise ToolInputError(' '.join(exc.messages))

    audit_log.info(
        'tool=confirm_complaint outcome=created complaint=%s ward=%s',
        complaint.complaint_id, complaint.ward_number,
    )

    return {
        'stage': 'filed',
        'complaint_id': complaint.complaint_id,
        'claim_token': str(complaint.claim_token) if complaint.claim_token else None,
        'status': complaint.get_status_display(),
    }
