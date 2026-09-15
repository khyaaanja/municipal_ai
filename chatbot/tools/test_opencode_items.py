"""Tests for the OpenCode report items that survived verification.

Temporal event queries and graded retrieval confidence. The report's other
recommendations were either already implemented, based on a field that does
not exist, or deliberately declined.
"""
from datetime import timedelta

from django.test import RequestFactory, TestCase
from django.core.cache import cache
from django.utils import timezone

from chatbot.models import KnowledgeChunk
from chatbot.tools import run_tool
from chatbot.tools.router import route
from events.models import Event


class _Anon:
    is_authenticated = False
    is_staff = False
    pk = None
    role = None


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()

    def request(self):
        req = self.rf.post('/chat/')
        req.user = _Anon()
        return req


class TemporalEventTests(Base):
    def setUp(self):
        super().setUp()
        now = timezone.now()
        self.today = Event.objects.create(
            name='Pottery demonstration', slug='pottery-today',
            description='Today at the square.',
            start_date=now + timedelta(hours=3), is_active=True)
        self.tomorrow = Event.objects.create(
            name='Ward assembly', slug='assembly-tomorrow',
            description='Tomorrow morning.',
            start_date=now + timedelta(days=1, hours=2), is_active=True)
        self.next_month = Event.objects.create(
            name='Bisket Jatra', slug='bisket-far',
            description='Much later.',
            start_date=now + timedelta(days=40), is_active=True)

    def names(self, **kwargs):
        result = run_tool('list_events', self.request(), **kwargs)
        self.assertTrue(result.ok)
        return {row['name'] for row in result.data}

    def test_today_excludes_later_events(self):
        self.assertEqual(self.names(when='today'), {'Pottery demonstration'})

    def test_tomorrow_selects_only_tomorrow(self):
        self.assertEqual(self.names(when='tomorrow'), {'Ward assembly'})

    def test_week_excludes_next_month(self):
        got = self.names(when='week')
        self.assertIn('Pottery demonstration', got)
        self.assertNotIn('Bisket Jatra', got)

    def test_upcoming_is_still_the_default(self):
        self.assertEqual(len(self.names()), 3)

    def test_router_extracts_today(self):
        name, kwargs = route("what's happening today")
        self.assertEqual(name, 'list_events')
        self.assertEqual(kwargs['when'], 'today')

    def test_router_extracts_nepali_today(self):
        name, kwargs = route('आज के events छ')
        self.assertEqual(kwargs['when'], 'today')

    def test_router_defaults_to_upcoming(self):
        _, kwargs = route('what events are there')
        self.assertEqual(kwargs['when'], 'upcoming')


class ConfidenceBandTests(Base):
    def setUp(self):
        super().setUp()
        KnowledgeChunk.objects.create(
            source_type='service', title='Property Tax Payment',
            content='Property tax is paid at the municipality office with '
                    'your ownership document and citizenship certificate. '
                    'Property tax rates depend on the property valuation.',
            is_active=True)

    def band(self, query):
        result = run_tool('search_municipal_knowledge', self.request(), query=query)
        self.assertTrue(result.ok)
        return result.data['confidence']

    def test_strong_match_is_not_low(self):
        self.assertIn(self.band('property tax payment document'), ('high', 'medium'))

    def test_no_match_reports_none(self):
        self.assertEqual(self.band('zzzzqqqq'), 'none')

    def test_no_match_still_reports_not_found(self):
        result = run_tool('search_municipal_knowledge', self.request(), query='zzzzqqqq')
        self.assertFalse(result.data['found'])

    def test_confidence_present_on_every_response(self):
        for q in ('tax', 'zzzz', 'citizenship certificate'):
            result = run_tool('search_municipal_knowledge', self.request(), query=q)
            self.assertIn(result.data['confidence'], ('high', 'medium', 'low', 'none'))


class NepaliScriptRoutingTests(Base):
    """Devanagari phrasing must route, not just romanised Nepali."""

    def test_notices_in_devanagari(self):
        self.assertEqual(route('सूचना हेर्न चाहन्छु')[0], 'list_public_notices')

    def test_own_complaints_in_devanagari(self):
        self.assertEqual(route('मेरो गुनासो')[0], 'get_my_complaints')

    def test_attractions_in_devanagari(self):
        self.assertEqual(route('मन्दिर घुम्न')[0], 'find_attractions')

    def test_businesses_in_devanagari(self):
        self.assertEqual(route('रेस्टुरेन्ट खोज्दै')[0], 'find_businesses')

    def test_events_in_devanagari(self):
        self.assertEqual(route('कार्यक्रम के छ')[0], 'list_events')

    def test_devanagari_possessive_still_gates_private_tools(self):
        """A bare topic word must not reach a per-citizen tool."""
        self.assertIsNone(route('गुनासो कसरी दर्ता गर्ने'))
