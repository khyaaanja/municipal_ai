"""Shared service-request creation.

Single validated path into ServiceRequest, used by both the web form and
the assistant's tool so neither can drift from the other's rules.
"""
from django.core.exceptions import ValidationError

from .models import ServiceRequest

VALID_SERVICE_TYPES = {c[0] for c in ServiceRequest.SERVICE_CHOICES}
SERVICE_LABELS = dict(ServiceRequest.SERVICE_CHOICES)
WARD_MIN, WARD_MAX = 1, 17

DETAILS_MIN, DETAILS_MAX = 15, 2000


def clean_ward(raw):
    try:
        ward = int(raw) if raw not in ('', None) else None
    except (TypeError, ValueError):
        return None
    if ward is None or not (WARD_MIN <= ward <= WARD_MAX):
        return None
    return ward


def validate(*, service_type, ward_number, applicant_name, applicant_phone,
             applicant_address, details):
    errors = []
    if not service_type:
        errors.append('Please choose which service you need.')
    elif service_type not in VALID_SERVICE_TYPES:
        # The model declares choices but does not enforce them on create().
        errors.append('That is not a service the municipality offers.')
    if ward_number is None:
        errors.append(f'A ward number between {WARD_MIN} and {WARD_MAX} is required.')
    if not applicant_name:
        errors.append('Your name is required.')
    if not applicant_phone:
        errors.append('A contact phone number is required.')
    if not applicant_address:
        errors.append('Your address is required.')
    if not details:
        errors.append('Some detail about the request is required.')
    elif len(details) < DETAILS_MIN:
        errors.append('Please describe the request in a little more detail.')
    return errors


def create_service_request(*, applicant, service_type, ward_number,
                           applicant_name, applicant_phone, applicant_address,
                           details):
    """Validate and persist a service request. Raises ValidationError."""
    if applicant is None or not getattr(applicant, 'is_authenticated', False):
        # Unlike complaints, there is no anonymous route: the model requires
        # an applicant and the record carries legal weight.
        raise ValidationError(['You need an account to apply for a service.'])

    service_type = (service_type or '').strip().upper()
    applicant_name = (applicant_name or '').strip()[:150]
    applicant_phone = (applicant_phone or '').strip()[:20]
    applicant_address = (applicant_address or '').strip()
    details = (details or '').strip()[:DETAILS_MAX]
    ward_number = clean_ward(ward_number)

    errors = validate(
        service_type=service_type, ward_number=ward_number,
        applicant_name=applicant_name, applicant_phone=applicant_phone,
        applicant_address=applicant_address, details=details,
    )
    if errors:
        raise ValidationError(errors)

    return ServiceRequest.objects.create(
        applicant=applicant,
        service_type=service_type,
        ward_number=ward_number,
        applicant_name=applicant_name,
        applicant_phone=applicant_phone,
        applicant_address=applicant_address,
        details=details,
    )
