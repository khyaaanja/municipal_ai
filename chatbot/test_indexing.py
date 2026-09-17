"""Indexing twice must not index twice.

The command appended by default, so every run added another full copy of the
corpus: 189 entries had become 873 byte-identical chunks. Retrieval
reconsiders its top candidates by coverage, so duplicates fill that pool and
crowd out the document that answers -- "building permit fees" stopped
reaching the Act that sets them because the pool held three copies each of
two visitor pages.
"""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from chatbot.models import KnowledgeBase, KnowledgeChunk


class IndexIdempotenceTests(TestCase):
    def setUp(self):
        KnowledgeBase.objects.create(
            title='Visitor Rules & Entry Fees',
            category='rules',
            content='Entry fee for foreign visitors is NPR 1500.',
            language='en',
            is_active=True,
        )

    def index(self, *args):
        call_command('index_knowledge_base', *args, stdout=StringIO())

    def test_running_twice_leaves_one_copy(self):
        self.index()
        first = KnowledgeChunk.objects.count()
        self.index()
        self.assertEqual(KnowledgeChunk.objects.count(), first)

    def test_running_twice_leaves_no_duplicate_titles(self):
        self.index()
        self.index()
        titles = list(KnowledgeChunk.objects.values_list('title', flat=True))
        self.assertEqual(len(titles), len(set(titles)))

    def test_append_is_available_but_not_the_default(self):
        self.index()
        first = KnowledgeChunk.objects.count()
        self.index('--append')
        self.assertEqual(KnowledgeChunk.objects.count(), first * 2)

    def test_reindexing_drops_content_removed_from_the_source(self):
        """A replaced index reflects the source; an appended one cannot."""
        self.index()
        KnowledgeBase.objects.update(is_active=False)
        self.index()
        self.assertEqual(KnowledgeChunk.objects.count(), 0)
