"""Shared complaint creation.

Single validated path into Complaint, used by both the web form and the
assistant's tool so neither can drift from the other's rules.
"""
import uuid

from django.core.exceptions import ValidationError

from .models import Complaint, ComplaintPhoto

VALID_CATEGORIES = {c[0] for c in Complaint.CATEGORY_CHOICES}
VALID_PRIORITIES = {p[0] for p in Complaint.PRIORITY_CHOICES}
WARD_MIN, WARD_MAX = 1, 17
MAX_PHOTOS = 5


def clean_ward(raw):
    try:
        ward = int(raw) if raw not in ('', None) else None
    except (TypeError, ValueError):
        return None
    if ward is None or not (WARD_MIN <= ward <= WARD_MAX):
        return None
    return ward


def clean_coord(raw):
    try:
        return float(raw) or None
    except (TypeError, ValueError):
        return None


def validate(*, category, title, description, location, submitter_name):
    """Return a list of human-readable errors; empty means valid."""
    errors = []
    if not category:
        errors.append('Please select a category.')
    elif category not in VALID_CATEGORIES:
        # The model declares choices but does not enforce them on create(),
        # so an unchecked value would be stored verbatim.
        errors.append('Please select a valid category.')
    if not title:
        errors.append('Title is required.')
    if not description:
        errors.append('Description is required.')
    if not location:
        errors.append('Location is required.')
    if not submitter_name:
        errors.append('Your name is required.')
    return errors


def create_complaint(*, category, title, description, location, submitter_name,
                     phone='', email='', priority='MEDIUM', ward_number=None,
                     latitude=None, longitude=None, user=None, session_key='',
                     photos=()):
    """Validate and persist a complaint. Raises ValidationError on bad input."""
    category = (category or '').strip().upper()
    title = (title or '').strip()[:200]
    description = (description or '').strip()
    location = (location or '').strip()[:300]
    submitter_name = (submitter_name or '').strip()[:100]

    errors = validate(
        category=category, title=title, description=description,
        location=location, submitter_name=submitter_name,
    )
    if errors:
        raise ValidationError(errors)

    if priority not in VALID_PRIORITIES:
        priority = 'MEDIUM'

    is_anon = user is None or not getattr(user, 'is_authenticated', False)

    complaint = Complaint.objects.create(
        category=category,
        title=title,
        description=description,
        location=location,
        submitter_name=submitter_name,
        submitter_phone=(phone or '').strip()[:20],
        submitter_email=(email or '').strip(),
        priority=priority,
        ward_number=ward_number,
        latitude=latitude,
        longitude=longitude,
        user=None if is_anon else user,
        claim_token=uuid.uuid4() if is_anon else None,
        session_key=session_key if is_anon else '',
    )

    for photo in list(photos)[:MAX_PHOTOS]:
        _attach_photo(complaint, photo)

    return complaint


def _attach_photo(complaint, photo):
    from core.utils import MAX_AI_IMAGE_BYTES, valid_uploaded_image
    try:
        if not valid_uploaded_image(photo, MAX_AI_IMAGE_BYTES):
            return
        ComplaintPhoto.objects.create(complaint=complaint, image=photo)
    except Exception:
        pass
