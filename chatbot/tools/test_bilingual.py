"""Retrieval must work from either language.

The municipal documents are all Devanagari and BILINGUAL was written
Nepali-first, so English questions scored zero against them: "business tax"
could not reach the Act that sets the business tax rate.
"""
from django.test import TestCase

from chatbot.models import KnowledgeChunk
from chatbot.tools.retrieval import BILINGUAL, ENGLISH_TO_NEPALI, coverage, equivalents, search


class ReverseIndexTests(TestCase):
    def test_reverse_index_is_derived_from_the_forward_one(self):
        for nepali, english_terms in BILINGUAL.items():
            for english in english_terms:
                self.assertIn(nepali, ENGLISH_TO_NEPALI[english], english)

    def test_equivalents_work_in_both_directions(self):
        self.assertIn('tax', equivalents('कर'))
        self.assertIn('कर', equivalents('tax'))

    def test_unknown_word_has_no_equivalents(self):
        self.assertEqual(equivalents('zzzzq'), ())

    def test_business_is_not_mapped_to_shop(self):
        """'shop' pulled a shopping guide above the Act setting business tax."""
        self.assertNotIn('shop', BILINGUAL['व्यवसाय'])


class CrossLanguageRetrievalTests(TestCase):
    def setUp(self):
        KnowledgeChunk.objects.create(
            source_type='rules', title='आर्थिक ऐन (कर तथा शुल्क)',
            content='व्यवसाय तथा उद्योग करः भक्तपुर नगरपालिका क्षेत्रभित्र व्यापार, '
                    'व्यवसाय वा उद्योग सेवामा कर लगाइनेछ । बहाल कर र सम्पत्ति कर पनि '
                    'अनुसूची बमोजिम असूल गरिनेछ ।',
            is_active=True)
        KnowledgeChunk.objects.create(
            source_type='general', title='Shopping & Handicrafts',
            content='Bhaktapur shops sell pottery, thangka and handicrafts to visitors.',
            is_active=True)

    def top(self, query):
        hits = search(query, limit=1)
        return hits[0]['title'] if hits else None

    def test_english_question_reaches_the_nepali_act(self):
        self.assertEqual(self.top('How much is the business tax?'),
                         'आर्थिक ऐन (कर तथा शुल्क)')

    def test_nepali_question_still_reaches_the_act(self):
        self.assertEqual(self.top('व्यवसाय कर कति हो?'), 'आर्थिक ऐन (कर तथा शुल्क)')

    def test_english_property_tax_reaches_the_act(self):
        self.assertEqual(self.top('property tax'), 'आर्थिक ऐन (कर तथा शुल्क)')

    def test_english_question_scores_as_a_real_match(self):
        hits = search('business tax', limit=1)
        self.assertGreaterEqual(coverage('business tax', hits[0]), 0.5)

    def test_shopping_query_still_finds_the_shopping_page(self):
        self.assertEqual(self.top('where can I go shopping for handicrafts'),
                         'Shopping & Handicrafts')


class ScriptFramingTests(TestCase):
    """An English asker should be told the answer is quoted Nepali."""

    def setUp(self):
        KnowledgeChunk.objects.create(
            source_type='rules', title='आर्थिक ऐन',
            content='व्यवसाय कर अनुसूची बमोजिम असूल गरिनेछ । बहाल कर पनि लाग्नेछ ।',
            is_active=True)

    def _ask(self, query):
        from django.test import RequestFactory

        from chatbot.tools import run_tool

        class Anon:
            is_authenticated = False; is_staff = False; pk = None; role = None
        req = RequestFactory().post('/chat/')
        req.user = Anon()
        return run_tool('search_municipal_knowledge', req, query=query)

    def test_english_question_is_flagged(self):
        data = self._ask('business tax').data
        self.assertTrue(data['answer_in_devanagari'])
        self.assertFalse(data['asked_in_devanagari'])

    def test_nepali_question_is_not_flagged(self):
        data = self._ask('व्यवसाय कर').data
        self.assertTrue(data['asked_in_devanagari'])

    def test_note_shown_only_to_the_english_asker(self):
        from chatbot.tools.present import present
        english, _ = present('search_municipal_knowledge', self._ask('business tax'))
        nepali, _ = present('search_municipal_knowledge', self._ask('व्यवसाय कर'))
        self.assertIn('official Nepali-language records', english)
        self.assertNotIn('official Nepali-language records', nepali)


class MapPlaceExtractionTests(TestCase):
    """A map lookup needs a place; without one it is not a map question."""

    def test_place_is_extracted(self):
        from chatbot.tools.router import _place_from
        self.assertEqual(_place_from('where is nyatapola temple'), 'nyatapola temple')
        self.assertEqual(_place_from('directions to pottery square'), 'pottery square')

    def test_trailing_clause_is_trimmed(self):
        """"get to Bhaktapur from Kathmandu" asks about Bhaktapur."""
        from chatbot.tools.router import _place_from
        self.assertEqual(_place_from('how do i get to bhaktapur from kathmandu'), 'bhaktapur')

    def test_question_with_no_place_does_not_route_to_the_map(self):
        from chatbot.tools.router import route
        routed = route('how do i get there')
        self.assertTrue(routed is None or routed[0] != 'find_on_map')

    def test_named_place_still_routes_to_the_map(self):
        from chatbot.tools.router import route
        self.assertEqual(route('where is nyatapola temple')[0], 'find_on_map')


class ScriptFlagPrecisionTests(TestCase):
    """The note must follow the passage the reader actually sees first."""

    def setUp(self):
        KnowledgeChunk.objects.create(
            source_type='emergency', title='Emergency Contacts',
            content='Police: 100, Fire Brigade: 101, Ambulance: 102 in Bhaktapur city.',
            is_active=True)
        KnowledgeChunk.objects.create(
            source_type='emergency', title='आपतकालीन सम्पर्क',
            content='प्रहरी सम्पर्क नम्बर १०० हो । एम्बुलेन्स १०२ ।', is_active=True)

    def test_english_top_hit_is_not_labelled_nepali(self):
        from django.test import RequestFactory

        from chatbot.tools import run_tool

        class Anon:
            is_authenticated = False; is_staff = False; pk = None; role = None
        req = RequestFactory().post('/chat/')
        req.user = Anon()
        data = run_tool('search_municipal_knowledge', req,
                        query='emergency police ambulance contacts').data
        if data['passages'] and 'Emergency Contacts' in data['passages'][0]['title']:
            self.assertFalse(data['answer_in_devanagari'])
