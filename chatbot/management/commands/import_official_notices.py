"""Import public notices from the official Bhaktapur Municipality site.

The assistant's knowledge problem is not retrieval, it is content: almost
nothing in the knowledge base came from the municipality. Notices are the
exception worth importing automatically — they are published as Unicode
Devanagari in HTML (not the scanned or Preeti-encoded PDFs the rest of the
site uses), they carry a date, and they are authoritative by definition.

Every row records where it came from, so nothing here can later be mistaken
for content the municipality entered into this application directly.
"""
import re
import html as html_lib

from django.core.management.base import BaseCommand
from django.db import transaction

SOURCE = 'https://bhaktapurmun.gov.np'
LISTING = f'{SOURCE}/ne/news-notices'
TIMEOUT = 60

# Keyword -> PublicNotice.notice_type. Nepali first: the site publishes in
# Nepali and the English pages lag behind.
TYPE_RULES = (
    ('TENDER', ('बोलपत्र', 'खरिद', 'ठेक्का', 'e-bidding', 'tender')),
    ('JOB', ('जनशक्ति', 'करार', 'पदपूर्ति', 'दरखास्त', 'अन्तर्वार्ता', 'vacancy')),
    ('REGULATION', ('ऐन', 'नियमावली', 'निर्देशिका', 'कार्यविधि')),
)

ROW = re.compile(
    r'class="[^"]*views-row[^"]*"[^>]*>(.*?)</div>\s*</div>', re.S | re.I)
LINK = re.compile(r'<a[^>]+href="(/ne/content/[^"]+)"[^>]*>(.*?)</a>', re.S | re.I)


def classify(title):
    lowered = title.lower()
    for notice_type, words in TYPE_RULES:
        if any(w.lower() in lowered for w in words):
            return notice_type
    return 'NOTICE'


def strip_tags(fragment):
    return html_lib.unescape(re.sub(r'<[^>]+>', ' ', fragment))


def parse(page_html):
    """Yield (title, url) for each notice row, newest first, de-duplicated."""
    seen = set()
    for block in ROW.findall(page_html):
        match = LINK.search(block)
        if not match:
            continue
        href, raw_title = match.groups()
        title = ' '.join(strip_tags(raw_title).split())
        if not title or len(title) < 8 or href in seen:
            continue
        seen.add(href)
        yield title, SOURCE + href


class Command(BaseCommand):
    help = 'Import public notices from the official municipality website.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=40)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        import requests
        from services.models import PublicNotice

        try:
            resp = requests.get(LISTING, timeout=TIMEOUT,
                                headers={'User-Agent': 'BhaktapurAI municipal assistant'})
            resp.raise_for_status()
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'Could not reach {LISTING}: {exc}'))
            return

        rows = list(parse(resp.text))[:options['limit']]
        if not rows:
            self.stdout.write(self.style.WARNING('No notices found — site layout may have changed.'))
            return

        if options['dry_run']:
            for title, url in rows:
                self.stdout.write(f'  [{classify(title):10}] {title[:70]}')
            self.stdout.write(f'{len(rows)} notices would be imported.')
            return

        created = updated = 0
        with transaction.atomic():
            for title, url in rows:
                obj, was_created = PublicNotice.objects.update_or_create(
                    reference_no=url[-90:],
                    defaults={
                        'title': title[:200],
                        'notice_type': classify(title),
                        'body': f'{title}\n\nSource: {url}',
                        'is_active': True,
                    },
                )
                created += was_created
                updated += not was_created

        self.stdout.write(self.style.SUCCESS(
            f'Imported {created} new, refreshed {updated} existing notices.'))
