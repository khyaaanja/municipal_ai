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


class NepaliStemmingTests(TestCase):
    """Nepali attaches case endings to the noun.

    "नगरपालिकाको" and "नगरपालिका" are one word to a reader and two strings to
    a matcher, so a question using one form could not reach a document using
    the other.
    """

    def test_inflected_and_bare_forms_agree(self):
        """Both spellings must land on the same token.

        This once asserted that "नगरपालिकाको" became "नगरपालिका", which the
        bare "नगरपालिका" never did -- it lost "का" and became "नगरपालि". The
        two forms stemmed to different strings, so the match this class
        exists to guarantee did not happen. What matters is that the forms
        agree, not which string they agree on.
        """
        from chatbot.tools.retrieval import tokenize
        for inflected, bare in [
            ('नगरपालिकाको', 'नगरपालिका'),
            ('सिफारिसलाई', 'सिफारिस'),
            ('पानीको', 'पानी'),
            ('करहरूको', 'कर'),
        ]:
            self.assertEqual(
                tokenize(inflected), tokenize(bare),
                f'{inflected} and {bare} must match each other',
            )

    def test_stemming_is_idempotent(self):
        """Stemming an already-stemmed token must change nothing."""
        from chatbot.tools.retrieval import tokenize
        for word in ['नगरपालिकाको', 'करहरूको', 'restaurants', 'eating']:
            once = tokenize(word)
            self.assertEqual(tokenize(' '.join(once)), once)

    def test_plural_ending_is_trimmed_whole(self):
        """हरूको must not be left as हरू."""
        from chatbot.tools.retrieval import tokenize
        self.assertEqual(tokenize('वडाहरूको'), ['वडा'])

    def test_two_letter_stems_survive(self):
        """कर is a real two-codepoint word; a longer minimum lost it."""
        from chatbot.tools.retrieval import tokenize
        self.assertEqual(tokenize('करको'), ['कर'])

    def test_short_words_are_not_destroyed(self):
        from chatbot.tools.retrieval import tokenize
        self.assertEqual(tokenize('को'), ['को'])
        self.assertEqual(tokenize('मा'), ['मा'])

    def test_english_is_untouched(self):
        from chatbot.tools.retrieval import tokenize
        self.assertEqual(tokenize('business tax rate'), ['business', 'tax', 'rate'])


class OfficialContactSeedTests(TestCase):
    """Facts read from the municipality's own site, never inferred."""

    def setUp(self):
        from django.core.management import call_command
        from io import StringIO
        call_command('seed_official_contacts', stdout=StringIO())

    def test_contact_and_officials_are_curated_not_generated(self):
        from chatbot.models import KnowledgeBase
        seeded = KnowledgeBase.objects.filter(source_query__icontains='bhaktapurmun')
        self.assertGreaterEqual(seeded.count(), 4)
        self.assertFalse(seeded.filter(auto_generated=True).exists())

    def test_every_seeded_entry_cites_its_source(self):
        from chatbot.models import KnowledgeBase
        for entry in KnowledgeBase.objects.filter(source_query__icontains='bhaktapurmun'):
            self.assertIn('bhaktapurmun.gov.np', entry.content)

    def test_seeding_twice_does_not_duplicate(self):
        from django.core.management import call_command
        from io import StringIO

        from chatbot.models import KnowledgeBase
        before = KnowledgeBase.objects.count()
        call_command('seed_official_contacts', stdout=StringIO())
        self.assertEqual(KnowledgeBase.objects.count(), before)


class EnglishStemmingTests(TestCase):
    """English inflections hid content that was already indexed.

    "where can I eat" returned nothing at all against a chunk reading
    "Best restaurants near Durbar Square. Avoid eating near temples",
    because "eat" is not "eating" and "restaurant" is not "restaurants".
    """

    def test_inflected_and_bare_forms_agree(self):
        from chatbot.tools.retrieval import tokenize
        for inflected, bare in [
            ('restaurants', 'restaurant'),
            ('fees', 'fee'),
            ('temples', 'temple'),
            ('eating', 'eat'),
            ('taxes', 'tax'),
        ]:
            self.assertEqual(tokenize(inflected), tokenize(bare))

    def test_short_words_are_not_destroyed(self):
        """"bus" must not become "bu"."""
        from chatbot.tools.retrieval import tokenize
        self.assertEqual(tokenize('bus'), ['bus'])

    def test_double_s_is_not_a_plural(self):
        from chatbot.tools.retrieval import tokenize
        self.assertEqual(tokenize('address'), ['address'])


