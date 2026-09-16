import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from core import contacts

logger = logging.getLogger(__name__)


@receiver(post_save, sender='dashboard.ComplaintLog')
def notify_complaint_status_change(sender, instance, created, **kwargs):
    if not created:
        return
    # Dispatch email asynchronously via Celery so the staff dashboard
    # response isn't blocked by an SMTP call.
    try:
        from chatbot.tasks import send_complaint_notification_async
        send_complaint_notification_async.delay(instance.pk)
    except Exception:
        logger.warning("Celery unavailable — sending complaint notification synchronously")
        # Celery not running — send synchronously as fallback
        from django.core.mail import send_mail
        from django.conf import settings
        complaint = instance.complaint
        recipients = []
        if complaint.submitter_email:
            recipients.append(complaint.submitter_email)
        if complaint.user and complaint.user.email and complaint.user.email not in recipients:
            recipients.append(complaint.user.email)
        if not recipients:
            return
        status_labels = {
            'PENDING': 'Pending Review', 'IN_REVIEW': 'In Review',
            'IN_PROGRESS': 'In Progress', 'RESOLVED': 'Resolved ✓', 'REJECTED': 'Rejected',
        }
        send_mail(
            subject=f"[{complaint.complaint_id}] Status Update: {status_labels.get(instance.new_status, instance.new_status)}",
            message=(
                f"Dear {complaint.submitter_name or 'Citizen'},\n\n"
                f"Complaint {complaint.complaint_id} — {complaint.title}\n"
                f"Status: {status_labels.get(instance.old_status, instance.old_status)} → "
                f"{status_labels.get(instance.new_status, instance.new_status)}\n\n"
                f"Track: {getattr(settings, 'SITE_URL', 'http://localhost:8000')}"
                f"/complaint/track/?id={complaint.complaint_id}\n\n"
                f"Bhaktapur Municipality {contacts.PHONES}"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=True,
        )
