"""Preeti (legacy Nepali typewriter font) to Unicode Devanagari.

Nepali municipal documents are overwhelmingly typeset in Preeti, which maps
Devanagari onto ASCII codepoints. Such a PDF extracts as text, but as
";]jfsf] lsl;d" rather than "सेवाको किसिम".

This is a font encoding, not OCR, so the mapping is deterministic and the
conversion is lossless. It is still only as good as the table below, which
is why `validate` exists: converted text is checked against known municipal
vocabulary before anything derived from it is trusted.
"""
import re

# The Preeti keyboard layout. Order matters only for multi-character
# sequences, which are applied first by `_TOKEN`.
SINGLE = {
    ')': '०', '!': '१', '@': '२', '#': '३', '$': '४',
    '%': '५', '^': '६', '&': '७', '*': '८', '(': '९',

    'a': 'ब', 'b': 'द', 'c': 'अ', 'd': 'म', 'e': 'भ', 'f': 'ा',
    'g': 'न', 'h': 'ज', 'i': 'ष', 'j': 'व', 'k': 'प', 'l': 'ि',
    'm': '्', 'n': 'ल', 'o': 'य', 'p': 'उ', 'q': 'त्र', 'r': 'च',
    's': 'क', 't': 'त', 'u': 'ग', 'v': 'ख', 'w': 'ध', 'x': 'ह',
    'y': 'थ', 'z': 'श',

    # Unshifted number row carries consonants in this layout; Devanagari
    # digits come from the shifted row above.
    '3': 'घ', '5': 'छ', '6': 'ट', '7': 'ठ', '8': 'ड', '9': 'ढ',

    'A': 'ब्', 'B': 'द्', 'C': 'ऋ', 'D': 'म्', 'E': 'भ्', 'F': 'ँ',
    'G': 'न्', 'H': 'ज्', 'I': 'क्ष्', 'J': 'व्', 'K': 'प्', 'L': 'ी',
    'M': 'ः', 'N': 'ल्', 'O': 'य्', 'P': 'ए', 'Q': 'त्त', 'R': 'च्',
    'S': 'क्', 'T': 'त्', 'U': 'ग्', 'V': 'ख्', 'W': 'ध्', 'X': 'ह्',
    'Y': 'थ्', 'Z': 'श्',

    ';': 'स', ':': 'स्', "'": 'ु', '"': 'ू', '[': 'ृ', ']': 'े',
    '{': 'र्', '}': 'ै', '|': '्र', '\\': 'ा', '/': 'र', '?': 'रु',
    '+': 'ं', '=': '.', '.': '।', ',': ',',
    '~': 'ञ्', '`': 'ञ', '<': 'ङ्', '>': 'ः', 'ª': 'ङ', '´': 'झ',
    '¥': 'र्‍', '÷': '/', '–': '-', '—': '-',
}

# Sequences that must win over their single-character prefixes.
MULTI = {
    'cf': 'आ', 'cf]': 'ओ', 'cf}': 'औ', 'cP': 'ऐ', 'c}': 'ऐ',
    # The long-a matra followed by e/ai composes into the o/au matra.
    'f]': 'ो', 'f}': 'ौ',
    'O{': 'ई', 'pm': 'ऊ', 'km': 'फ', '0f': 'ण', 'if': 'ष',
    '1': 'ज्ञ', '4': 'द्व', '>': 'श्र', 'qm': 'क्र', 'Qm': 'क्त', 'If': 'क्ष', 'Iff': 'क्षा',
    'if{': 'र्ष', 'sf}': 'कौ',
}

_TOKEN = re.compile('|'.join(
    re.escape(k) for k in sorted(set(MULTI) | set(SINGLE), key=len, reverse=True)))

# In Preeti the short-i matra is typed before its consonant; Unicode stores
# it after the full consonant cluster, so each one hops right.
_I_MATRA = re.compile(r'ि((?:[क-ह]्)*[क-ह])')

# The reph is typed after its consonant in Preeti and stored before it in
# Unicode, so "पूवर्" has to become "पूर्व".
_REPH = re.compile(r'([क-ह])((?:[ािीुूृेैोौंँः])*)र्')

# Preeti's "1" is the letter ज्ञ, but documents routinely use the same key
# for the digit १. In a fee schedule the digit reading is nearly always the
# intended one, so ज्ञ is restored to १ wherever it sits in a number.
_DIGIT_CONTEXT = re.compile(r'(?<=[०-९0-9])ज्ञ|ज्ञ(?=[०-९0-9])|(?<=रु\.)ज्ञ|(?<=रु)ज्ञ')


# Municipal vocabulary used to check a conversion actually produced Nepali.
PROBE_WORDS = (
    'सेवा', 'शुल्क', 'प्रमाण', 'नागरिक', 'सिफारिस', 'दस्तुर', 'वडा',
    'निवेदन', 'कार्यालय', 'नगरपालिका', 'प्रतिलिपि', 'दर्ता', 'कर',
    'जन्म', 'मृत्यु', 'विवाह', 'सम्बन्ध', 'अधिकृत', 'समय', 'कागजात',
)


def convert(text):
    """Return Unicode Devanagari for Preeti-encoded `text`."""
    if not text:
        return ''
    table = dict(SINGLE)
    table.update(MULTI)
    out = _TOKEN.sub(lambda m: table[m.group(0)], text)
    out = _I_MATRA.sub(r'\1ि', out)
    out = _REPH.sub(r'र्\1\2', out)
    out = _DIGIT_CONTEXT.sub('१', out)
    return _normalise_digits(out)


def validate(converted, min_hits=6):
    """How many known municipal words the conversion produced.

    A correct table yields many; a wrong one yields almost none, because
    plausible-looking Devanagari that is not real Nepali will not contain
    these exact strings.
    """
    hits = {w: converted.count(w) for w in PROBE_WORDS if w in converted}
    return hits, len(hits) >= min_hits


def looks_like_preeti(text, threshold=0.10):
    if not text:
        return False
    sample = text[:4000]
    markers = sum(sample.count(c) for c in ";]|{}[fkjnb/'")
    return markers / max(len(sample), 1) > threshold


_ASCII_TO_DEV = str.maketrans('0123456789', '०१२३४५६७८९')
_MIXED_NUMBER = re.compile(r'[०-९][०-९0-9]*|(?<=रु\.)[0-9]+')


def _normalise_digits(text):
    """Make numbers single-script.

    Extraction leaves runs like "रु.१0" where part of a figure converted and
    part did not. A fee that renders half in each script reads as broken, so
    any run touching a Devanagari digit is normalised to Devanagari.
    """
    return _MIXED_NUMBER.sub(lambda m: m.group(0).translate(_ASCII_TO_DEV), text)
