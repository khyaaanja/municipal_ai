from django.db import models
from django.conf import settings


class ComplaintLog(models.Model):
    complaint  = models.ForeignKey(
                   'complaints.Complaint',
                   on_delete=models.CASCADE,
                   related_name='logs')
    changed_by = models.ForeignKey(
                   settings.AUTH_USER_MODEL,
                   on_delete=models.SET_NULL, null=True)
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    note       = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']
