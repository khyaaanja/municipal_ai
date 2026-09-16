"""Seed contact and office-holder facts published by the municipality.

These are the questions the assistant was falling through to the model on —
"municipality phone number", "who is the mayor" — where a generated answer
would be a plausible-looking invention about a real public office.

Every value here was read from bhaktapurmun.gov.np. Nothing is inferred. If
a value cannot be found on the site it does not belong in this file: the
assistant declining is better than the assistant guessing who holds office.
"""
from django.core.management.base import BaseCommand

SOURCE = 'https://bhaktapurmun.gov.np'

ENTRIES = [
    {
        'title': 'Bhaktapur Municipality — contact',
        'category': 'general',
        'language': 'en',
        'content': (
            'Bhaktapur Municipality office contact.\n\n'
            'Phone: 977-01-6613957\n'
            'Phone: 977-01-6610096\n'
            'Email: info@bhaktapurmun.gov.np\n'
            'Website: https://bhaktapurmun.gov.np\n\n'
            'For emergencies use the national numbers instead: '
            'Police 100, Fire Brigade 101, Ambulance 102.'
        ),
    },
    {
        'title': 'भक्तपुर नगरपालिका — सम्पर्क',
        'category': 'general',
        'language': 'ne',
        'content': (
            'भक्तपुर नगरपालिका कार्यालयको सम्पर्क।\n\n'
            'फोन: 977-01-6613957\n'
            'फोन: 977-01-6610096\n'
            'इमेल: info@bhaktapurmun.gov.np\n'
            'वेबसाइट: https://bhaktapurmun.gov.np\n\n'
            'आपतकालीन अवस्थामा: प्रहरी १००, दमकल १०१, एम्बुलेन्स १०२।'
        ),
    },
    {
        'title': 'Bhaktapur Municipality — elected officials',
        'category': 'general',
        'language': 'en',
        'content': (
            'Elected office holders of Bhaktapur Municipality, as published '
            'by the municipality.\n\n'
            'Mayor: Sunil Prajapati — 9851078885\n'
            'Deputy Mayor: Rajani Joshi — 9851177744\n\n'
            'Ward-level matters are handled by the ward chairperson for your '
            'ward. The municipality also has a Chief Administrative Officer '
            'and a designated Information Officer.'
        ),
    },
    {
        'title': 'भक्तपुर नगरपालिका — निर्वाचित पदाधिकारी',
        'category': 'general',
        'language': 'ne',
        'content': (
            'भक्तपुर नगरपालिकाका निर्वाचित पदाधिकारीहरू।\n\n'
            'नगर प्रमुख (मेयर): सुनिल प्रजापति — 9851078885\n'
            'उप-प्रमुख: रजनी जोशी — 9851177744\n\n'
            'वडास्तरका विषयमा सम्बन्धित वडाअध्यक्षलाई सम्पर्क गर्नुहोस्।'
        ),
    },
]


class Command(BaseCommand):
    help = 'Seed municipality contact and office-holder facts from the official site.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        from chatbot.models import KnowledgeBase

        created = updated = 0
        for entry in ENTRIES:
            if options['dry_run']:
                self.stdout.write(f"  {entry['title']}")
                continue
            _, was_created = KnowledgeBase.objects.update_or_create(
                title=entry['title'],
                defaults={
                    'content': f"{entry['content']}\n\nSource: {SOURCE}",
                    'category': entry['category'],
                    'language': entry['language'],
                    'is_active': True,
                    # Published by the municipality, not written by the
                    # assistant, so it belongs in the retrievable corpus.
                    'auto_generated': False,
                    'source_query': SOURCE,
                },
            )
            created += was_created
            updated += not was_created

        verb = 'would seed' if options['dry_run'] else 'seeded'
        self.stdout.write(self.style.SUCCESS(
            f'{verb} {len(ENTRIES)} entries ({created} new, {updated} refreshed)'))