class CoverageRerankTests(TestCase):
    """BM25 weight is not the same as answering the question.

    A hotel listing that repeats one common word many times outranked the Act
    that actually sets the building-permit fee. Reconsidering the strongest
    candidates by how much of the question each addresses put the Act back on
    top.
    """

    CHUNKS = [
        {
            'id': 1,
            'title': 'Accommodation in Bhaktapur',
            'content': 'Guest houses and home stays. Houses near the square. '
                       'Home stay hosts. Guest house rooms. Houses.',
            'source_type': 'tourism',
        },
        {
            'id': 2,
            'title': 'Building permit fee schedule',
            'content': 'House map approval and building permit fees are set '
                       'by the Act.',
            'source_type': 'municipal',
        },
    ]

    def test_document_that_answers_outranks_the_one_that_repeats(self):
        from chatbot.tools.retrieval import search
        hits = search('building permit fees for a house map',
                      limit=2, chunks=self.CHUNKS)
        self.assertEqual(hits[0]['title'], 'Building permit fee schedule')

    def test_reranking_does_not_invent_a_match(self):
        """A query sharing nothing with either chunk still returns nothing."""
        from chatbot.tools.retrieval import search
        self.assertEqual(search('zzzz', limit=2, chunks=self.CHUNKS), [])


class ScriptPreferenceTests(TestCase):
    """Answer in the script the question was asked in, where there is a choice.

    "tourist police" returned the Nepali entry to an English speaker. That
    entry cites its source -- ntb.gov.np/.../tourist-police -- and a URL
    tokenises into English words, so it matched an English query as well as
    the English entry did and won the tie.
    """

    CHUNKS = [
        {
            'id': 1,
            'title': 'आपतकालीन सम्पर्क नम्बर',
            'content': 'पर्यटक प्रहरी ११४४। स्रोत: '
                       'https://ntb.gov.np/en/plan-your-trip/tourist-police',
            'source_type': 'municipal',
        },
        {
            'id': 2,
            'title': 'Emergency Contacts',
            'content': 'Tourist Police, toll free 1144. Source: '
                       'https://ntb.gov.np/en/plan-your-trip/tourist-police',
            'source_type': 'municipal',
        },
    ]

    def test_english_question_prefers_english_content(self):
        from chatbot.tools.retrieval import search
        hits = search('tourist police', limit=2, chunks=self.CHUNKS)
        self.assertEqual(hits[0]['title'], 'Emergency Contacts')

    def test_nepali_question_prefers_nepali_content(self):
        from chatbot.tools.retrieval import search
        hits = search('पर्यटक प्रहरी', limit=2, chunks=self.CHUNKS)
        self.assertEqual(hits[0]['title'], 'आपतकालीन सम्पर्क नम्बर')

    def test_script_only_breaks_ties(self):
        """Content in the other script must still be reachable.

        A citizen asking in Nepali about something documented only in
        English has to be able to find it; preference is not a filter.
        """
        from chatbot.tools.retrieval import search
        english_only = [self.CHUNKS[1]]
        hits = search('पर्यटक प्रहरी tourist police',
                      limit=2, chunks=english_only)
        self.assertEqual(len(hits), 1)

    def test_source_url_does_not_make_a_nepali_entry_english(self):
        from chatbot.tools.retrieval import _is_devanagari
        self.assertTrue(_is_devanagari(self.CHUNKS[0]['content']))
        self.assertFalse(_is_devanagari(self.CHUNKS[1]['content']))


class NepaliToNepaliSynonymTests(TestCase):
    """Two Nepali words for one thing must meet.

    The expansion map only ever crossed languages, so a citizen and the
    citizen charter could name the same service differently and never match.
    The charter documents a water connection as "धारा/विद्ुत जडान सिफारिस";
    a resident asks "पानीको धारा कसरी जोड्ने". One word of three was shared,
    which scored below the gate -- so a procedure that is written down, with
    its documents and its fee, was reported as something the municipality
    had no answer for.
    """

    CHUNKS = [
        {
            'id': 1,
            'title': 'नागरिक वडापत्र — ५',
            'content': 'ड धारा/विद्ुत जडान सिफारिस क_ निवेदन '
                       'ख_ जग्गाधनी प्रमाण पूर्जा ग_ चालु आ.ब.को मालपोत तिरेको',
            'source_type': 'procedure',
        },
        {
            'id': 2,
            'title': 'आर्थिक ऐन — कर',
            'content': 'व्यवसाय कर र सम्पत्ति कर को दर तोकिएको छ।',
            'source_type': 'procedure',
        },
    ]

    def test_the_charter_is_reachable_from_a_resident_wording(self):
        from chatbot.tools.retrieval import search, coverage
        hits = search('पानीको धारा कसरी जोड्ने', limit=2, chunks=self.CHUNKS)
        self.assertEqual(hits[0]['title'], 'नागरिक वडापत्र — ५')
        self.assertGreaterEqual(
            coverage('पानीको धारा कसरी जोड्ने', hits[0]), 0.35)

    def test_a_tax_question_still_reaches_the_act(self):
        """"धारा" also means a legal article; the water sense must not win."""
        from chatbot.tools.retrieval import search
        hits = search('व्यवसाय कर कति हो', limit=2, chunks=self.CHUNKS)
        self.assertEqual(hits[0]['title'], 'आर्थिक ऐन — कर')


