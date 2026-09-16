"""Guard the published contact details against drifting back.

`+977-1-6610000` reached citizens from twelve places -- complaint mail,
password-reset mail, marketplace mail, dashboard notifications and the
assistant's own "I don't know" reply -- and the municipality publishes no
such number. It looked right, so it survived every review until someone
went looking for its source.
"""
import pathlib
import re

from django.test import TestCase

from core import contacts

REPO = pathlib.Path(__file__).resolve().parent.parent
# Only our own source. rglob over the repo root walks venv/ and
# node_modules/ before any filter can reject them, which took the test from
# under a second to over ten minutes.
SOURCES = ('accounts', 'chatbot', 'civic', 'complaints', 'core', 'dashboard',
           'events', 'marketplace', 'municipal_ai', 'news', 'services',
           'tourism', 'businesses', 'templates')
SKIP = {'node_modules', 'log', 'venv', '.git', 'staticfiles', 'graphify-out',
        'migrations', '__pycache__'}
UNVERIFIED = re.compile(r'6610000')


class PublishedContactTests(TestCase):
    def test_no_unverified_number_in_source(self):
        """No file may name a number the municipality does not publish."""
        offenders = []
        candidates = (
            path
            for root in SOURCES
            if (REPO / root).is_dir()
            for path in (REPO / root).rglob('*')
        )
        for path in candidates:
            if path.suffix not in {'.py', '.html', '.txt', '.json'}:
                continue
            if SKIP & set(path.relative_to(REPO).parts):
                continue
            # Two files name the number legitimately: the one explaining
            # why it is gone, and the one that removes it from stored data.
            if path == pathlib.Path(contacts.__file__):
                continue
            if path.name in {pathlib.Path(__file__).name,
                             'correct_contact_numbers.py'}:
                continue
            try:
                text = path.read_text(encoding='utf-8')
            except (UnicodeDecodeError, OSError):
                continue
            if UNVERIFIED.search(text):
                offenders.append(str(path.relative_to(REPO)))
        self.assertEqual(
            offenders, [],
            'unverified municipality number found in: ' + ', '.join(offenders),
        )

    def test_nepali_text_uses_nepali_forms(self):
        """An English "or" or Arabic digits inside Devanagari reads as a bug."""
        self.assertNotIn(' or ', contacts.PHONES_NE)
        self.assertIn(' वा ', contacts.PHONES_NE)
        for digit in '0123456789':
            self.assertNotIn(digit, contacts.EMERGENCY_LINE_NE)

    def test_no_answer_reply_carries_a_reachable_contact(self):
        from chatbot.services.answer_engine import NO_INFO_MESSAGE
        self.assertIn(contacts.PHONE_PRIMARY, NO_INFO_MESSAGE)
        self.assertIn(contacts.EMAIL, NO_INFO_MESSAGE)
