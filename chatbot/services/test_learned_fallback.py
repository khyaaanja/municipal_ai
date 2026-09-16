"""The fallback's three tiers, and the line between them.

Municipal documents are quoted as record. Answers a resident found helpful
are served only when no document matches, and never as record — a generated
answer entering the same store as the charter is how the knowledge base once
ended up two-thirds written by the assistant citing itself.
"""
from django.core.cache import cache
from django.test import TestCase

from chatbot.management.commands.promote_helpful_answers import (
    is_promotable, keywords_of,
)
from chatbot.models import FAQEntry, KnowledgeChunk
from chatbot.services.answer_engine import (
    LocalRetrieverAdapter, get_answer_engine, open_circuit,
)


class PromotionRulesTests(TestCase):
    def test_refusals_are_never_promoted(self):
        for answer in ["Sorry, I don't have confident information on this right now, please try later and contact the office.",
                       'माफ गर्नुहोस्, यस विषयमा अहिले जानकारी उपलब्ध छैन। कृपया फेरि प्रयास गर्नुहोस्।',
                       '⚠️ Connection error. Please check your network and try again now.']:
            ok, why = is_promotable('some question', answer)
            self.assertFalse(ok, f'promoted a refusal: {why}')

    def test_short_answers_are_not_promoted(self):
        self.assertFalse(is_promotable('q', 'Yes.')[0])

    def test_a_real_answer_is_promotable(self):
        ok, _ = is_promotable(
            'Plan me a two day trip',
            'Day one: Durbar Square, Nyatapola Temple and Pottery Square. '
            'Day two: Changu Narayan and Dattatreya Square, then juju dhau.')
        self.assertTrue(ok)

    def test_keywords_cover_both_scripts(self):
        self.assertIn('bhaktapur', keywords_of('trip to Bhaktapur'))
        self.assertIn('कर', keywords_of('व्यवसाय कर'))


class TierOrderTests(TestCase):
    def setUp(self):
        cache.clear()
        KnowledgeChunk.objects.create(
            source_type='rules', title='आर्थिक ऐन (कर तथा शुल्क)',
            content='व्यवसाय तथा उद्योग करः भक्तपुर नगरपालिका क्षेत्रभित्र कर लगाइनेछ ।',
            is_active=True)
        FAQEntry.objects.create(
            question='Plan me a two day trip in Bhaktapur',
            answer='[learned] Day one: Durbar Square and Nyatapola Temple. '
                   'Day two: Changu Narayan and Dattatreya Square.',
            keywords=['plan', 'two', 'day', 'trip'], category='tourism',
            is_active=True)
        open_circuit()
        self.engine = get_answer_engine(retriever=LocalRetrieverAdapter())

    def test_municipal_document_is_quoted_as_record(self):
        answer = self.engine.answer('व्यवसाय कर कति हो?')['answer']
        self.assertIn('Based on our municipal records', answer)

    def test_learned_answer_is_not_called_a_record(self):
        answer = self.engine.answer('Plan me a two day trip in Bhaktapur')['answer']
        self.assertIn('marked helpful', answer)
        self.assertNotIn('Based on our municipal records', answer)

    def test_internal_marker_is_not_shown(self):
        answer = self.engine.answer('Plan me a two day trip in Bhaktapur')['answer']
        self.assertNotIn('[learned]', answer)

    def test_unanswerable_question_still_refuses(self):
        """A learned store must not become a source of near-miss answers."""
        result = self.engine.answer('how many complaints are pending')
        self.assertEqual(result['source'], 'none')
