"""An answer quoted as official should say how old the document is.

The corpus spans seven fiscal years. The citizen charter is 2076/077 --
roughly 2019 -- and the tax Act is 2083/084, the current year. Both were
presented with the same words: "quoted from the municipality's official
records, unchanged". A citizen reading a fee off a seven-year-old charter
had no way to know it might have moved, and would act on it.
"""
from django.core.cache import cache
from django.test import TestCase

from chatbot.models import KnowledgeChunk
from chatbot.tools.present import _age_note, _fiscal_year_of


class FiscalYearTests(TestCase):
    def test_year_is_read_from_the_title(self):
        self.assertEqual(_fiscal_year_of('नागरिक वडापत्र (2076/077) — 9'), 2076)
        self.assertEqual(_fiscal_year_of('आर्थिक ऐन (कर तथा शुल्क) (2083/084)'), 2083)

    def test_an_undated_title_has_no_year(self):
        self.assertIsNone(_fiscal_year_of('Accommodation in Bhaktapur'))


class AgeNoteTests(TestCase):
    def setUp(self):
        cache.clear()
        for title in ['आर्थिक ऐन (कर तथा शुल्क) (2083/084) — 2',
                      'नागरिक वडापत्र (2076/077) — 9',
                      'Accommodation in Bhaktapur']:
            KnowledgeChunk.objects.create(
                source_type='procedure', title=title,
                content='x', is_active=True)

    def test_an_old_document_is_flagged_with_its_age(self):
        note = _age_note(['नागरिक वडापत्र (2076/077) — 9'])
        self.assertIn('7 years older', note)
        self.assertIn('2076/077', note)

    def test_the_current_document_is_not_flagged(self):
        self.assertEqual(_age_note(['आर्थिक ऐन (कर तथा शुल्क) (2083/084) — 2']), '')

    def test_undated_content_is_not_flagged(self):
        self.assertEqual(_age_note(['Accommodation in Bhaktapur']), '')

    def test_the_oldest_source_decides(self):
        """A mixed answer is only as current as its weakest source."""
        note = _age_note(['आर्थिक ऐन (कर तथा शुल्क) (2083/084) — 2',
                          'नागरिक वडापत्र (2076/077) — 9'])
        self.assertIn('7 years older', note)

    def test_the_baseline_comes_from_the_corpus_not_a_constant(self):
        """Importing a newer document must move the baseline by itself."""
        cache.clear()
        KnowledgeChunk.objects.create(
            source_type='procedure', title='आर्थिक ऐन (2090/091)',
            content='x', is_active=True)
        note = _age_note(['आर्थिक ऐन (कर तथा शुल्क) (2083/084) — 2'])
        self.assertIn('7 years older', note)
