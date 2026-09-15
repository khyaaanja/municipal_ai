"""Populate KnowledgeChunk from KnowledgeBase.

KnowledgeBase holds the authored municipal content; KnowledgeChunk is what
retrieval actually reads. Until this runs, the assistant's knowledge search
falls back to substring matching over an empty table.
"""
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from chatbot.models import KnowledgeBase, KnowledgeChunk

# KnowledgeBase categories are editorial; KnowledgeChunk source types are
# retrieval-facing. Anything unmapped lands in 'general' rather than being
# dropped silently.
CATEGORY_TO_SOURCE = {
    'general': 'general',
    'heritage': 'heritage',
    'culture': 'culture',
    'transport': 'transport',
    'emergency': 'emergency',
    'services': 'service',
    'rules': 'procedure',
}

TARGET_CHARS = 800
MIN_CHARS = 120


def split_content(text, target=TARGET_CHARS):
    """Split on sentence boundaries, keeping chunks near the target size."""
    text = re.sub(r'\s+', ' ', (text or '')).strip()
    if not text:
        return []
    if len(text) <= target:
        return [text]

    sentences = re.split(r'(?<=[.!?।])\s+', text)
    chunks, current = [], ''
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > target:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f'{current} {sentence}'.strip()
    if current.strip():
        chunks.append(current.strip())

    # A trailing fragment is folded back rather than stored as a stub. Pop
    # first: the index must be resolved against the already-shortened list.
    if len(chunks) > 1 and len(chunks[-1]) < MIN_CHARS:
        tail = chunks.pop()
        chunks[-1] = f'{chunks[-1]} {tail}'
    return chunks


class Command(BaseCommand):
    help = 'Build KnowledgeChunk rows from KnowledgeBase entries.'

    def add_arguments(self, parser):
        parser.add_argument('--rebuild', action='store_true',
                            help='Delete existing chunks before indexing.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would be written, change nothing.')

    def handle(self, *args, **options):
        entries = KnowledgeBase.objects.filter(is_active=True)
        total = entries.count()
        if not total:
            self.stdout.write(self.style.WARNING(
                'KnowledgeBase is empty — run the seed command first.'))
            return

        planned = []
        for entry in entries.iterator():
            source_type = CATEGORY_TO_SOURCE.get(entry.category, 'general')
            for index, chunk in enumerate(split_content(entry.content), start=1):
                title = entry.title if index == 1 else f'{entry.title} ({index})'
                planned.append(KnowledgeChunk(
                    source_type=source_type,
                    title=title[:200],
                    content=chunk,
                    is_active=True,
                ))

        if options['dry_run']:
            self.stdout.write(
                f'{total} active entries would produce {len(planned)} chunks.')
            return

        with transaction.atomic():
            if options['rebuild']:
                removed = KnowledgeChunk.objects.all().delete()[0]
                self.stdout.write(f'Removed {removed} existing chunks.')
            KnowledgeChunk.objects.bulk_create(planned, batch_size=200)

        self.stdout.write(self.style.SUCCESS(
            f'Indexed {total} entries into {len(planned)} chunks.'))
