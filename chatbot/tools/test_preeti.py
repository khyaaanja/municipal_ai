"""Tests for Preeti conversion.

Conversion feeds municipal content to citizens, so the table is pinned by
strings whose correct Nepali is independently known.
"""
from django.test import TestCase

from chatbot.services.preeti import convert, looks_like_preeti, validate


class ConversionTests(TestCase):
    CASES = {
        ';]jfsf] lsl;d': 'सेवाको किसिम',
        'k|lqmof': 'प्रक्रिया',
        "z'Ns": 'शुल्क',
        'nfUg] ;do': 'लाग्ने समय',
        'lgj]bg': 'निवेदन',
        'gful/stf': 'नागरिकता',
        'k|df0fkq': 'प्रमाणपत्र',
        'j8f ;lrj': 'वडा सचिव',
        ';f]xL lbg': 'सोही दिन',
        'l;kmfl/;': 'सिफारिस',
        "k|zf;sLo clws[t": 'प्रशासकीय अधिकृत',
        "eQmk'/": 'भक्तपुर',
        'j8fcWoIf': 'वडाअध्यक्ष',
        'hGd btf{sf]': 'जन्म दर्ताको',
        'sfuhft': 'कागजात',
    }

    def test_known_municipal_terms(self):
        for preeti, expected in self.CASES.items():
            self.assertEqual(convert(preeti), expected, preeti)

    def test_currency_amount(self):
        self.assertEqual(convert('?= %)).-'), 'रु. ५००।-')

    def test_digit_in_numeric_context_is_not_a_letter(self):
        """Preeti's "1" is ज्ञ as a letter but १ inside a figure."""
        self.assertEqual(convert('?=10'), 'रु.१०')
        self.assertEqual(convert('1fg'), 'ज्ञान')

    def test_figures_survive_conversion(self):
        """The unshifted digit row is consonants, so figures need protecting."""
        self.assertEqual(convert('7,500।00'), '७,५००।००')
        self.assertEqual(convert('ax fn s/ 7,500.00'), 'बह ाल कर ७,५००.००')

    def test_digit_flanked_by_consonants_stays_a_consonant(self):
        """"j8f" is वडा: the 8 is ड, not the digit 8."""
        self.assertEqual(convert('j8f ;lrj'), 'वडा सचिव')
        self.assertEqual(convert('1fg'), 'ज्ञान')

    def test_trailing_comma_does_not_make_a_figure(self):
        self.assertEqual(convert('O{G6/g]6,'), 'ईन्टरनेट,')

    def test_empty_input(self):
        self.assertEqual(convert(''), '')
        self.assertEqual(convert(None), '')


class DetectionTests(TestCase):
    def test_detects_preeti(self):
        self.assertTrue(looks_like_preeti(';]jfsf] lsl;d k|lqmof lgj]bg j8f ;lrj' * 20))

    def test_does_not_flag_unicode_nepali(self):
        self.assertFalse(looks_like_preeti('सेवाको किसिम प्रक्रिया निवेदन ' * 20))

    def test_does_not_flag_empty(self):
        self.assertFalse(looks_like_preeti(''))


class ValidationTests(TestCase):
    def test_real_conversion_passes(self):
        text = convert(';]jf z\'Ns k|df0f gful/stf l;kmfl/; b:t'
                       "'/ j8f lgj]bg sfof{no")
        hits, ok = validate(text, min_hits=5)
        self.assertTrue(ok, hits)

    def test_garbage_fails_validation(self):
        _, ok = validate('zzz qqq www', min_hits=6)
        self.assertFalse(ok)
