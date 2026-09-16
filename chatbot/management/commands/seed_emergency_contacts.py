"""Seed emergency numbers, each one carrying the source it came from.

The existing Emergency Contacts entries listed +977-1-4247041 as "Tourist
Police Bhaktapur". The Nepal Tourism Board publishes no such number:
Bhaktapur is 9851289448, Nagarkot is 9851289447, and there is a national
toll-free line, 1144, that none of the entries mentioned at all.

This is the content a visitor reaches on the worst day of their trip, so
every number here is attributed inline. A number whose owner could not be
found publishing it is not listed -- the national 100/101/102 lines always
work, and sending someone to a wrong number in an emergency is worse than
sending them to a short list that is right.
"""
from django.core.management.base import BaseCommand

from core import contacts

NTB = 'https://ntb.gov.np/en/plan-your-trip/before-you-come/tourist-police'
HOSPITAL = 'https://bhaktapurhospital.gov.np'

ENTRIES = [
    {
        'title': 'Emergency Contacts — Bhaktapur',
        'category': 'emergency',
        'language': 'en',
        'content': (
            'Dial these free from any phone, anywhere in Nepal:\n'
            f'Police {contacts.POLICE}\n'
            f'Fire Brigade {contacts.FIRE}\n'
            f'Ambulance {contacts.AMBULANCE}\n'
            'Traffic Police 103\n'
            'Tourist Police, toll free 1144\n\n'
            'Tourist Police posts near Bhaktapur:\n'
            'Bhaktapur 9851289448\n'
            'Nagarkot 9851289447\n'
            f'Source: Nepal Tourism Board, {NTB}\n\n'
            'Bhaktapur Hospital, Dudhpati — open 24 hours:\n'
            '01-6610798, 01-6610676\n'
            f'Source: {HOSPITAL}\n\n'
            'Bhaktapur Municipality office — office hours only, '
            'not an emergency line:\n'
            f'{contacts.PHONES}\n'
            f'Source: {contacts.SOURCE}'
        ),
    },
    {
        'title': 'आपतकालीन सम्पर्क नम्बर',
        'category': 'emergency',
        'language': 'ne',
        'content': (
            'नेपालभरि कुनै पनि फोनबाट निःशुल्क:\n'
            'प्रहरी १००\n'
            'दमकल १०१\n'
            'एम्बुलेन्स १०२\n'
            'ट्राफिक प्रहरी १०३\n'
            'पर्यटक प्रहरी (निःशुल्क) ११४४\n\n'
            'भक्तपुर नजिकका पर्यटक प्रहरी चौकी:\n'
            'भक्तपुर 9851289448\n'
            'नगरकोट 9851289447\n'
            f'स्रोत: नेपाल पर्यटन बोर्ड, {NTB}\n\n'
            'भक्तपुर अस्पताल, दुधपाटी — २४ घण्टा खुला:\n'
            '01-6610798, 01-6610676\n'
            f'स्रोत: {HOSPITAL}\n\n'
            'भक्तपुर नगरपालिका कार्यालय — कार्यालय समयमा मात्र, '
            'आपतकालीन लाइन होइन:\n'
            f'{contacts.PHONES_NE}\n'
            f'स्रोत: {contacts.SOURCE}'
        ),
    },
]


class Command(BaseCommand):
    help = 'Seed sourced emergency contact numbers.'

    def handle(self, *args, **options):
        from chatbot.models import KnowledgeBase

        for entry in ENTRIES:
            obj, created = KnowledgeBase.objects.update_or_create(
                title=entry['title'],
                defaults={
                    'category': entry['category'],
                    'content': entry['content'],
                    'language': entry['language'],
                    'is_active': True,
                },
            )
            verb = 'created' if created else 'updated'
            self.stdout.write(f'  {verb}: {obj.title}')
        self.stdout.write(self.style.SUCCESS('emergency contacts seeded'))
