import random
import string
from django.db import models
from django.conf import settings
from django.utils import timezone


def generate_sr_id():
    from django.db import IntegrityError
    prefix = timezone.now().strftime('SR-%Y%m-')
    for _ in range(10):
        sid = prefix + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not ServiceRequest.objects.filter(reference_number=sid).exists():
            return sid
    raise RuntimeError("Could not generate unique service request ID after 10 attempts")


class ServiceRequest(models.Model):
    SERVICE_CHOICES = [
        ('BIRTH_CERT',      'Birth Certificate'),
        ('DEATH_CERT',      'Death Certificate'),
        ('MARRIAGE_REG',    'Marriage Registration'),
        ('PROPERTY_TAX',    'Property Tax'),
        ('BUILDING_PERMIT', 'Building Permit'),
        ('WATER_CONN',      'Water Connection'),
    ]
    STATUS_CHOICES = [
        ('SUBMITTED',  'Submitted'),
        ('DOCUMENTS',  'Documents Required'),
        ('IN_REVIEW',  'In Review'),
        ('APPROVED',   'Approved'),
        ('REJECTED',   'Rejected'),
        ('READY',      'Ready for Collection'),
        ('COMPLETED',  'Completed'),
    ]

    reference_number    = models.CharField(max_length=18, unique=True,
                                           default=generate_sr_id, editable=False)
    service_type        = models.CharField(max_length=20, choices=SERVICE_CHOICES)
    ward_number         = models.IntegerField(db_index=True)
    applicant           = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                            related_name='service_requests')
    applicant_name      = models.CharField(max_length=150)
    applicant_phone     = models.CharField(max_length=20)
    applicant_address   = models.TextField()
    details             = models.TextField()
    document_1          = models.FileField(upload_to='service_docs/%Y/%m/', null=True, blank=True)
    document_2          = models.FileField(upload_to='service_docs/%Y/%m/', null=True, blank=True)
    document_3          = models.FileField(upload_to='service_docs/%Y/%m/', null=True, blank=True)
    status              = models.CharField(max_length=12, choices=STATUS_CHOICES,
                                           default='SUBMITTED')
    staff_notes         = models.TextField(blank=True)
    assigned_to         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                            null=True, blank=True,
                                            related_name='assigned_service_requests')
    documents_requested = models.TextField(blank=True)
    fee_amount          = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fee_paid            = models.BooleanField(default=False)
    estimated_ready     = models.DateField(null=True, blank=True)
    created_at          = models.DateTimeField(auto_now_add=True)
    updated_at          = models.DateTimeField(auto_now=True)
    completed_at        = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'service_requests'
        indexes = [
            models.Index(fields=['ward_number', 'status']),
            models.Index(fields=['applicant', 'status']),
        ]

    def __str__(self):
        return self.reference_number


class ServiceRequestStatusHistory(models.Model):
    request    = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='history')
    old_status = models.CharField(max_length=12, blank=True)
    new_status = models.CharField(max_length=12)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True)
    note       = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'service_request_history'
        ordering = ['-changed_at']


class PublicNotice(models.Model):
    TYPE_CHOICES = [
        ('TENDER',     'Tender'),
        ('JOB',        'Job'),
        ('NOTICE',     'Notice'),
        ('REGULATION', 'Regulation'),
        ('OTHER',      'Other'),
    ]

    ward_number  = models.IntegerField(null=True, blank=True)
    notice_type  = models.CharField(max_length=12, choices=TYPE_CHOICES)
    title        = models.CharField(max_length=200)
    body         = models.TextField()
    reference_no = models.CharField(max_length=100, blank=True)
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='published_notices')
    attachment   = models.FileField(upload_to='notices/%Y/%m/', null=True, blank=True)
    deadline     = models.DateField(null=True, blank=True)
    is_active    = models.BooleanField(default=True, db_index=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'public_notices'
        indexes = [models.Index(fields=['is_active', 'notice_type'])]

    def __str__(self):
        return self.title
