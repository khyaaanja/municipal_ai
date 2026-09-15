"""Shared proposal creation.

Single validated path into Proposal, used by both the web form and the
assistant's tool.
"""
from django.core.exceptions import ValidationError

from .models import Proposal

VALID_CATEGORIES = {c[0] for c in Proposal.CATEGORY_CHOICES}
CATEGORY_LABELS = dict(Proposal.CATEGORY_CHOICES)
WARD_MIN, WARD_MAX = 1, 17

TITLE_MAX = 200
DESC_MIN, DESC_MAX = 40, 4000
BENEFIT_MAX = 2000


def clean_ward(raw):
    try:
        ward = int(raw) if raw not in ('', None) else None
    except (TypeError, ValueError):
        return None
    if ward is None or not (WARD_MIN <= ward <= WARD_MAX):
        return None
    return ward


def validate(*, category, title, description, ward_number):
    errors = []
    if not category:
        errors.append('Please choose a category for the proposal.')
    elif category not in VALID_CATEGORIES:
        errors.append('That is not a valid proposal category.')
    if not title:
        errors.append('A title is required.')
    if not description:
        errors.append('A description is required.')
    elif len(description) < DESC_MIN:
        errors.append('Please describe the proposal in more detail.')
    if ward_number is None:
        errors.append(f'A ward number between {WARD_MIN} and {WARD_MAX} is required.')
    return errors


def create_proposal(*, submitted_by, category, title, description,
                    ward_number, expected_benefit=''):
    """Validate and persist a proposal. Raises ValidationError."""
    if submitted_by is None or not getattr(submitted_by, 'is_authenticated', False):
        raise ValidationError(['You need an account to submit a proposal.'])

    category = (category or '').strip().upper()
    title = (title or '').strip()[:TITLE_MAX]
    description = (description or '').strip()[:DESC_MAX]
    expected_benefit = (expected_benefit or '').strip()[:BENEFIT_MAX]
    ward_number = clean_ward(ward_number)

    errors = validate(category=category, title=title,
                      description=description, ward_number=ward_number)
    if errors:
        raise ValidationError(errors)

    return Proposal.objects.create(
        submitted_by=submitted_by,
        category=category,
        title=title,
        description=description,
        expected_benefit=expected_benefit,
        ward_number=ward_number,
    )
