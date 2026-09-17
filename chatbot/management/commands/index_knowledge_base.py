"""Populate KnowledgeChunk from KnowledgeBase.

KnowledgeBase holds the authored municipal content; KnowledgeChunk is what
retrieval actually reads. Until this runs, the assistant's knowledge search
falls back to substring matching over an empty table.

This command is the only writer of KnowledgeChunk, so the table is entirely
derived and replacing it is always correct. It used to append by default,
which meant running it twice silently doubled the index: 189 entries had
become 873 byte-identical chunks. That is not merely wasteful. Retrieval
reconsiders its top candidates by coverage, and three copies of one document
fill that pool and crowd out the document that actually answers -- "building
permit fees" stopped reaching the Act that sets them because the pool held
three copies each of two visitor pages.
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
                            help='Deprecated: replacing is now the default.')
        parser.add_argument('--append', action='store_true',
                            help='Add to the existing index instead of '
                                 'replacing it. Duplicates whatever is '
                                 'already there; almost never what you want.')
        parser.add_argument('--include-auto', action='store_true',
                            help='Also index AI-generated entries (not municipal record).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would be written, change nothing.')

    def handle(self, *args, **options):
        entries = KnowledgeBase.objects.filter(is_active=True)
        if not options['include_auto']:
            # auto_generated rows are the assistant's own past answers, saved
            # back by the self-learning path. Indexing them lets the assistant
            # cite itself as municipal record, which sections 14 and 37 forbid.
            excluded = entries.filter(auto_generated=True).count()
            entries = entries.filter(auto_generated=False)
            if excluded:
                self.stdout.write(self.style.WARNING(
                    f'Skipping {excluded} AI-generated entries '
                    '(pass --include-auto to index them anyway).'))
        total = entries.count()
        if not total:
            # Returning here left withdrawn content in the index forever. The
            # chunks are derived from KnowledgeBase and nothing else, so an
            # entry the municipality deactivates -- a superseded fee schedule,
            # say -- must stop being served, not linger because the source it
            # came from is now empty.
            self.stdout.write(self.style.WARNING(
                'No active KnowledgeBase entries — run the seed command first.'))
            if not options['append']:
                removed = KnowledgeChunk.objects.all().delete()[0]
                if removed:
                    self.stdout.write(self.style.WARNING(
                        f'Cleared {removed} chunks that no longer have a '
                        'source entry.'))
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
            existing = KnowledgeChunk.objects.count()
            verb = 'added to' if options['append'] else 'replacing'
            self.stdout.write(
                f'{total} active entries would produce {len(planned)} chunks, '
                f'{verb} {existing} already indexed.')
            return

        with transaction.atomic():
            if not options['append']:
                removed = KnowledgeChunk.objects.all().delete()[0]
                if removed:
                    self.stdout.write(f'Replaced {removed} existing chunks.')
            KnowledgeChunk.objects.bulk_create(planned, batch_size=200)

        self.stdout.write(self.style.SUCCESS(
            f'Indexed {total} entries into {len(planned)} chunks.'))
