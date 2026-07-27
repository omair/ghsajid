"""Decide what one decoded paragraph is.

Measured against the real corpus rather than guessed. In تجاوز's verse body,
`geometry == 1` marks the second misra of every sher — it is exactly 50% of
paragraphs and alternates across 1634 of 1642 transitions. Verse runs 28-42
characters at p10-p90; only 7 paragraphs in the whole book exceed 100 (the
foreword), 133 fall under 25, and 51 are the فہرست's page-number column.

The rules overlap — a nazm title is shorter than the verse floor, ۰۰۰ is
digits-only — so the ORDER below is part of the specification, not an
implementation detail.
"""

import re

from .groundtruth import skeleton
from .models import Paragraph

SEPARATOR = "separator"
TOC = "toc"
HEADING = "heading"
COLOPHON = "colophon"
PROSE = "prose"
VERSE = "verse"
FRONT_MATTER = "front_matter"
UNKNOWN = "unknown"

VERSE_MIN = 15
VERSE_MAX = 62
PROSE_MIN = 101
SEPARATOR_TEXT = "۰۰۰"
SECOND_MISRA_GEOMETRY = 1

TOC_LINE = re.compile(r"^[۰-۹۔\s]+$")
# The hamza after a year decodes as ئ (InPage 0xA3), not ء. Accept both.
YEAR = re.compile(r"[۰-۹]{4}\s*[ئء]")
COLOPHON_MAX = 50

SECTION_HEADINGS = frozenset({
    "غزلیں", "نعت", "نظمیں", "حمد", "قطعات", "رباعیات",
    "نیند میں چلتے ہوئے", "چہار دریا", "ہست و بود", "اعادہ", "حقیقت", "گل سیمیا",
})

# Headings in the کلیات source can carry diacritics the codepage now maps
# (e.g. گُل سیمیا with a pesh on the گ). SECTION_HEADINGS stays written in
# plain form per the brief; comparisons go through skeleton() instead, so the
# match is diacritic-insensitive without touching the readable constant.
# Precomputed once — not per paragraph — since this set never changes. Maps
# the normalised form back to the plain heading, so a diacritic-bearing
# source heading (گُل سیمیا) still records the section as گل سیمیا, matching
# SECTION_HEADINGS rather than whatever spelling the source happened to use.
NORMALISED_HEADINGS = {skeleton(heading): heading for heading in SECTION_HEADINGS}


def _is_verse_length(text: str) -> bool:
    return VERSE_MIN <= len(text) <= VERSE_MAX


def body_start_index(paragraphs: list[Paragraph]) -> int:
    """Index of the first ghazal-shaped pair, or len(paragraphs) if none.

    Uses raw character length rather than the VERSE kind: VERSE itself depends
    on the body having started, so the other way round would be circular.
    """
    for index in range(len(paragraphs) - 1):
        first, second = paragraphs[index], paragraphs[index + 1]
        if (
            _is_verse_length(first.text)
            and _is_verse_length(second.text)
            and first.geometry != SECOND_MISRA_GEOMETRY
            and second.geometry == SECOND_MISRA_GEOMETRY
        ):
            return index
    return len(paragraphs)


def _kind(text: str, in_body: bool) -> str:
    if text == SEPARATOR_TEXT:
        return SEPARATOR
    if TOC_LINE.fullmatch(text):
        return TOC
    if skeleton(text) in NORMALISED_HEADINGS:
        return HEADING
    if len(text) <= COLOPHON_MAX and YEAR.search(text):
        return COLOPHON
    if len(text) >= PROSE_MIN:
        return PROSE
    if in_body and _is_verse_length(text):
        return VERSE
    if not in_body:
        return FRONT_MATTER
    return UNKNOWN


def classify(paragraphs: list[Paragraph]) -> list[str]:
    """Return one kind per paragraph, in order."""
    start = body_start_index(paragraphs)
    return [
        _kind(para.text.strip(), index >= start)
        for index, para in enumerate(paragraphs)
    ]
