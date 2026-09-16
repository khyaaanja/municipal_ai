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
