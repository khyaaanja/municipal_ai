import random
import string
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


def generate_complaint_id():
    from django.db import IntegrityError
    for _ in range(10):
        cid = 'BK-' + ''.join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )
        if not Complaint.objects.filter(complaint_id=cid).exists():
            return cid
    raise RuntimeError("Could not generate unique complaint ID after 10 attempts")


class Complaint(models.Model):
    CATEGORY_CHOICES = [
        ('INFRASTRUCTURE', '🏗 Infrastructure'),
        ('SANITATION',     '🗑 Sanitation'),
        ('WATER',          '💧 Water Supply'),
        ('ELECTRICITY',    '⚡ Electricity'),
        ('ROAD',           '🛣 Road & Transport'),
        ('NOISE',          '🔊 Noise & Pollution'),
        ('OTHER',          '📋 Other'),
    ]
    STATUS_CHOICES = [
        ('PENDING',     'Pending'),
        ('IN_REVIEW',   'In Review'),
        ('IN_PROGRESS', 'In Progress'),
        ('RESOLVED',    'Resolved'),
        ('REJECTED',    'Rejected'),
    ]
    PRIORITY_CHOICES = [
        ('LOW',      'Low'),
        ('MEDIUM',   'Medium'),
        ('HIGH',     'High'),
        ('CRITICAL', 'Critical'),
    ]

    complaint_id    = models.CharField(
                        max_length=10, unique=True,
                        default=generate_complaint_id,
                        editable=False, db_index=True)
    category        = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    title           = models.CharField(max_length=200)
    description     = models.TextField()
    location        = models.CharField(max_length=300)
    submitter_name  = models.CharField(max_length=100)
    submitter_phone = models.CharField(max_length=20, blank=True)
    submitter_email = models.EmailField(blank=True)
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    priority        = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='MEDIUM')
    ward_number     = models.IntegerField(null=True, blank=True, help_text='Ward number (1-17) the complaint belongs to')
    admin_notes     = models.TextField(blank=True, null=True)
    latitude        = models.FloatField(null=True, blank=True)
    longitude       = models.FloatField(null=True, blank=True)
    user            = models.ForeignKey(
                        settings.AUTH_USER_MODEL,
                        on_delete=models.SET_NULL,
                        null=True, blank=True,
                        related_name='complaints')
    claim_token     = models.UUIDField(
                        null=True, blank=True, unique=True, db_index=True,
                        help_text='One-time UUID for anonymous claim; nulled after claimed.')
    session_key     = models.CharField(
                        max_length=40, blank=True, default='',
                        help_text='Browser session at submission; enables same-session auto-claim.')
    assigned_to     = models.ForeignKey(
                        settings.AUTH_USER_MODEL,
                        on_delete=models.SET_NULL,
                        null=True, blank=True,
                        related_name='assigned_complaints',
                        help_text='Staff member assigned to handle this complaint')
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)
    resolved_at     = models.DateTimeField(null=True, blank=True)

    SLA_DAYS = {'CRITICAL': 1, 'HIGH': 3, 'MEDIUM': 7, 'LOW': 14}

    class Meta:
        ordering = ['-created_at']
        db_table = 'complaints'
        indexes = [
            models.Index(fields=['status', 'created_at'], name='idx_complaint_status_created'),
            models.Index(fields=['category', 'status'], name='idx_complaint_cat_status'),
            models.Index(fields=['priority', 'status', 'created_at'], name='idx_cmpl_prio_status_created'),
            models.Index(fields=['ward_number', 'status'], name='idx_complaint_ward_status'),
            models.Index(fields=['user', '-created_at'], name='idx_complaint_user_created'),
        ]

    def __str__(self):
        return f"{self.complaint_id} — {self.title}"

    @property
    def sla_deadline(self):
        days = self.SLA_DAYS.get(self.priority, 7)
        return self.created_at + timezone.timedelta(days=days)

    @property
    def is_overdue(self):
        return self.status not in ('RESOLVED', 'REJECTED') and timezone.now() > self.sla_deadline


