"""Reporting a problem in Devanagari, and asking about one.

The civic keyword map held English and romanised Nepali but no Devanagari,
so a resident writing in the script the municipality itself publishes in
could not open a complaint by describing the problem. The reverse mistake
also mattered: a category word inside a question is a question, and
answering it with a complaint form is not an answer.
"""
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.test import RequestFactory, TestCase

from chatbot.tools.flow import detect_category, handle, _is_a_question


class Anon:
    is_authenticated = False
    is_staff = False
    pk = None
    role = None


class DevanagariCategoryTests(TestCase):
    def test_each_category_is_detectable_in_devanagari(self):
        cases = {
            'सडकमा खाल्डो छ': 'ROAD',
            'फोहोर उठाएको छैन': 'SANITATION',
            'पानी आएन': 'WATER',
            'बत्ती बलेको छैन': 'ELECTRICITY',
            'ढल जाम भयो': 'INFRASTRUCTURE',
            'हल्ला धेरै छ': 'NOISE',
        }
        for text, expected in cases.items():
            self.assertEqual(detect_category(text.lower()), expected, text)

    def test_english_and_romanised_still_work(self):
        self.assertEqual(detect_category('there is a pothole'), 'ROAD')
        self.assertEqual(detect_category('garbage everywhere'), 'SANITATION')