class SocialProtectionReachabilityTests(TestCase):
    """Two services the municipality delivers were recorded as gaps.

    The charter distributes the identity card that entitles someone to the
    social security allowance, and covers the disability card. Neither was
    reachable from English, so a citizen asking in English was told the
    municipality had no answer.

    The scanned charter came through Preeti conversion spelling these
    "ज्येषठ" and "अपांगता", and a term nobody spells that way is a term
    nobody reaches.
    """

    CHUNKS = [
        {
            'id': 1,
            'title': 'नागरिक वडापत्र — २७',
            'content': 'सामाजिक सुरक्षा भत्ता पाउन परिचय पत्र वितरण। '
                       'ज्येषठ नागरिकको लागि निवेदन र नागरिकता।',
            'source_type': 'procedure',
        },
        {
            'id': 2,
            'title': 'नागरिक वडापत्र — २८',
            'content': 'अपांगता कार्डको फोटोकपी, फोटो-२ प्रति, '
                       'जन्म दर्ता प्रमाण पत्र।',
            'source_type': 'procedure',
        },
    ]

    def test_english_reaches_the_allowance_procedure(self):
        from chatbot.tools.retrieval import search
        hits = search('senior citizen allowance', limit=2, chunks=self.CHUNKS)
        self.assertEqual(hits[0]['title'], 'नागरिक वडापत्र — २७')

    def test_english_reaches_the_disability_procedure(self):
        from chatbot.tools.retrieval import search
        hits = search('disability card', limit=2, chunks=self.CHUNKS)
        self.assertEqual(hits[0]['title'], 'नागरिक वडापत्र — २८')

    def test_the_converted_spellings_are_mapped(self):
        """A term the document spells oddly still has to be findable."""
        from chatbot.tools.retrieval import equivalents, _stem
        self.assertIn('senior', equivalents(_stem('ज्येषठ')))
        self.assertIn('disability', equivalents(_stem('अपांगता')))


class PreetiConjunctRepairTests(TestCase):
    """The scanned documents lost conjuncts, and took whole words with them.

    A halant followed by a vowel sign is not valid Devanagari -- the
    consonant between them was dropped. The corpus was full of it:
    "उद्योग" (industry) appeared 33 times and never once spelled correctly,
    "विद्यालय" (school) 10 times, never correctly. The bilingual map's entry
    for विद्यालय had therefore never matched anything at all.
    """

    def test_dropped_ya_is_restored(self):
        from chatbot.services.preeti import repair_conjuncts
        self.assertEqual(repair_conjuncts('उद्ोग'), 'उद्योग')
        self.assertEqual(repair_conjuncts('विद्ालय'), 'विद्यालय')
        self.assertEqual(repair_conjuncts('विद्ुतीय'), 'विद्युतीय')

    def test_jha_is_restored(self):
        """झ lands as भ + halant before a vowel."""
        from chatbot.services.preeti import repair_conjuncts
        self.assertEqual(repair_conjuncts('सम्भ्ौता'), 'सम्झौता')
        self.assertEqual(repair_conjuncts('बुभ्ाउनु'), 'बुझाउनु')

    def test_ordinary_nepali_is_untouched(self):
        """भ् before a consonant is a real cluster: अभ्यास."""
        from chatbot.services.preeti import repair_conjuncts
        for word in ['अभ्यास', 'व्यवसाय', 'सम्पत्ति', 'नागरिकता',
                     'विद्यालय', 'ज्येष्ठ', 'कर']:
            self.assertEqual(repair_conjuncts(word), word, word)

    def test_both_spellings_reach_the_same_token(self):
        """The point of repairing inside the matcher."""
        from chatbot.tools.retrieval import tokenize
        self.assertEqual(tokenize('उद्ोग'), tokenize('उद्योग'))
        self.assertEqual(tokenize('विद्ालय'), tokenize('विद्यालय'))

    def test_the_converter_emits_valid_devanagari(self):
        """Conversion output must not contain an orphaned halant."""
        import re
        from chatbot.services.preeti import convert
        broken = re.compile('[\u0915-\u0939]\u094D[\u093E-\u094C]')
        self.assertIsNone(broken.search(convert('ljBfno')))
