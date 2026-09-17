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


# A run of ASCII digits with optional separators is a figure, not letters.
# Preeti's unshifted number row carries consonants, so "7,500.00" would
# otherwise convert to "ठ,छ००.००" — a garbled amount in a fee schedule.
# Bounded by non-letters, because a digit flanked by Preeti consonants is a
# consonant itself: "j8f" is वडा, not "v8a". And a lone digit is ambiguous,
# so a figure must be two digits or carry a separator.
# A trailing comma does not make a figure: "6," in "O{G6/g]6," is the letter
# ट. Thousands separators must sit between digit groups, and a matra before
# the digit means we are mid-word, not at a number.
_NUMERIC_RUN = re.compile(
    r"(?<![A-Za-z\]\['\"}{])"
    r'(?:\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+\.\d+|\d{2,})'
    r'(?![A-Za-z])')
_SENTINEL = '\uE000'


# The unshifted number row carries consonants in this layout, so a digit that
# survived conversion between two letters was never a figure: "व८ा" is वडा.
# The numeric-run guard lifts figures out before conversion, and it cannot
# tell a consonant-digit from a real one, so it occasionally protects the
# wrong thing and hands back a Devanagari numeral wedged inside a word.
_LETTER = '\u0900-\u0939\u093E-\u094D'
_DIGIT_CONSONANT = {'\u0969': '\u0918', '\u096B': '\u091B', '\u096C': '\u091F',
                    '\u096D': '\u0920', '\u096E': '\u0921', '\u096F': '\u0922'}
# '0f' was ण: the zero became ० and the 'f' became the long-a matra.
_LOST_NA = re.compile(f'(?<=[{_LETTER}])\u0966\u093E')
# A short-i typed before the consonant could not hop over a protected digit,
# so it is still on the wrong side: "एि६एम" is एटिएम.
#
# Only where the matra is on an independent vowel, which Devanagari does not
# allow -- "ए" cannot carry one, so the matra must belong to the consonant
# the digit is hiding. After an ordinary consonant the matra is already where
# it belongs: "मि६र" is मिटर, not मटिर.
_INDEPENDENT_VOWEL = '\u0905-\u0914'
_MATRA_BEFORE_DIGIT = re.compile(
    f'(?<=[{_INDEPENDENT_VOWEL}])\u093F([{"".join(_DIGIT_CONSONANT)}])'
    f'(?=[{_LETTER}])')
_DIGIT_IN_WORD = re.compile(
    f'(?<=[{_LETTER}])([{"".join(_DIGIT_CONSONANT)}])(?=[{_LETTER}])')


# A digit at the edge of a word cannot be judged by position alone. Nine of
# the thirty-three candidates in this corpus are Preeti's own encoding of
# brackets around English that was mangled by being converted at all --
# "९द्गषति ग्उ ब्च०" is "(Square feet)", where ९ is "(" and not ढ. Mapping
# those to consonants would corrupt text that is merely untranslated.
#
# So the edge cases are listed, not inferred, and each was read in context
# before being added here.
_EDGE_WORDS = {
    'पर्ने५': 'पर्नेछ', 'लाग्ने५': 'लाग्नेछ', 'सक्ने५': 'सक्नेछ',
    'हुने५': 'हुनेछ', 'गर्ने५': 'गर्नेछ',
    'बुझाएपि५': 'बुझाएपछि',
    'बजे६': 'बजेट', 'कम्पोष६': 'कम्पोषट',
    '३न': 'घन',      # घन मिटर -- the unit a water tariff is charged in
    '९ल': 'ढल',      # ढल जोडाय् शुल्क -- the sewer connection charge
}
_EDGE = re.compile('|'.join(sorted(map(re.escape, _EDGE_WORDS), key=len,
                                   reverse=True)))


def repair_edge_digits(text):
    """Fix words whose digit sits at the edge, from a verified list."""
    return _EDGE.sub(lambda m: _EDGE_WORDS[m.group(0)], text or '')


def repair_digit_consonants(text):
    """Turn a digit wedged between letters back into its consonant."""
    text = _LOST_NA.sub('\u0923', text or '')
    text = _MATRA_BEFORE_DIGIT.sub(
        lambda m: _DIGIT_CONSONANT[m.group(1)] + '\u093F', text)
    return _DIGIT_IN_WORD.sub(lambda m: _DIGIT_CONSONANT[m.group(1)], text)


# A halant followed by a vowel sign is not valid Devanagari: the consonant
# that belonged between them was lost. The table above maps 'E' to भ् with
# nothing to complete it, and the scanned documents came through full of the
# result -- "उद्योग" appeared 33 times and never once spelled correctly,
# "विद्यालय" 10 times, never correctly. A term nobody spells the way the
# document spells it is a term nobody can search for.
_VOWEL_SIGNS = '\u093E-\u094C\u0962\u0963'
# झ lands as भ + halant before a vowel. भ् before a *consonant* is ordinary
# Nepali -- अभ्यास -- and must be left alone.
_LOST_JHA = re.compile(f'\u092D\u094D(?=[{_VOWEL_SIGNS}])')
# Every other orphaned halant lost a य: उद्ोग -> उद्योग.
_LOST_YA = re.compile(f'([\u0915-\u0939])\u094D(?=[{_VOWEL_SIGNS}])')


def repair_text(text):
    """Every repair that is safe to re-apply to already-correct text.

    The short-i hop in `convert` is deliberately not here: it moves a matra
    that sits before a consonant, which is exactly what correct Unicode looks
    like, so running it twice would break "मिति" into "मति".
    """
    return repair_conjuncts(
        repair_edge_digits(repair_digit_consonants(text)))


def repair_conjuncts(text):
    """Restore conjuncts the conversion dropped.

    Applied to converted output, and again by the matcher, so a document
    imported before this existed still meets a question that uses the
    correct spelling.
    """
    text = _LOST_JHA.sub('\u091D', text or '')
    return _LOST_YA.sub('\\1\u094D\u092F', text)


def convert(text):
    """Return Unicode Devanagari for Preeti-encoded `text`."""
    if not text:
        return ''
    table = dict(SINGLE)
    table.update(MULTI)

    # Lift figures out before conversion, then put them back as Devanagari
    # digits. Protecting them afterwards is impossible: by then the digits
    # have already become consonants and are indistinguishable from letters.
    figures = []

    def _stash(match):
        figures.append(match.group(0))
        return _SENTINEL

    text = _NUMERIC_RUN.sub(_stash, text)
    out = _TOKEN.sub(lambda m: table[m.group(0)], text)
    for figure in figures:
        out = out.replace(_SENTINEL, figure.translate(_ASCII_TO_DEV), 1)
    # Before the matra hop: a short-i cannot move across a protected digit,
    # which is how "एटिएम" came out as "एि६एम".
    out = repair_digit_consonants(out)
    out = _I_MATRA.sub(r'\1ि', out)
    out = _REPH.sub(r'र्\1\2', out)
    out = _DIGIT_CONTEXT.sub('१', out)
    out = repair_conjuncts(out)
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
