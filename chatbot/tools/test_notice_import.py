"""Tests for the official notice importer.

Parsing and classification are tested against a fixture rather than the
live site, so the suite stays offline and deterministic.
"""
from django.test import TestCase

from chatbot.management.commands.import_official_notices import classify, parse

FIXTURE = '''
<div class="views-row">
  <a href="/ne/content/tender-one">भक्तपुर नगरपालिकाको बोलपत्र (E-bidding)आव्हानको सूचना !</a>
</div></div>
<div class="views-row">
  <a href="/ne/content/job-one">भक्तपुर नगरपालिकाको लागि आवश्यक जनशक्ति सेवा करारमा लिनेसम्बन्धी सूचना</a>
</div></div>
<div class="views-row">
  <a href="/ne/content/notice-one">भक्तपुर नगरपालिकाको अनुरोध सूचना !</a>
</div></div>
<div class="views-row">
  <a href="/ne/content/tender-one">भक्तपुर नगरपालिकाको बोलपत्र (E-bidding)आव्हानको सूचना !</a>
</div></div>
<div class="views-row"><a href="/ne/content/x">short</a></div></div>
'''


class ParseTests(TestCase):
    def setUp(self):
        self.rows = list(parse(FIXTURE))

    def test_extracts_notices(self):
        self.assertEqual(len(self.rows), 3)

    def test_duplicate_links_collapse(self):
        urls = [url for _, url in self.rows]
        self.assertEqual(len(urls), len(set(urls)))

    def test_titles_are_absolute_urls(self):
        for _, url in self.rows:
            self.assertTrue(url.startswith('https://bhaktapurmun.gov.np/'))

    def test_too_short_titles_are_skipped(self):
        self.assertNotIn('short', [t for t, _ in self.rows])

    def test_empty_input_yields_nothing(self):
        self.assertEqual(list(parse('')), [])


class ClassifyTests(TestCase):
    def test_nepali_tender_keyword(self):
        self.assertEqual(classify('नगरपालिकाको बोलपत्र आव्हानको सूचना'), 'TENDER')

    def test_nepali_job_keyword(self):
        self.assertEqual(classify('आवश्यक जनशक्ति सेवा करारमा लिनेसम्बन्धी'), 'JOB')

    def test_english_tender_keyword(self):
        self.assertEqual(classify('E-bidding notice'), 'TENDER')

    def test_regulation_keyword(self):
        self.assertEqual(classify('कार्यविधि स्वीकृत'), 'REGULATION')

    def test_defaults_to_notice(self):
        self.assertEqual(classify('नगरपालिकाको अनुरोध'), 'NOTICE')


class PresentationTests(TestCase):
    def test_url_reference_is_not_shown_as_a_reference_number(self):
        from chatbot.tools.readonly import _public_reference
        self.assertIsNone(_public_reference(
            'https://bhaktapurmun.gov.np/ne/content/%E0%A4%AD'))
        self.assertIsNone(_public_reference('/ne/content/abc'))
        self.assertEqual(_public_reference('BKT-362'), 'BKT-362')

    def test_source_url_extracted_from_body(self):
        from chatbot.tools.readonly import _source_url
        self.assertEqual(
            _source_url('Title\n\nSource: https://bhaktapurmun.gov.np/ne/content/x'),
            'https://bhaktapurmun.gov.np/ne/content/x')
        self.assertIsNone(_source_url('no source here'))
