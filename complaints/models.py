import random
import string
from django.db import models
from django.conf import settings


def generate_complaint_id():
    while True:
        cid = 'BK-' + ''.join(
            random.choices(string.ascii_uppercase + string.digits, k=5)
        )
        if not Complaint.objects.filter(complaint_id=cid).exists():
            return cid


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
    admin_notes     = models.TextField(blank=True, null=True)
    user            = models.ForeignKey(
                        settings.AUTH_USER_MODEL,
                        on_delete=models.SET_NULL,
                        null=True, blank=True,
                        related_name='complaints')
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)
    resolved_at     = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        db_table = 'complaints'

    def __str__(self):
        return f"{self.complaint_id} — {self.title}"