class QuestionVersusReportTests(TestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()

    def ask(self, message):
        req = self.rf.post('/chat/')
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        req.user = Anon()
        result = handle(req, message)
        return 'model' if result is None else result[2]

    def test_devanagari_report_opens_a_complaint(self):
        for text in ['सडकमा खाल्डो छ', 'फोहोर उठाएको छैन', 'पानी आएन']:
            self.assertEqual(self.ask(text), 'complaint_filing', text)

    def test_devanagari_question_does_not_open_a_complaint(self):
        """कहिले means "when" — that is a question about the service."""
        for text in ['फोहोर कहिले उठाउँछ', 'पानी कहिले आउँछ']:
            self.assertNotEqual(self.ask(text), 'complaint_filing', text)

    def test_english_question_does_not_open_a_complaint(self):
        self.assertNotEqual(self.ask('when is garbage collected'), 'complaint_filing')

    def test_english_report_still_opens_a_complaint(self):
        self.assertEqual(self.ask('there is garbage piled up on my street'),
                         'complaint_filing')

    def test_explicit_report_verb_beats_the_question_form(self):
        """"How do I report a pothole" is still someone wanting to report."""
        self.assertEqual(self.ask('how do I report a pothole'), 'complaint_filing')


class QuestionDetectionTests(TestCase):
    def test_devanagari_question_words_are_matched(self):
        self.assertTrue(_is_a_question('फोहोर कहिले उठाउँछ'))
        self.assertTrue(_is_a_question('कसरी दर्ता गर्ने'))

    def test_a_statement_is_not_a_question(self):
        self.assertFalse(_is_a_question('सडकमा खाल्डो छ'))
        self.assertFalse(_is_a_question('there is garbage on my street'))


class NepaliParityTests(TestCase):
    """A resident writing in Nepali must get the same service, in Nepali.

    Reporting a broken street light in Devanagari went wrong at every step:
    it was filed under the wrong category, the whole conversation came back
    in English, the description was refused as too short, and confirming it
    with "हो" threw the draft away.
    """

    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()

    def _session_request(self):
        req = self.rf.post('/chat/')
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        req.user = Anon()
        return req

    def say(self, req, message):
        result = handle(req, message)
        return result[0] if result else None

    def test_street_light_is_electricity_in_both_languages(self):
        """"सडक बत्ती" is a street light, not a road.

        "सडक" (road) and "बत्ती" (light) both match; the longer keyword is
        the more specific claim, so ELECTRICITY wins.
        """
        self.assertEqual(detect_category('सडक बत्ती बिग्रियो'), 'ELECTRICITY')
        self.assertEqual(detect_category('my street light is broken'),
                         'ELECTRICITY')
        # The plain road cases must not have moved.
        self.assertEqual(detect_category('सडकमा खाल्डो छ'), 'ROAD')

    def test_a_nepali_report_is_answered_in_nepali(self):
        from chatbot.tools.retrieval import _is_devanagari
        req = self._session_request()
        reply = self.say(req, 'सडक बत्ती बिग्रियो')
        self.assertIsNotNone(reply)
        self.assertTrue(_is_devanagari(reply), reply)

    def test_an_english_report_is_still_answered_in_english(self):
        from chatbot.tools.retrieval import _is_devanagari
        req = self._session_request()
        reply = self.say(req, 'my street light is broken')
        self.assertIsNotNone(reply)
        self.assertFalse(_is_devanagari(reply), reply)

    def test_devanagari_confirmation_files_rather_than_discards(self):
        """"हो" must submit. An unrecognised reply throws the draft away."""
        from chatbot.tools.flow import AFFIRMATIVE, NEGATIVE
        for word in ['हो', 'हुन्छ', 'ठीक छ', 'पठाउनुहोस्']:
            self.assertIn(word, AFFIRMATIVE)
        for word in ['होइन', 'छैन', 'रद्द']:
            self.assertIn(word, NEGATIVE)

    def test_a_short_nepali_description_is_not_refused(self):
        """Devanagari says the same thing in fewer codepoints.

        "सडक बत्ती बिग्रियो" is 18 characters and was refused by a flat
        20-character floor; "my street light is broken" says the same in 25
        and passed.
        """
        from chatbot.tools.write import _minimum_for, DESC_MIN, DESC_MIN_NE
        self.assertEqual(_minimum_for('सडक बत्ती बिग्रियो', DESC_MIN),
                         DESC_MIN_NE)
        self.assertEqual(_minimum_for('my street light is broken', DESC_MIN),
                         DESC_MIN)
        self.assertLess(len('सडक बत्ती बिग्रियो'), DESC_MIN)
        self.assertGreaterEqual(len('सडक बत्ती बिग्रियो'), DESC_MIN_NE)

    def test_a_one_word_nepali_description_is_still_refused(self):
        """Lowering the floor must not let "बिग्रियो" through as a report."""
        from chatbot.tools.write import _minimum_for, DESC_MIN, DESC_MIN_NE
        self.assertLess(len('बिग्रियो'), DESC_MIN_NE)
        self.assertEqual(_minimum_for('बिग्रियो', DESC_MIN), DESC_MIN_NE)


class BrowseVersusQuestionTests(TestCase):
    """A catalogue answers "what is there to see", not "what should I wear".

    find_attractions and find_businesses take no arguments: they return the
    whole list and cannot narrow it. Matching the bare word "temple" meant a
    question about temple dress code came back as a list of places to visit.
    """

    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()
        # Without indexed content the fallback has nothing to return and the
        # listing correctly stands in, so the rule under test never fires.
        from chatbot.models import KnowledgeChunk
        KnowledgeChunk.objects.create(
            source_type='tourism',
            title='Visitor Guidelines',
            content='Dress modestly at temples and remove your shoes before '
                    'entering. Photography is restricted inside shrines.',
            is_active=True,
        )

    def ask(self, message):
        req = self.rf.post('/chat/')
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        req.user = Anon()
        result = handle(req, message)
        return result[2] if result else None

    def test_a_specific_question_reaches_knowledge(self):
        self.assertEqual(self.ask('what should I wear to the temples'),
                         'search_municipal_knowledge')

    def test_asking_for_the_list_still_gets_the_list(self):
        """Handing every question to knowledge first was too broad.

        "what things to do in Bhaktapur" came back as Emergency Contacts,
        which matched on the place name and answered confidently.
        """
        for message in ['what is there to see', 'what things to do in Bhaktapur',
                        'what to do here', 'show me attractions']:
            self.assertEqual(self.ask(message), 'find_attractions', message)

    def test_a_plain_topic_word_still_browses(self):
        self.assertEqual(self.ask('temples in Bhaktapur'), 'find_attractions')


class CaseloadQuestionTests(TestCase):
    """Figures about the municipality's caseload are not a document question.

    "how many complaints are open" came back as the lost-passport guide, with
    full confidence. No retrieval score separated these from good answers:
    measured over a dozen known-good and known-bad cases, neither coverage
    nor the margin between the top two hits told them apart -- a correct
    "birth certificate" had a 0.02 margin and a wrong "complaint resolution
    rate" had 0.20. The mismatch is one of kind, not of confidence.
    """

    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()
        from chatbot.models import KnowledgeChunk
        KnowledgeChunk.objects.create(
            source_type='emergency',
            title='Lost passport, documents or theft',
            content='Report it to the Tourist Police, who register the '
                    'complaint and issue a Police Report. Toll free 1144.',
            is_active=True,
        )

    def ask(self, message):
        req = self.rf.post('/chat/')
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        req.user = Anon()
        result = handle(req, message)
        return result if result else (None, None, None)

    def test_caseload_questions_are_declined(self):
        for message in ['how many complaints are open',
                        'what is the complaint resolution rate',
                        'show me pending service requests',
                        'total complaints this month',
                        'कति उजुरी छन्']:
            _reply, _followups, intent = self.ask(message)
            self.assertEqual(intent, 'caseload_unavailable', message)

    def test_a_superlative_is_the_same_question(self):
        """Ranking instead of counting asks for the same unavailable figure."""
        for message in ['which ward has most complaints',
                        'सबैभन्दा धेरै उजुरी कुन वडामा']:
            _r, _f, intent = self.ask(message)
            self.assertEqual(intent, 'caseload_unavailable', message)

    def test_a_superlative_without_a_record_noun_is_untouched(self):
        """"most popular temple" is a question about temples."""
        _r, _f, intent = self.ask('most popular temple')
        self.assertNotEqual(intent, 'caseload_unavailable')

    def test_the_refusal_leaks_no_figures(self):
        reply, _f, _i = self.ask('how many complaints are open')
        self.assertNotRegex(reply, r'\d+\s+(complaints|open|pending)')

    def test_a_nepali_question_is_declined_in_nepali(self):
        from chatbot.tools.retrieval import _is_devanagari
        reply, _f, _i = self.ask('कति उजुरी छन्')
        self.assertTrue(_is_devanagari(reply), reply)

    def test_ordinary_questions_are_not_swallowed(self):
        """"how many days" is a question about a service, not a caseload."""
        for message in ['how many days for a birth certificate',
                        'how much is property tax',
                        'व्यवसाय कर कति हो']:
            _r, _f, intent = self.ask(message)
            self.assertNotEqual(intent, 'caseload_unavailable', message)

    def test_a_report_mentioning_complaints_is_still_a_report(self):
        _r, _f, intent = self.ask(
            'garbage is piling up and many complaints are ignored')
        self.assertEqual(intent, 'complaint_filing')

    def test_a_personal_lookup_is_not_swallowed(self):
        _r, _f, intent = self.ask('my complaints')
        self.assertEqual(intent, 'get_my_complaints')


class NamedFestivalTests(TestCase):
    """A named festival is not a request for the calendar.

    list_events returns what is coming up and cannot filter it, so "Bisket
    Jatra" -- the festival Bhaktapur is known for -- came back as a
    photography walk and two thangka workshops.
    """

    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()
        from chatbot.models import KnowledgeChunk
        KnowledgeChunk.objects.create(
            source_type='culture',
            title='Bisket Jatra Festival',
            content='Bisket Jatra is the Nepali new year festival of '
                    'Bhaktapur, with chariot processions in Taumadhi Square.',
            is_active=True,
        )

    def ask(self, message):
        req = self.rf.post('/chat/')
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        req.user = Anon()
        result = handle(req, message)
        return result[2] if result else None

    def test_a_named_festival_reaches_knowledge(self):
        self.assertEqual(self.ask('Bisket Jatra'), 'search_municipal_knowledge')

    def test_asking_for_the_calendar_still_gets_the_calendar(self):
        for message in ['upcoming events', 'what events are on',
                        'festivals in Bhaktapur']:
            self.assertEqual(self.ask(message), 'list_events', message)

    def test_a_partial_match_does_not_displace_the_calendar(self):
        """"Gai Jatra" must not be answered with the Bisket Jatra page."""
        self.assertEqual(self.ask('Gai Jatra'), 'list_events')


class BusinessHoursTests(TestCase):
    """The hours were fetched and then dropped on the floor.

    find_businesses already returns opening_hours and the attraction listing
    renders them, so "what time do the shops close" was answered with a list
    of addresses while the answer sat unused in the same payload.
    """

    def test_the_listing_shows_opening_hours(self):
        from chatbot.tools.present import present
        from chatbot.tools.base import ToolResult

        rows = [{'name': 'Peacock Restaurant', 'category': 'Restaurant',
                 'address': 'Durbar Square Area', 'rating': None,
                 'opening_hours': '8:00 AM - 9:00 PM'}]
        # find_businesses returns a plain list, which present() hands
        # straight to the renderer.
        reply, _ = present('find_businesses', ToolResult(ok=True, data=rows))
        self.assertIn('8:00 AM - 9:00 PM', reply)

    def test_a_business_without_hours_still_renders(self):
        from chatbot.tools.present import present
        from chatbot.tools.base import ToolResult

        rows = [{'name': 'Corner Shop', 'category': 'Retail',
                 'address': 'Taumadhi', 'rating': None,
                 'opening_hours': None}]
        reply, _ = present('find_businesses', ToolResult(ok=True, data=rows))
        self.assertIn('Corner Shop', reply)
