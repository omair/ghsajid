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

# The typesetter sometimes ran two misras onto a single physical line, e.g.
# "آپ کا اذن ہوتے ہی چل دوں گا مَیں، اپنے موجود کو بھی بدل دوں گا مَیں" (67
# chars) and "میرے ہونے سے کچھ فرق پڑتا نہیں، بارِ غم میرے رونے سے جھڑتا نہیں"
# (63 chars) — both plainly two misras joined by a comma. Measured across the
# corpus, this UNKNOWN band (63-100 chars, in body) is never noise: تجاوز 0,
# باغِ نشاط 7, کلیات vol 1 22, کلیات vol 2 204 (503 UNKNOWN total, of which
# 299 are the genuinely ambiguous <15 case). Anything in this range is kept as
# verse rather than falling through to UNKNOWN, where segment() only ever
# treats UNKNOWN as a possible nazm title and silently drops the rest.
# VERSE_MAX itself still means "a normal single misra" and is used elsewhere
# (e.g. body_start_index); this is a distinct, explicit rule layered on top,
# not a widening of that constant.
RUN_TOGETHER_MISRA_MAX = 100

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


# Two shers' worth of alternation. ONE sher is not enough evidence: تجاوز's
# publisher block — رنگِ ادب پبلی کیشنز (19 chars, geometry 81) followed by
# آفس نمبرکتاب مارکیٹ ،اُردو بازار،کراچی (38 chars, geometry 1) — is
# coincidentally sher-shaped, and a 2-paragraph test starts the body at index
# 10 in both pilot books, swallowing the whole فہرست.
#
# Measured: a run of 4 lands تجاوز on index 85 (its first ghazal) and
# باغِ نشاط on 136 (a real verse line). Do NOT raise it further — 6 pushes
# باغِ نشاط to 145 and skips a genuine poem.
MIN_BODY_RUN = 4


def body_start_index(paragraphs: list[Paragraph]) -> int:
    """Index where the poems begin, or len(paragraphs) if never.

    Uses raw character length rather than the VERSE kind: VERSE itself depends
    on the body having started, so the other way round would be circular.

    The ghazal-shaped run locates the body, but it is not where the body
    begins: both pilot books close their critic's essay with a ۰۰۰, and
    باغِ نشاط then prints the epigraph couplet it is named after and the
    opening four lines of its نعت before the first run the search can see.
    Starting at the run classified all six as front_matter and dropped them.
    The boundary therefore lands just after the LAST separator preceding the
    run — in تجاوز that separator is at 84 and the run at 85, so nothing
    moves; in باغِ نشاط the separator is at 128 and the run at 136, and the
    six paragraphs become body. With no separator before the run, the run's
    own index stands.

    The backward search stops at prose (see `_last_separator_before`): an
    essay is front matter however it is fenced, and reaching back over one
    would put the critic inside the poems.
    """
    for index in range(len(paragraphs) - MIN_BODY_RUN + 1):
        run = paragraphs[index:index + MIN_BODY_RUN]
        if all(
            _is_verse_length(para.text)
            and (para.geometry == SECOND_MISRA_GEOMETRY) == (offset % 2 == 1)
            for offset, para in enumerate(run)
        ):
            return _last_separator_before(paragraphs, index)
    return len(paragraphs)


def _last_separator_before(paragraphs: list[Paragraph], index: int) -> int:
    """One past the last ۰۰۰ before `index`, or `index` if there is none.

    The walk stops at the first prose-length paragraph, which is the critic's
    essay. Both pilot books close that essay with its own ۰۰۰, so the walk
    never reaches it — but a book that did not would otherwise have the body
    start at the separator that OPENS the essay, putting the whole essay
    inside the poems and swallowing the first ghazal along with it (see
    tests.test_inpage_segment.TestEssayRegion). Prose before the poems is
    front matter however it is fenced.
    """
    for earlier in range(index - 1, -1, -1):
        text = paragraphs[earlier].text.strip()
        if text == SEPARATOR_TEXT:
            return earlier + 1
        if len(text) >= PROSE_MIN:
            break
    return index


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
    if in_body and VERSE_MAX < len(text) <= RUN_TOGETHER_MISRA_MAX:
        # Run-together misras (see RUN_TOGETHER_MISRA_MAX above) — real verse,
        # not unknown.
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


URDU_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
DIGIT_RUN = re.compile(r"[۰-۹]+")


def toc_count(paragraphs: list[Paragraph]) -> int | None:
    """How many pieces the book's own فہرست says it contains.

    The highest entry number, read only from paragraphs before the body
    starts — page numbers printed within the poems would otherwise count.
    Returns None when the book has no parseable فہرست, so the gate can report
    that it could not run rather than passing silently.
    """
    start = body_start_index(paragraphs)
    numbers: list[int] = []
    for para in paragraphs[:start]:
        text = para.text.strip()
        if text == SEPARATOR_TEXT or not TOC_LINE.fullmatch(text):
            continue
        numbers.extend(
            int(run.translate(URDU_DIGITS)) for run in DIGIT_RUN.findall(text)
        )
    positive = [n for n in numbers if n > 0]
    return max(positive) if positive else None