class ComplaintPhoto(models.Model):
    complaint  = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='photos')
    image      = models.ImageField(upload_to='complaint_photos/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Photo for {self.complaint.complaint_id}"


class ComplaintStatusHistory(models.Model):
    complaint   = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='history')
    old_status  = models.CharField(max_length=20, blank=True)
    new_status  = models.CharField(max_length=20)
    changed_by  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    note        = models.TextField(blank=True)
    changed_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.complaint.complaint_id}: {self.old_status} → {self.new_status}"


class ComplaintVote(models.Model):
    complaint   = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='votes')
    session_key = models.CharField(max_length=40, blank=True)
    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('complaint', 'session_key'), ('complaint', 'user')]

    def __str__(self):
        return f"Vote on {self.complaint.complaint_id}"


class ComplaintFollow(models.Model):
    complaint  = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='followers')
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='followed_complaints')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('complaint', 'user')]
        db_table = 'complaint_follows'

    def __str__(self):
        return f"{self.user} follows {self.complaint.complaint_id}"


class ComplaintRating(models.Model):
    RATING_CHOICES = [(1, 'Thumbs Down'), (5, 'Thumbs Up')]
    complaint  = models.OneToOneField(Complaint, on_delete=models.CASCADE, related_name='rating')
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='complaint_ratings')
    score      = models.IntegerField(choices=RATING_CHOICES)
    comment    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'complaint_ratings'

    def __str__(self):
        return f"Rating {self.score} for {self.complaint.complaint_id}"


class ComplaintUpdate(models.Model):
    complaint  = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='updates')
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='complaint_updates')
    message    = models.TextField()
    photo      = models.ImageField(upload_to='complaint_updates/%Y/%m/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'complaint_updates'
        ordering = ['created_at']

    def __str__(self):
        return f"Update by {self.user} on {self.complaint.complaint_id}"


class ComplaintSupport(models.Model):
    """Citizen formally declares they are affected by this complaint.
    Distinct from anonymous votes — requires login, visible to officials as social proof."""
    complaint   = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='supporters')
    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='supported_complaints')
    supported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('complaint', 'user')]
        db_table = 'complaint_supports'
        ordering = ['supported_at']

    def __str__(self):
        return f"{self.user} supports {self.complaint.complaint_id}"


class ComplaintEscalation(models.Model):
    """Formal escalation of a stalled complaint to the Mayor.
    Only available to logged-in citizens when SLA is breached — creates official accountability record."""
    REASON_CHOICES = [
        ('no_update',       'No update for over a week'),
        ('issue_worsened',  'Issue has worsened since filing'),
        ('partial_fix',     'Partial fix — problem remains'),
        ('wrong_resolution','Marked resolved but issue persists'),
        ('safety_risk',     'Poses immediate safety risk'),
    ]
    complaint    = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name='escalations')
    escalated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='escalated_complaints')
    reason       = models.CharField(max_length=20, choices=REASON_CHOICES)
    note         = models.TextField(blank=True)
    escalated_at = models.DateTimeField(auto_now_add=True)
    is_reviewed  = models.BooleanField(default=False)
    reviewed_at  = models.DateTimeField(null=True, blank=True)
    reviewed_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reviewed_escalations'
    )
    mayor_note   = models.TextField(blank=True)

    class Meta:
        db_table = 'complaint_escalations'
        ordering = ['-escalated_at']

    def __str__(self):
        return f"Escalation of {self.complaint.complaint_id} by {self.escalated_by}"


class ServiceRating(models.Model):
    """Post-resolution service quality rating by the citizen who filed the complaint."""
    STAR_CHOICES = [(1, '1 — Very Poor'), (2, '2 — Poor'), (3, '3 — Average'), (4, '4 — Good'), (5, '5 — Excellent')]

    complaint = models.OneToOneField(
        Complaint, on_delete=models.CASCADE, related_name='service_rating'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='service_ratings'
    )
    rating = models.IntegerField(choices=STAR_CHOICES)
    feedback = models.TextField(blank=True, max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'service_ratings'

    def __str__(self):
        return f"ServiceRating {self.rating}★ for {self.complaint.complaint_id}"
