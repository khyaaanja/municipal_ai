from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from events.models import Event


def make_event(name='Bisket Jatra', **kw):
    defaults = dict(
        slug=name.lower().replace(' ', '-'),
        description='A great festival.',
        category='festival',
        venue='Taumadhi Square',
        start_date=timezone.now() + timedelta(days=7),
        is_active=True,
        is_free=True,
    )
    defaults.update(kw)
    return Event.objects.create(name=name, **defaults)


class EventListTests(TestCase):
    def setUp(self):
        self.e1 = make_event('Bisket Jatra')
        self.e2 = make_event('Indra Jatra', slug='indra-jatra')

    def test_list_loads(self):
        r = self.client.get('/events/')
        self.assertEqual(r.status_code, 200)

    def test_list_shows_events(self):
        r = self.client.get('/events/')
        self.assertContains(r, 'Bisket Jatra')

    def test_inactive_event_hidden(self):
        make_event('Hidden Event', slug='hidden-event', is_active=False)
        r = self.client.get('/events/')
        self.assertNotContains(r, 'Hidden Event')


class EventDetailTests(TestCase):
    def setUp(self):
        self.e = make_event('Gai Jatra', slug='gai-jatra')

    def test_detail_loads(self):
        r = self.client.get('/events/gai-jatra/')
        self.assertEqual(r.status_code, 200)

    def test_detail_contains_name(self):
        r = self.client.get('/events/gai-jatra/')
        self.assertContains(r, 'Gai Jatra')

    def test_404_on_missing(self):
        r = self.client.get('/events/no-such-event/')
        self.assertEqual(r.status_code, 404)
