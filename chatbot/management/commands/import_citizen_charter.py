"""Import the municipality's citizen charter / fee schedule PDFs.

These documents are the authoritative answer to the questions citizens
actually ask — which documents a service needs, what it costs, how long it
takes, which officer handles it. They are published as Preeti-encoded PDFs,
so they extract as ASCII gibberish and have been unusable until now.

Deliberately not parsed into structured fee fields. PDF extraction
interleaves the table columns, so pairing a fee with a service name would
sometimes pair it with the wrong one — and a confidently wrong fee is worse
for a citizen than no answer. Passages are stored as published, attributed
to the source document and its fiscal year, and left for retrieval to find.
"""
import re
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from chatbot.services.preeti import convert, looks_like_preeti, validate

TARGET_CHARS = 700
MIN_CHARS = 120


def extract_pdf_text(path):
    try:
        import pypdf
    except ImportError:
        raise RuntimeError('pypdf is required: pip install pypdf')
    reader = pypdf.PdfReader(str(path))
    return '\n'.join((page.extract_text() or '') for page in reader.pages)


def to_unicode(raw):
    """Convert if the text is Preeti; validate before trusting the result."""
    if not looks_like_preeti(raw):
        return raw, True, {}
    converted = convert(raw)
    hits, ok = validate(converted)
    return converted, ok, hits


def passages(text, target=TARGET_CHARS):
    text = re.sub(r'[ \t]+', ' ', text)
    blocks, current = [], []
    for line in (l.strip() for l in text.split('\n')):
        if not line:
            continue
        current.append(line)
        if sum(len(x) for x in current) >= target:
            blocks.append(' '.join(current))
            current = []
    if current:
        tail = ' '.join(current)
        if blocks and len(tail) < MIN_CHARS:
            blocks[-1] += ' ' + tail
        else:
            blocks.append(tail)
    return blocks


class Command(BaseCommand):
    help = 'Import a citizen-charter or fee-schedule PDF into the knowledge base.'

    def add_arguments(self, parser):
        parser.add_argument('pdf', help='Path to the downloaded PDF.')
        parser.add_argument('--title', required=True,
                            help='Human title, e.g. "नागरिक वडापत्र".')
        parser.add_argument('--fiscal-year', required=True,
                            help='Fiscal year the document covers, e.g. "2076/077".')
        parser.add_argument('--source-url', default='', help='Official source URL.')
        parser.add_argument('--category', default='services')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        from chatbot.models import KnowledgeBase

        path = Path(options['pdf'])
        if not path.exists():
            self.stdout.write(self.style.ERROR(f'No such file: {path}'))
            return

        raw = extract_pdf_text(path)
        if not raw.strip():
            self.stdout.write(self.style.ERROR(
                'No text layer — this PDF is a scan and needs OCR, not this command.'))
            return

        text, ok, hits = to_unicode(raw)
        if not ok:
            self.stdout.write(self.style.ERROR(
                f'Conversion failed validation (only {len(hits)} known terms found). '
                'Refusing to import, rather than store text that may be wrong.'))
            return
        if hits:
            self.stdout.write(f'Conversion validated: {len(hits)} municipal terms recognised.')

        year = options['fiscal_year']
        blocks = [b for b in passages(text) if len(b) >= MIN_CHARS]
        self.stdout.write(f'{len(blocks)} passages from {path.name}')

        if options['dry_run']:
            for b in blocks[:3]:
                self.stdout.write('  ' + b[:130])
            return

        created = 0
        with transaction.atomic():
            for i, block in enumerate(blocks, 1):
                title = f"{options['title']} ({year}) — {i}"
                # The fiscal year rides with the content, so a retrieved
                # passage can never be read as this year's fee schedule.
                body = f"[{options['title']} · आर्थिक वर्ष {year}]\n\n{block}"
                if options['source_url']:
                    body += f"\n\nSource: {options['source_url']}"
                _, was_created = KnowledgeBase.objects.update_or_create(
                    title=title[:200],
                    defaults={
                        'content': body,
                        'category': options['category'],
                        'language': 'ne',
                        'is_active': True,
                        'auto_generated': False,
                        'source_query': options['source_url'][:500],
                    },
                )
                created += was_created

        self.stdout.write(self.style.SUCCESS(
            f'Imported {created} new passages ({len(blocks) - created} refreshed).'))
