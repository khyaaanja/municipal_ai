"""
Weekly complaint digest email for mayor and officials.
Run: python manage.py send_weekly_digest
"""
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.db.models import Count, Q


class Command(BaseCommand):
    help = 'Send weekly complaint digest email to mayor and officials'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Print digest without sending email')

    def handle(self, *args, **options):
        from complaints.models import Complaint
        from accounts.models import User

        now = timezone.now()
        week_ago = now - timezone.timedelta(days=7)

        # This-week stats
        week_qs   = Complaint.objects.filter(created_at__gte=week_ago)
        new_count = week_qs.count()
        resolved_this_week = Complaint.objects.filter(status='RESOLVED', resolved_at__gte=week_ago).count()
        still_open = Complaint.objects.exclude(status__in=('RESOLVED', 'REJECTED')).count()

        # SLA overdue
        sla_map = {'CRITICAL': 1, 'HIGH': 3, 'MEDIUM': 7, 'LOW': 14}
        open_qs = Complaint.objects.exclude(status__in=('RESOLVED', 'REJECTED')).only('priority', 'created_at')
        overdue = sum(
            1 for c in open_qs
            if now > c.created_at + timezone.timedelta(days=sla_map.get(c.priority, 7))
        )

        # Top categories this week
        cat_label = dict(Complaint.CATEGORY_CHOICES)
        top_cats = list(
            week_qs.values('category').annotate(n=Count('id')).order_by('-n')[:5]
        )

        # Ward summary
        ward_lines = []
        for ward in range(1, 18):
            wc = week_qs.filter(ward_number=ward).count()
            if wc:
                ward_lines.append(f'  Ward {ward:2d}: {wc} new complaint{"s" if wc != 1 else ""}')

        body = (
            f"Bhaktapur Municipality — Weekly Complaint Digest\n"
            f"Week ending {now.strftime('%B %d, %Y')}\n"
            f"{'='*50}\n\n"
            f"NEW THIS WEEK\n"
            f"  Complaints filed   : {new_count}\n"
            f"  Resolved this week : {resolved_this_week}\n"
            f"  Still open         : {still_open}\n"
            f"  SLA overdue        : {overdue}\n\n"
        )

        if top_cats:
            body += "TOP CATEGORIES THIS WEEK\n"
            for row in top_cats:
                label = cat_label.get(row['category'], row['category'])
                body += f"  {label}: {row['n']}\n"
            body += "\n"

        if ward_lines:
            body += "BY WARD\n" + "\n".join(ward_lines) + "\n\n"

        body += (
            f"View full dashboard: {getattr(settings, 'SITE_URL', 'http://localhost:8000')}/mayor/\n\n"
            f"Bhaktapur Municipality Management System\n"
            f"This digest is sent automatically every week."
        )

        if options['dry_run']:
            self.stdout.write(body)
            self.stdout.write(self.style.SUCCESS('\n[DRY RUN] Email not sent.'))
            return

        recipients = list(
            User.objects.filter(role__in=('mayor', 'official'), is_active=True)
            .values_list('email', flat=True)
        )
        if not recipients:
            self.stdout.write(self.style.WARNING('No mayor or official accounts found — nothing sent.'))
            return

        try:
            send_mail(
                subject=f'[Weekly Digest] Bhaktapur Complaints — {now.strftime("%b %d, %Y")}',
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS(f'Digest sent to {len(recipients)} recipient(s): {", ".join(recipients)}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to send digest: {e}'))
