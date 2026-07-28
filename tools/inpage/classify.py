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

import collections
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
RUNNING_HEADER = "running_header"

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

# Measured across all four books, counting EVERY short body paragraph that
# repeats — no name list involved. The twelve collection names of the two
# کلیات volumes run 89-209 (نیند میں چلتے ہوئے 209, موسم 182, گُلِ سیمیا 197,
# اِعادہ 179, روداد 168, ہست و بود 158, عناصر 149, کتابِ صبح 149, آیندہ 143,
# حقیقت 137, معاملہ 93, چہار دریا 89). Everything else tops out at 26:
# فہرست (26 in vol 2, 18 in vol 1), a refrain repeated 15 times inside one
# poem of vol 2, آرا 10 in vol 1. تجاوز and باغِ نشاط, which name no
# collection anywhere, have no repeat at all. That is a gap 63 wide, and 55
# sits inside it — 29 clear of the highest noise, 34 clear of the lowest
# real name.
#
# Where the repetition comes from is worth stating, because it is not what
# the name of this constant suggests. Almost every occurrence is in the
# back-of-book فہرست, where each index line prints the collection its entry
# belongs to: of عناصر's 149, some 135 are there. In the poems themselves
# each name is printed roughly once, on the collection's title page. So what
# this threshold really asks is "does the book's own index treat this text
# as a collection", and the answer is what lets `collections_at` read the
# single in-body occurrence as the point where that collection begins.
#
# This one threshold does both jobs the old name-keyed threshold of 10 did.
# It still separates a SECTION heading from a collection name (نعت 5 times,
# غزلیں 2 in vol 1) — those are far below 55 — so the two are not distinct
# concerns needing two constants: a section heading is printed where its
# section starts and nowhere else, a collection name is printed again on
# every line of the index, and any cut inside the 26-89 gap tells them apart.
RUNNING_HEADER_MIN = 55


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


def _could_be_header(text: str) -> bool:
    """A page header is a short line of text, not prose and not punctuation.

    The separator is excluded by name: ۰۰۰ repeats freely (11 times in the
    body of کلیات جلد ۲) and is punctuation, not a heading. Digit-only lines
    go with it — a page-number column is furniture of a different kind, and
    `_kind` resolves both before it ever consults this set, so admitting them
    here would only misreport what the book's headers are.
    """
    return bool(text) and len(text) < PROSE_MIN and text != SEPARATOR_TEXT \
        and not TOC_LINE.fullmatch(text)


def running_headers(paragraphs: list[Paragraph]) -> set[str]:
    """Texts that are page furniture rather than anything a piece contains.

    A header is any sufficiently-repeated short line — NOT a line whose text
    some list here recognises. Keying this on SECTION_HEADINGS worked for
    کلیات جلد ۲, whose six collection names happen to sit in that set, and
    hid کلیات جلد ۱'s six entirely: موسم، عناصر، کتابِ صبح، آیندہ، معاملہ،
    روداد are printed 884 times between them and every one of those
    paragraphs fell through to UNKNOWN, reaching no piece. A book names
    collections this pipeline has never seen, and repetition is what marks
    them out.

    Counted only inside the body: a فہرست lists section names too, and those
    are front matter, not evidence of a running header.
    """
    start = body_start_index(paragraphs)
    counts = collections.Counter(
        text
        for para in paragraphs[start:]
        if _could_be_header(text := para.text.strip())
    )
    return {text for text, n in counts.items() if n > RUNNING_HEADER_MIN}


def _kind(text: str, in_body: bool, running: set[str]) -> str:
    if text == SEPARATOR_TEXT:
        return SEPARATOR
    if TOC_LINE.fullmatch(text):
        return TOC
    if in_body and text in running:
        return RUNNING_HEADER
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


def _bridge_short_verse_lines(kinds: list[str]) -> None:
    """Reclassify UNKNOWN paragraphs enclosed by VERSE on BOTH sides.

    VERSE_MIN was measured on ghazals, whose misras run 28-42 characters. A
    نظم is free verse and its lines are not that: کلیات جلد ۲ prints سُکڑ کر
    (7 chars), کشف کی رات (10), مِرے کاندھے (11) as whole lines of one poem.
    Every one of them falls under the floor, classifies UNKNOWN, and breaks
    the verse run it sits in — so `segment` emits the fragments either side as
    separate pieces. That is where جلد ۲'s 33 one-line "nazms" came from, and
    much of its 103 unknown paragraphs reaching no piece at all.

    Lowering VERSE_MIN is not the fix. `body_start_index`, the
    front-matter/verse boundary and nazm titling all read that constant, and a
    nazm's TITLE is short in exactly the same way its lines are — dropping the
    floor would make every title verse. What separates the two is not length,
    which is identical, but position: a title sits at the EDGE of a run, a
    line of the poem sits INSIDE it. So the run's interior is what this
    reclassifies, and only that.

    A gap of any length is bridged, not only a single line — ¶877-879
    (اِس کہانی میں / کشف کی رات / بہت دن بعد) are three consecutive lines of
    one نظم, and a one-line rule would still have cut the poem there.

    A paragraph TOUCHING a run on one side only is deliberately left UNKNOWN.
    That position is genuinely ambiguous and it is where a nazm title lives
    (یاد, 3 chars, immediately before its poem); `segment` reads UNKNOWN as
    its one title candidate, so sweeping those in would retitle nazms by
    their own first line and gain nothing that context can vouch for.
    Measured, both promoted books have ZERO enclosed cases — تجاوز 0 of 8
    UNKNOWN, باغِ نشاط 0 of 4 — so neither can move; جلد ۲ has 148.
    """
    index = 0
    while index < len(kinds):
        if kinds[index] != UNKNOWN:
            index += 1
            continue
        end = index
        while end < len(kinds) and kinds[end] == UNKNOWN:
            end += 1
        if index and kinds[index - 1] == VERSE and kinds[end:end + 1] == [VERSE]:
            kinds[index:end] = [VERSE] * (end - index)
        index = end


def classify(paragraphs: list[Paragraph]) -> list[str]:
    """Return one kind per paragraph, in order."""
    start = body_start_index(paragraphs)
    running = running_headers(paragraphs)
    kinds = [
        _kind(para.text.strip(), index >= start, running)
        for index, para in enumerate(paragraphs)
    ]
    _bridge_short_verse_lines(kinds)
    return kinds


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
