"""An answer must not claim a source it does not have.

The chat labelled every reply with the data that had been put in front of
the model, not the data the reply came from. A generated itinerary carrying
an invented taxi fare was tagged "📚 Knowledge Base", which reads as though
the municipality published that figure.
"""
import re

from django.core.cache import cache
from django.test import TestCase

from chatbot.tools import REGISTRY


class QuotedIntentCoverageTests(TestCase):
    """Every tool must be listed as quoted, or its answers get a false caveat."""

    def setUp(self):
        cache.clear()
        body = self.client.get('/chat/').content.decode()
        block = re.search(r'QUOTED_INTENTS = new Set\((\[.*?\])\)', body, re.S)
        self.assertIsNotNone(block, 'QUOTED_INTENTS not found in the chat page')
        self.listed = set(re.findall(r"'([a-z_]+)'", block.group(1)))

    def test_every_registered_tool_is_listed(self):
        missing = set(REGISTRY) - self.listed
        self.assertEqual(missing, set(),
                         f'tools missing from QUOTED_INTENTS: {sorted(missing)}')

    def test_conversational_states_are_listed(self):
        for state in ('complaint_filing', 'submission_cancelled'):
            self.assertIn(state, self.listed, state)


class SourceLabelTests(TestCase):
    def setUp(self):
        cache.clear()
        self.body = self.client.get('/chat/').content.decode()

    def test_generated_answers_carry_a_caveat(self):
        self.assertIn('Written by the assistant using city data', self.body)

    def test_caveat_names_what_to_double_check(self):
        """Vague warnings get ignored; name the things that cost money."""
        for word in ('fee', 'date', 'phone'):
            self.assertIn(word, self.body)

    def test_labels_do_not_claim_the_answer_is_a_database_row(self):
        """'Knowledge Base' on generated prose overstates the provenance."""
        self.assertNotIn("'knowledge_base': '📚 Knowledge Base'", self.body)
        self.assertIn('Municipal records', self.body)
