"""Phase 7 write tools.

Two steps, never one. draft_complaint validates and stages a payload;
confirm_complaint executes the payload the server stored. The model can
influence what is drafted, never what is executed.
"""
from django.core.exceptions import ValidationError

from .base import AUTH_OPTIONAL, AUTH_REQUIRED, ToolInputError, audit_log, tool
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

    # Evidence arrives on the confirming request rather than in the stored
    # payload: an uploaded file is not JSON-serialisable, and keeping bytes
    # out of the pending store means a stale token cannot resurrect them.
    files = getattr(request, 'FILES', None)
    photos = files.getlist('photos') if files else []

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
            photos=photos,
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
        'photos_attached': complaint.photos.count(),
        'complaint_id': complaint.complaint_id,
        'claim_token': str(complaint.claim_token) if complaint.claim_token else None,
        'status': complaint.get_status_display(),
    }


# ---------------------------------------------------------------------------
# Phase 9 — apply for a municipal service
# ---------------------------------------------------------------------------

SERVICE_ACTION = 'create_service_request'


@tool('draft_service_request', auth=AUTH_REQUIRED, rate_user=5,
      audit=True, cacheable=False)
def draft_service_request(request, service_type='', ward_number=None,
                          applicant_name='', applicant_phone='',
                          applicant_address='', details=''):
    from services.services import (SERVICE_LABELS, VALID_SERVICE_TYPES,
                                   clean_ward, validate)

    service_type = (service_type or '').strip().upper()
    if service_type not in VALID_SERVICE_TYPES:
        offered = ', '.join(sorted(SERVICE_LABELS.values()))
        raise ToolInputError(f'I can help you apply for: {offered}. Which one?')

    user = request.user
    applicant_name = (applicant_name or user.get_full_name()
                      or user.username or '').strip()

    payload = {
        'service_type': service_type,
        'ward_number': clean_ward(ward_number),
        'applicant_name': applicant_name[:150],
        'applicant_phone': (applicant_phone or '').strip()[:20],
        'applicant_address': (applicant_address or '').strip(),
        'details': (details or '').strip(),
    }

    errors = validate(**payload)
    if errors:
        raise ToolInputError(' '.join(errors))

    token = create(request, SERVICE_ACTION, payload)
    return {'stage': 'awaiting_confirmation', 'token': token, 'draft': payload}


@tool('confirm_service_request', auth=AUTH_REQUIRED, rate_user=5,
      audit=True, cacheable=False)
def confirm_service_request(request, token=''):
    from services.services import create_service_request

    try:
        payload = consume(request, SERVICE_ACTION, token)
    except PendingError as exc:
        audit_log.info('tool=confirm_service_request outcome=rejected reason=%s', exc)
        raise ToolInputError(
            'That confirmation has expired or was already used — nothing was '
            'submitted. Tell me again and I will prepare a fresh application.'
        )

    try:
        sr = create_service_request(applicant=request.user, **payload)
    except ValidationError as exc:
        raise ToolInputError(' '.join(exc.messages))

    audit_log.info(
        'tool=confirm_service_request outcome=created reference=%s service=%s',
        sr.reference_number, sr.service_type,
    )
    return {
        'stage': 'submitted',
        'reference_number': sr.reference_number,
        'service_type': sr.get_service_type_display(),
        'status': sr.get_status_display(),
        # Read from the record, never computed by the model.
        'fee_amount': str(sr.fee_amount) if sr.fee_amount is not None else None,
    }


# ---------------------------------------------------------------------------
# Phase 10 — submit a citizen proposal
# ---------------------------------------------------------------------------

PROPOSAL_ACTION = 'create_proposal'


@tool('draft_proposal', auth=AUTH_REQUIRED, rate_user=3,
      audit=True, cacheable=False)
def draft_proposal(request, category='', title='', description='',
                   ward_number=None, expected_benefit=''):
    from civic.services import CATEGORY_LABELS, VALID_CATEGORIES, clean_ward, validate

    category = (category or '').strip().upper()
    if category not in VALID_CATEGORIES:
        offered = ', '.join(sorted(CATEGORY_LABELS.values()))
        raise ToolInputError(f'Which area is this proposal about? {offered}')

    payload = {
        'category': category,
        'title': (title or '').strip()[:200],
        'description': (description or '').strip(),
        'ward_number': clean_ward(ward_number),
        'expected_benefit': (expected_benefit or '').strip(),
    }

    errors = validate(category=payload['category'], title=payload['title'],
                      description=payload['description'],
                      ward_number=payload['ward_number'])
    if errors:
        raise ToolInputError(' '.join(errors))

    token = create(request, PROPOSAL_ACTION, payload)
    return {'stage': 'awaiting_confirmation', 'token': token, 'draft': payload}


@tool('confirm_proposal', auth=AUTH_REQUIRED, rate_user=3,
      audit=True, cacheable=False)
def confirm_proposal(request, token=''):
    from civic.services import create_proposal

    try:
        payload = consume(request, PROPOSAL_ACTION, token)
    except PendingError as exc:
        audit_log.info('tool=confirm_proposal outcome=rejected reason=%s', exc)
        raise ToolInputError(
            'That confirmation has expired or was already used — nothing was '
            'submitted. Tell me the idea again and I will redraft it.'
        )

    try:
        proposal = create_proposal(submitted_by=request.user, **payload)
    except ValidationError as exc:
        raise ToolInputError(' '.join(exc.messages))

    audit_log.info(
        'tool=confirm_proposal outcome=created proposal=%s ward=%s',
        proposal.pk, proposal.ward_number,
    )
    return {
        'stage': 'submitted',
        'proposal_id': proposal.pk,
        'title': proposal.title,
        'category': proposal.get_category_display(),
        'status': proposal.get_status_display(),
        'ward_number': proposal.ward_number,
    }
