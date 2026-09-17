"""Repair conjuncts the Preeti conversion dropped from stored content.

Retrieval already repairs these on the way into the matcher, so search works
either way. This is about what the citizen reads: an answer quoted from the
municipality's records should not show "विद्ालय" to someone who knows the
word is विद्यालय. A document that looks mistranscribed is a document that
looks untrustworthy, and these are quoted as the municipal record.

The rules are in chatbot.tools.retrieval so the matcher and the stored text
cannot drift apart.
"""
import re

from django.core.management.base import BaseCommand

from chatbot.tools.retrieval import repair_preeti

# A halant followed by a vowel sign: the marker of a dropped consonant.
BROKEN = re.compile('[क-ह]्[ा-ौॢॣ]')


class Command(BaseCommand):
    help = 'Restore conjuncts lost in the Preeti-to-Unicode conversion.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change, write nothing.')

    def handle(self, *args, **options):
        from chatbot.models import KnowledgeBase, KnowledgeChunk

        dry = options['dry_run']
        changed = 0
        samples = []
        for model in (KnowledgeBase, KnowledgeChunk):
            for row in model.objects.all():
                body = row.content or ''
                if not BROKEN.search(body):
                    continue
                fixed = repair_preeti(body)
                if fixed == body:
                    continue
                changed += 1
                if len(samples) < 6:
                    match = BROKEN.search(body)
                    start = max(0, match.start() - 20)
                    samples.append(
                        f'  {model.__name__}[{row.pk}] '
                        f'{body[start:match.end() + 20]!r}'
                    )
                if not dry:
                    row.content = fixed
                    row.save(update_fields=['content'])

        for line in samples:
            self.stdout.write(line)
        verb = 'would repair' if dry else 'repaired'
        self.stdout.write(self.style.SUCCESS(f'{verb} {changed} row(s)'))
        if not dry and changed:
            self.stdout.write(
                'Re-run index_knowledge_base if only KnowledgeBase changed.')
