"""Tests for the conversational filing flow."""
import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase

from chatbot.management.commands.index_knowledge_base import split_content
from chatbot.models import KnowledgeBase, KnowledgeChunk
from complaints.models import Complaint

User = get_user_model()


class FilingFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()

    def say(self, message):
        resp = self.client.post(
            '/api/chat/', data=json.dumps({'message': message}),
            content_type='application/json')
        return resp.json()['response']

    def test_full_anonymous_filing_conversation(self):
        self.assertIn('Where is it', self.say('there is a huge pothole on my street'))
        self.assertIn('name', self.say('Durbar Square road').lower())
        draft = self.say('Ram Shrestha')
        self.assertIn('Nothing has been filed yet', draft)
        self.assertEqual(Complaint.objects.count(), 0)

        filed = self.say('yes')
        self.assertIn('Filed', filed)
        self.assertEqual(Complaint.objects.count(), 1)
        self.assertEqual(Complaint.objects.get().category, 'ROAD')

    def test_declining_files_nothing(self):
        self.say('garbage is piling up near the temple')
        self.say('Taumadhi Square')
        self.say('Sita Devi')
        self.assertIn('Nothing was filed', self.say('no'))
        self.assertEqual(Complaint.objects.count(), 0)

    def test_ambiguous_reply_does_not_submit(self):
        """An unclear answer must never be read as consent."""
        self.say('no water supply for three days')
        self.say('Ward 4')
        self.say('Alice')
        self.say('actually can you change the location')
        self.assertEqual(Complaint.objects.count(), 0)

    def test_authenticated_user_is_not_asked_for_a_name(self):
        user = User.objects.create_user(email='flow@example.com', password='pw-flow-1')
        self.client.force_login(user)
        self.say('streetlight is broken outside my house')
        draft = self.say('Sukuldhoka')
        self.assertIn('Nothing has been filed yet', draft)
        self.say('yes')
        self.assertEqual(Complaint.objects.get().user, user)

    def test_unrelated_message_falls_through(self):
        self.say('tell me about the history of Bhaktapur')
        self.assertEqual(Complaint.objects.count(), 0)


class SplitContentTests(TestCase):
    def test_short_content_is_one_chunk(self):
        self.assertEqual(split_content('A short fact.'), ['A short fact.'])

    def test_empty_content_yields_nothing(self):
        self.assertEqual(split_content(''), [])
        self.assertEqual(split_content(None), [])

    def test_long_content_splits_on_sentences(self):
        text = ' '.join(f'Sentence number {i} about Bhaktapur.' for i in range(120))
        chunks = split_content(text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 1000 for c in chunks))

    def test_devanagari_danda_is_a_boundary(self):
        text = ('भक्तपुर एक ऐतिहासिक शहर हो। ' * 60).strip()
        chunks = split_content(text)
        self.assertGreater(len(chunks), 1)

    def test_two_chunks_with_short_tail_fold_together(self):
        """Regression: folding the tail back must not index past the list."""
        body = 'This is a reasonably long sentence about Bhaktapur heritage. ' * 14
        chunks = split_content(body + 'Short tail.')
        self.assertTrue(all(c.strip() for c in chunks))
        self.assertIn('Short tail.', chunks[-1])

    def test_no_content_is_lost(self):
        text = ' '.join(f'Fact {i} here.' for i in range(100))
        joined = ' '.join(split_content(text))
        self.assertEqual(len(joined.split()), len(text.split()))


class IndexCommandTests(TestCase):
    def test_indexing_populates_chunks(self):
        from django.core.management import call_command
        from io import StringIO

        KnowledgeBase.objects.create(
            title='Bisket Jatra', category='culture', language='en',
            content='Bisket Jatra marks the Nepali new year in Bhaktapur. '
                    'It features a chariot procession through the old town.',
            is_active=True,
        )
        call_command('index_knowledge_base', stdout=StringIO())
        self.assertEqual(KnowledgeChunk.objects.count(), 1)
        chunk = KnowledgeChunk.objects.get()
        self.assertEqual(chunk.source_type, 'culture')
        self.assertTrue(chunk.is_active)

    def test_rebuild_does_not_duplicate(self):
        from django.core.management import call_command
        from io import StringIO

        KnowledgeBase.objects.create(
            title='Emergency', category='emergency', language='en',
            content='Call 100 for police assistance in Bhaktapur.', is_active=True)
        call_command('index_knowledge_base', stdout=StringIO())
        call_command('index_knowledge_base', '--rebuild', stdout=StringIO())
        self.assertEqual(KnowledgeChunk.objects.count(), 1)

    def test_inactive_entries_are_skipped(self):
        from django.core.management import call_command
        from io import StringIO

        KnowledgeBase.objects.create(
            title='Retired notice', category='general', language='en',
            content='This entry is no longer current.', is_active=False)
        call_command('index_knowledge_base', stdout=StringIO())
        self.assertEqual(KnowledgeChunk.objects.count(), 0)
