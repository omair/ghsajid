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
from collections.abc import Iterable

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

# The Gregorian months as the poet writes them. Every colophon in the corpus
# names one.
MONTHS = (
    "جنوری", "فروری", "مارچ", "اپریل", "مئی", "جون",
    "جولائی", "اگست", "ستمبر", "اکتوبر", "نومبر", "دسمبر",
)

# A month name followed by the year marker in the position a year occupies:
# nothing between them but digits, spaces and the punctuation that separates
# a date — `مئی ۲۰۱۰ئ` when the digits survived, `دسمبرئ`, `دسمبر ئ`,
# `جنوری، ئ` when they did not. The longest real gap measured is five
# characters (` ۲۰۰۴`, جلد ۲ ¶4114); six is allowed, and widening it to eight
# changes no line in any of the four books.
MONTH_YEAR = re.compile(
    "(?:" + "|".join(MONTHS) + r")[۰-۹\s،,\-]{0,6}[ئء]"
)

# A date bracketed as a WHOLE line is a publisher's imprint on a collection's
# title page, not a poem's signature (see `_is_colophon`). The whole line, not
# a bracket anywhere in it: جلد ۲ ¶2036 `، اپریل ئ۔لاہور (کرفیو کا ایک دن)` is
# a genuine colophon that happens to end in a parenthetical.
WHOLLY_BRACKETED = re.compile(r"\(.*\)")

