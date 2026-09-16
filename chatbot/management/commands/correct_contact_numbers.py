"""Correct stored contact details that name an unpublished number.

Fixing the seed files does not fix a database that was already seeded from
them. `+977-1-6610000` was still being served from three indexed chunks --
all of them Emergency Contacts entries, which is the worst place for it --
after every source file had been corrected.

This command is idempotent and reports rather than guesses. It replaces only
the municipality's own number, where a published value exists to replace it
with. Every other number it finds without a cited source is listed for a
human to verify: an emergency number that is quietly deleted leaves a
tourist with nothing, and one that is quietly invented is worse.
"""
import re

from django.core.management.base import BaseCommand

from core import contacts

# Each correction replaces a number its supposed owner does not publish with
# one that owner does, and only where such a replacement was found. Nothing
# here is a guess; the source is named so the next reader can re-check it.
CORRECTIONS = (
    (
        # Not a number bhaktapurmun.gov.np lists anywhere.
        re.compile(r'\+?977[-\s]?1[-\s]?6610000|\b01[-\s]?6610000\b'),
        contacts.PHONE_PRIMARY,
        'https://bhaktapurmun.gov.np',
    ),
    (
        # Listed as "Tourist Police Bhaktapur". The Nepal Tourism Board
        # publishes 9851289448 for Bhaktapur; 4247041 appears nowhere in its
        # list, and the national toll-free line 1144 was missing entirely.
        re.compile(r'\+?977[-\s]?1[-\s]?4247041'),
        '9851289448 (toll free 1144)',
        'https://ntb.gov.np/en/plan-your-trip/before-you-come/tourist-police',
    ),
)

# Numbers that appear with no source and that this command must not touch.
UNSOURCED_NOTE = (
    'Numbers below have no cited source. Verify each against the '
    'organisation that owns it before relying on it.'
)
PHONE = re.compile(r'\+?977[-\s]?\d[-\s]?\d{6,7}\b')
VERIFIED = {contacts.PHONE_PRIMARY, contacts.PHONE_SECONDARY}


class Command(BaseCommand):
    help = 'Replace the unpublished municipality number in stored content.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='report what would change without writing',
        )

    def handle(self, *args, **options):
        from chatbot.models import KnowledgeBase, KnowledgeChunk

        dry = options['dry_run']
        changed = 0
        for model in (KnowledgeBase, KnowledgeChunk):
            for row in model.objects.all():
                body = row.content or ''
                fixed = body
                for pattern, replacement, source in CORRECTIONS:
                    if pattern.search(fixed):
                        fixed = pattern.sub(replacement, fixed)
                        self.stdout.write(
                            f'  {model.__name__}[{row.pk}] {row.title[:40]} '
                            f'-> {replacement} ({source})'
                        )
                if fixed == body:
                    continue
                changed += 1
                if not dry:
                    row.content = fixed
                    row.save(update_fields=['content'])

        verb = 'would correct' if dry else 'corrected'
        self.stdout.write(self.style.SUCCESS(f'{verb} {changed} row(s)'))

        # Report, do not touch.
        unsourced = {}
        for model in (KnowledgeBase, KnowledgeChunk):
            for row in model.objects.all():
                body = f'{row.title} {row.content or ""}'
                if 'bhaktapurmun.gov.np' in body or 'Source:' in body:
                    continue
                for number in set(PHONE.findall(body)):
                    if number.replace('+', '').replace('-', '') in {
                        v.replace('-', '') for v in VERIFIED
                    }:
                        continue
                    unsourced.setdefault(number, set()).add(row.title[:40])
        if unsourced:
            self.stdout.write(self.style.WARNING(f'\n{UNSOURCED_NOTE}'))
            for number in sorted(unsourced):
                where = ', '.join(sorted(unsourced[number])[:2])
                self.stdout.write(f'  {number:18} {where}')
