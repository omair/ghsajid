"""The InPage byte <-> Unicode table.

InPage stores text as (font_selector, char_code) byte pairs. Only ~132 distinct
char codes occur across the corpus, and they are per-LETTER codes, not
per-ligature glyph ids — so a lookup table is sufficient and no font
reverse-engineering is required.

Every entry carries the evidence that established it. A wrong entry corrupts
every occurrence of that letter, silently, in every poem at once; character
counts and round-trip checks are both blind to it. Do not add an entry you
cannot justify here.
"""

from typing import Iterable

_ALPHABET = "ابپتٹثجچحخدڈذرڑزژسشصضطظعغفقکگلمن"
_ALPHABET_EVIDENCE = (
    "0x81-0xA0 follow the Urdu alphabet order; confirmed by decoding "
    "the prose preface of TAJAWUZ into fluent Urdu"
)

# byte code -> (unicode text, evidence)
CODEPAGE: dict[int, tuple[str, str]] = {
    0x20: (" ", "literal ASCII space; 19% of all codes, the word separator"),
}
for _i, _ch in enumerate(_ALPHABET):
    CODEPAGE[0x81 + _i] = (_ch, _ALPHABET_EVIDENCE)

CODEPAGE.update({
    0xA1: ("ں", "noon-ghunna; from زبانوں / میں in the TAJAWUZ preface"),
    0xA2: ("و", "wao; from اور / خوش in the TAJAWUZ preface"),
    0xA3: ("ئ", "hamza-ye; from مسائل / کئی in the TAJAWUZ preface"),
    0xA4: ("ی", "choti ye; 7.4% freq, from حسین / کی"),
    0xA5: ("ے", "bari ye; from سے / ہے"),
    0xA6: ("ہ", "gol he; from ہیں / عہد"),
    0xA7: ("ھ", "do-chashmi he; 1.9% freq, the remaining he form"),
    0xAC: ("ُ", "pesh/damma; from اُردو / اُنہوں"),
    0xF3: ("۔", "Urdu full stop; sentence-final throughout the preface"),
})

# Genuine duplicate codes, if any are discovered: alias -> canonical code.
# Declared explicitly so the injectivity test stays meaningful.
ALIASES: dict[int, int] = {}

_REVERSE: dict[str, int] = {
    text: code
    for code, (text, _) in CODEPAGE.items()
    if code not in ALIASES
}


def decode_byte(code: int) -> str | None:
    """Return the Unicode text for one InPage char code, or None if unmapped."""
    entry = CODEPAGE.get(code)
    return entry[0] if entry else None


def encode_char(text: str) -> int | None:
    """Return the canonical InPage char code for `text`, or None."""
    return _REVERSE.get(text)


def unmapped(codes: Iterable[int]) -> set[int]:
    """Return the subset of `codes` this table cannot decode."""
    return {code for code in codes if code not in CODEPAGE}