SECTION_HEADINGS = frozenset({
    # سلام belongs with نعت and حمد: the same devotional forms, printed the
    # same way. Without it the word fell inside the نعت run as a line of
    # verse, so the نعت that precedes it ended on a phantom half-sher and
    # the سلام itself lost its own section.
    "غزلیں", "نعت", "نظمیں", "حمد", "سلام", "قطعات", "رباعیات",
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


def heading_map(sections: Iterable[str] = ()) -> dict[str, str]:
    """Normalised heading text → the section name to record for it.

    `SECTION_HEADINGS` above are forms of address that recur across books —
    غزلیں, نعت, a کلیات volume's own collection names. `sections` are names
    that exist only in ONE book's printed index: موسم's بہار، سعیر، برشگال،
    خزاں، زمہریر، قدیم and عناصر's مٹّی، پانی، آگ، ہَوا، خواب, transcribed
    in `printed_index`.

    They are passed in per book rather than added to the frozenset because
    they are ordinary Urdu words. Nothing licenses reading آگ as a section
    heading in a book whose index never declared one, and جلد ۲ prints a
    bare خواب of its own at ¶32. Measured across all four books, none of
    these names occurs anywhere in تجاوز or باغِ نشاط — both promoted, both
    required to stay byte-identical — and the empty default keeps every
    existing caller's classification unchanged.

    `حمدِ <section>` maps to the SECTION, not to itself. Each of موسم's six
    sections opens with a حمد the index titles that way, and the poem needs
    the section it belongs to; its own title comes from its matlaa like
    every other poem in the archive. Being a heading at all is the point —
    `_bridge_lines_enclosed_by_verse` was absorbing these lines into the
    previous ghazal, which cost the heading, the following poem's boundary,
    and six poems from موسم's count.
    """
    mapping = dict(NORMALISED_HEADINGS)
    for name in sections:
        mapping[skeleton(name)] = name
        mapping[skeleton(f"حمدِ {name}")] = name
    return mapping

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


def _is_colophon(text: str) -> bool:
    """A short line signing a poem with the date and place it was written.

    Two independent ways in, because InPage stores digits separately from the
    text and they do not always survive decoding. A colophon does two jobs —
    it becomes the piece's `written_note`, and it CLOSES the poem it follows —
    so a missed one does not merely lose metadata, it welds the next poem onto
    the last. جلد ۲'s largest نظم piece was 365 lines for that reason.

    `YEAR` — four Urdu digits then ء/ئ — is the original rule and is kept
    unchanged: it catches every colophon whose digits did survive (117 in
    کلیات جلد ۲, 11 in جلد ۱, 1 in تجاوز) and does not depend on a month
    being named at all.

    `MONTH_YEAR` is the added path, for the colophons whose digits vanished:
    `یکم دسمبرئ۔ لاہور`, `، اپریل ئ۔ لاہور`, `دسمبر ئ۔ لاہور`. It finds 52
    more in کلیات جلد ۲, 1 in جلد ۱, and 0 in either promoted book — neither
    تجاوز nor باغِ نشاط has a digit-stripped colophon anywhere, so neither can
    move, and a before/after dump of both confirms they do not.

    Both the month AND the year marker are required, never either alone:

    * A month alone is not evidence. A poem may simply name one, and the
      count of month-naming lines in جلد ۲ (179) is three times the count of
      colophons among them.
    * ء/ئ alone is far weaker still — کوئی and ہوئی each carry one, so the
      letter says nothing about a line.
    * Nor is "a month somewhere and a hamza somewhere" enough. Requiring the
      marker in the YEAR'S OWN POSITION — separated from the month only by
      the digits that vanished and their punctuation — is what excludes
      جلد ۲ ¶1090, a real line of verse that contains both: گُلِ غیب کی آگ سے
      رنگ لیتی ہوئی سُرمئی بے کلی (سُرمئی holds مئی, and its own ئ). That is
      the single false positive the loose form admits, and the tight one
      admits none.

    The length bound stays for the same reason it was there: جلد ۱'s اعتذار
    and the biographical note are 333-722 character essays that name months
    and carry a stray ئ, and an essay is not a signature.

    A wholly-bracketed line is refused by the new path only. کلیات جلد ۱
    prints four publisher imprints shaped almost like colophons — ¶248, ¶2125,
    ¶6789, ¶7874, e.g. (یکم اکتوبر ئ،اورینٹ پبلشرز،لاہور) — each sitting on a
    collection's title page between its name and its dedication. اورینٹ
    پبلشرز is not where a poem was written, so calling one a colophon would
    stamp a publisher onto the preceding ghazal's `written_note`; and those
    lines are part of the title-page block `attribute_gathered_collections`
    reads to place collection boundaries, which must not move. Brackets are
    the shape that separates the two: none of جلد ۲'s 52 digit-stripped
    colophons is bracketed, and every bracketed date that IS a colophon
    (تجاوز ¶83 (۵-مئی ۲۰۲۳ئ), جلد ۱ ¶264, ¶5294) kept its four digits, so the
    `YEAR` path still claims it and the exclusion costs nothing.
    """
    if len(text) > COLOPHON_MAX:
        return False
    if YEAR.search(text):
        return True
    return bool(MONTH_YEAR.search(text)) and not WHOLLY_BRACKETED.fullmatch(text)


def _kind(
    text: str,
    in_body: bool,
    running: set[str],
    headings: dict[str, str] | None = None,
) -> str:
    if text == SEPARATOR_TEXT:
        return SEPARATOR
    if TOC_LINE.fullmatch(text):
        return TOC
    if in_body and text in running:
        return RUNNING_HEADER
    if skeleton(text) in (NORMALISED_HEADINGS if headings is None else headings):
        return HEADING
    if _is_colophon(text):
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


# What the enclosure rule may rewrite, and how long a run of each it will
# take. UNKNOWN and PROSE are the two kinds a line of a poem falls into when
# only its LENGTH is consulted — under VERSE_MIN and over PROSE_MIN
# respectively — so they are the two the rule may reconsider. Every other kind
# is recognised by something other than length (a separator by its text, a
# colophon by its date, a running header by its repetition); that evidence is
# positive where length is merely a default, so enclosure does not override
# it, and a RUNNING_HEADER between two verse lines stays page furniture.
#
# The run limits differ, and that difference is measured, not stylistic:
#
# * Consecutive SHORT lines are consecutive lines of one poem. جلد ۲ ¶877-879
#   (اِس کہانی میں / کشف کی رات / بہت دن بعد) is three of them in a row, so
#   any limit at all would cut that نظم. Hence None.
#
# * Consecutive PROSE-LENGTH paragraphs, with no verse between them, are prose
#   discourse — a critic writing paragraph after paragraph and quoting the
#   poet only now and then. Of the enclosed prose runs measured, the singles
#   are the poet's own asides (356, 231, 135, 103 …) but EVERY run of two or
#   more is essay text: جلد ۱'s pairs are 1323+1066, 1181+593, 1249+431 and
#   its longest enclosed run is 17 paragraphs; جلد ۲'s are 1698+433,
#   4021+380, 1618+3008. Bridging them dissolves the essays into the poems —
#   at a limit of 2 جلد ۱'s اورینٹ پبلشرز title-page block becomes a نظم, and
#   at 4 جلد ۲'s ڈاکٹر مسعود اقبال essay becomes a 331-line one. A poet sets
#   ONE aside between two lines of verse; two 1,300-character paragraphs
#   back to back is someone else talking. Hence 1.
MAX_ENCLOSED_RUN = {UNKNOWN: None, PROSE: 1}

# An ASIDE — a body paragraph over PROSE_MIN that OPENS with a bracket — is
# grouped with the short lines rather than with prose discourse, because that
# is what it is: something set inside a poem, not a paragraph of a critic's
# argument. A critic's paragraph does not begin mid-parenthesis.
#
# Measured across all four books, body paragraphs of prose length opening with
# a bracket: تجاوز 0, باغِ نشاط 0, کلیات جلد ۱ 0, کلیات جلد ۲ 1 — ¶1855,
# '(جو نِت دن بند مُٹھی میں قید تتلی کی طرح…', the aside of the نظم that
# begins اور یہ دِل. (¶1272, the 356-character aside this change was written
# for, opens with a bracket too; it needs no help, having verse on both
# sides already.) One paragraph is thin evidence for a rule and it is stated
# here as such — but the alternative is worse than thin, it is impossible:
# ¶1855's left neighbour is the نظم line اور یہ دِل, 10 characters and so
# UNKNOWN, and merging UNKNOWN with PROSE into one enclosed run is what moves
# باغِ نشاط (see the docstring below). The bracket is the only thing that
# separates ¶1855 from باغِ نشاط's decode garbage, and without it ¶1855 opens
# an essay region that swallows 1,269 paragraphs.
#
# Grouping, not classifying: an aside that is NOT enclosed by verse keeps the
# kind `_kind` gave it and still opens a region, so nothing can be lost this
# way.
OPENING_BRACKET = "("
ASIDE_GROUP = UNKNOWN


def _enclosable_group(kind: str, text: str) -> str | None:
    """Which enclosed-run group a paragraph joins, or None if it joins none."""
    if kind == PROSE and text.startswith(OPENING_BRACKET):
        return ASIDE_GROUP
    return kind if kind in MAX_ENCLOSED_RUN else None


def _bridge_lines_enclosed_by_verse(
    kinds: list[str], paragraphs: list[Paragraph]
) -> None:
    """Reclassify length-derived kinds enclosed by VERSE on BOTH sides.

    One rule now, where there were two. VERSE_MIN and PROSE_MIN were both
    measured on ghazals, whose misras run 28-42 characters, and free verse
    breaks that calibration at BOTH ends. Under the floor: کلیات جلد ۲ prints
    سُکڑ کر (7 chars), کشف کی رات (10), مِرے کاندھے (11) as whole lines of one
    poem — they classify UNKNOWN, break the verse run, and `segment` emits the
    fragments either side as separate pieces (whence جلد ۲'s 33 one-line
    "nazms"). Over the ceiling: ¶1272 is a 356-character parenthetical aside
    sitting between two verse lines of a نظم — it classifies PROSE, and PROSE
    is what OPENS a critic's essay region, so that one line swallowed 1,749
    verse paragraphs, 42 colophons and 30 unknowns into a single 3,617-line
    `reviews` piece holding poetry from several collections.

    Those are the same failure — length read as evidence where it has none —
    so they get one enclosure test, one BRIDGEABLE set, and one pass. What
    they do NOT share is how many paragraphs in a row the evidence survives,
    and MAX_ENCLOSED_RUN above states that per kind with the measurement
    behind it. Unifying to "any run of either, any length" was tried and is
    wrong twice over: it merges a mixed UNKNOWN+PROSE run, which moves
    باغِ نشاط (a promoted book), and it dissolves real critics' essays into
    nazms.

    An enclosed paragraph may still be very long — جلد ۱ has single enclosed
    paragraphs of 945 and 1217 characters, جلد ۲ one of 972. Whether such a
    passage is one very long verse line or a prose interlude the poet set
    inside a nazm is not something this pipeline can tell, and it does not
    need to: either way it belongs to the poem it sits in, not to a separate
    `reviews` piece attributed to a critic.

    Neither bound may be relaxed instead. `body_start_index`, the
    front-matter/verse boundary and nazm titling all read VERSE_MIN, and a
    nazm's TITLE is short in exactly the same way its lines are — dropping the
    floor would make every title verse. Raising PROSE_MIN is worse: the
    critics' essays contain real paragraphs of 250-3,000 characters that must
    stay prose. What separates the two cases is not length, which is
    identical, but position: an essay or a title sits at the EDGE of a verse
    run, a line of the poem sits INSIDE it.

    A paragraph TOUCHING a run on one side only is deliberately left alone, at
    both ends of the length scale. That position is genuinely ambiguous and it
    is where both a nazm title (یاد, 3 chars, immediately before its poem) and
    a critic's essay opening on a quotation live; `segment` reads UNKNOWN as
    its one title candidate and PROSE as its one region opener, so sweeping
    those in would retitle nazms by their own first line and weld essays onto
    poems.

    A run is homogeneous by GROUP, and the groups are not the kinds: UNKNOWN
    and ordinary PROSE never merge into one enclosed run, because merging them
    moves a promoted book. باغِ نشاط ¶1419-1421 is UNKNOWN(8), UNKNOWN(9),
    PROSE(106) between two verse lines — end-of-stream decode garbage — and
    جلد ۲ ¶1854-1855 is UNKNOWN(10), PROSE(149) between two verse lines, a
    real نظم line and the poet's aside. By kind and position the two are
    identical, so no adjacency rule can take the second without also taking
    the first, and باغِ نشاط must come out byte-identical. What separates them
    is the bracket ¶1855 opens with (see ASIDE_GROUP): an aside is set inside
    a poem, garbage is not, and grouping the aside with the short lines lets
    the نظم line beside it come along.

    Measured, both promoted books have ZERO enclosed cases of either kind —
    تجاوز 0 of 8 UNKNOWN and 0 prose in body, باغِ نشاط 0 of 4 UNKNOWN and 0
    of its 1 body prose — so neither moves, and a direct `segment()` dump
    before and after confirms both are byte-identical. جلد ۲ has 148 enclosed
    short runs and 45 single enclosed prose paragraphs, جلد ۱ has 12.
    """
    groups = [
        _enclosable_group(kind, para.text.strip())
        for kind, para in zip(kinds, paragraphs, strict=True)
    ]
    index = 0
    while index < len(kinds):
        group = groups[index]
        if group is None:
            index += 1
            continue
        end = index
        while end < len(kinds) and groups[end] == group:
            end += 1
        limit = MAX_ENCLOSED_RUN[group]
        if (
            index
            and kinds[index - 1] == VERSE
            and kinds[end:end + 1] == [VERSE]
            and (limit is None or end - index <= limit)
        ):
            kinds[index:end] = [VERSE] * (end - index)
        index = end


def classify(
    paragraphs: list[Paragraph], sections: Iterable[str] = ()
) -> list[str]:
    """Return one kind per paragraph, in order.

    `sections` names the headings known only from this book's printed
    index — see `heading_map`. Omitting it classifies exactly as before.
    """
    start = body_start_index(paragraphs)
    running = running_headers(paragraphs)
    headings = heading_map(sections)
    kinds = [
        _kind(para.text.strip(), index >= start, running, headings)
        for index, para in enumerate(paragraphs)
    ]
    _bridge_lines_enclosed_by_verse(kinds, paragraphs)
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
