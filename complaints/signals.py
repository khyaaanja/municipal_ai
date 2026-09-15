import logging

from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Complaint, ComplaintStatusHistory

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Complaint)
def track_status_change(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old = Complaint.objects.get(pk=instance.pk)
    except Complaint.DoesNotExist:
        return
    if old.status != instance.status:
        instance._old_status = old.status
        # Auto-populate resolved_at when transitioning to RESOLVED
        if instance.status == 'RESOLVED' and not instance.resolved_at:
            from django.utils import timezone
            instance.resolved_at = timezone.now()
    else:
        instance._old_status = None


from django.db.models.signals import post_save


@receiver(post_save, sender=Complaint)
def create_status_history(sender, instance, created, **kwargs):
    if created:
        ComplaintStatusHistory.objects.create(
            complaint=instance,
            old_status='',
            new_status=instance.status,
        )
        return
    old_status = getattr(instance, '_old_status', None)
    if old_status is not None:
        ComplaintStatusHistory.objects.create(
            complaint=instance,
            old_status=old_status,
            new_status=instance.status,
            changed_by=getattr(instance, '_changed_by', None),
            note=getattr(instance, '_change_note', ''),
        )
        # Send notification to complaint owner
        if instance.user:
            try:
                from accounts.models import Notification
                status_labels = {
                    'PENDING': 'Pending', 'IN_REVIEW': 'Under Review',
                    'IN_PROGRESS': 'In Progress', 'RESOLVED': 'Resolved', 'REJECTED': 'Rejected',
                }
                Notification.objects.create(
                    user=instance.user,
                    message=f'Your complaint {instance.complaint_id} status changed to {status_labels.get(instance.status, instance.status)}.',
                    url=f'/complaint/status/{instance.complaint_id}/',
                )
            except Exception:
                logger.exception("Failed to create status-change notification for complaint %s", instance.complaint_id)
