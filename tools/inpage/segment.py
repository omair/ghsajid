"""Find piece boundaries inside a decoded book.

A ghazal carries no title in the source; the site titles poems by their matlaa,
so finding the boundary IS finding the title. The paragraph mark's 4-byte
record is geometry — a line position stepping down a page — not a style id, so
a value that drops back toward the top of a page marks a new piece.

This is heuristic by construction. Nothing here writes to content/: the output
goes to staging with a report, and a human resolves every flag.
"""

import re
from collections.abc import Iterable

from .classify import (
    COLOPHON, HEADING, PROSE, RUNNING_HEADER,
    SECOND_MISRA_GEOMETRY, SEPARATOR, TOC, UNKNOWN, VERSE, body_start_index,
    classify, heading_map,
)
from .groundtruth import skeleton
from .models import Paragraph, Segment
from .flags import BYLINE_FLAG, TITLE_PAGE_FLAG
from .printed_index import PROSE_TITLES_BY_BOOK, SECTION_NAMES_BY_BOOK

# A real ghazal's matlaa is a line of verse, not a paragraph. When the
# boundary heuristic fails to find a break inside a large prose block (front
# matter, a foreword), the whole block becomes one "title" — one real pilot
# run produced a ~1400-character title that then crashed slugify()'s output
# path. The piece is never dropped for this; it is only flagged so a human
# reviewing the report can see it.
MAX_TITLE_LENGTH = 200

# Rhyme in Urdu is heard, not spelled, so the two orthographic differences that
# never change the sound are folded before any tail is compared. Both were
# measured as real missed matlaa in the pilot: تجاوز's ...اُتر آئی against a
# run rhyming گویائی/پسپائی/شہنائی (آ vs ا), and باغِ نشاط's ...ہالہ کہاں سے
# آتا ہے against اُجالا/والا/سنبھالا (word-final ہ vs ا). Each miss silently
# welded two ghazals into one piece.
# ق folds to ک for the same reason, and it is the one entry here that is
# about Urdu rather than about orthography: ق is an Arabic letter Urdu
# borrowed and pronounces /k/, so حق and دستک rhyme as surely as دستک and
# ٹھنڈک do. عناصر's ہَوا section is where it mattered — every one of its
# twenty ghazals ends ہَوا نے, so the radif can never separate them, and the
# only boundary is the qafia. The poem opening
# `چراغِ صبح سے چھینا ہے اُس کا حق ہَوا نے` was read as a continuation of the
# ghazal above it because its ق did not match the ک of the دستک/ٹھنڈک/کالک
# run, and ہَوا stood at 19 against the بیس غزلیں its فہرست declares.
# Confirmed against the printed book, which starts the two on different
# pages. Measured across all four books, this fold moves exactly that one
# boundary: تجاوز, باغِ نشاط and جلد ۲ are byte-identical without it.
RHYME_FOLD = str.maketrans(
    {"آ": "ا", "ۂ": "ہ", "ۃ": "ہ", "ؤ": "و", "ۓ": "ے", "ق": "ک"}
)
FINAL_HE = re.compile(r"ہ(?=\s|$)")

# A rhyme is compared as characters, not words: the qafia is a *partial* word
# (نگ سے across سنگ/رنگ/ترنگ, یں تھا across زمیں/مبیں/یقیں), and it is exactly
# the part a word-tail comparison cannot see. Two characters is the floor —
# a bare ہے or سے is not evidence of anything.
MIN_RHYME = 2

# How many shers of the prospective new ghazal establish its rhyme. One sher
# cannot: its own tail carries accidental letters (سنگ سے alone yields
# "سنگ سے", not the qafia). Measured, the piece count is identical at 3, 4 and
# 5 for both pilot books, so this is a plateau rather than a fitted constant.
RHYME_WINDOW = 4

# The poet's takhallus. A sher carrying it is the maqtaa, the closing sher, so
# the ghazal after it is a new ghazal even when it happens to rhyme alike —
# this is what separates باغِ نشاط's ...بنامِ وصال ghazal from the ...خدّ و خال
# ghazal that follows it in the same "-ال" family.
TAKHALLUS = "ساجد"


GHAZAL_SHAPE_THRESHOLD = 0.9

# What opens an essay region, and what closes it. Both pilot books fence the
# critic's opening essay between ۰۰۰ separators; a section heading (غزلیں,
# نعت) closes one just as firmly, and so does the body start, since anything
# past it is the poems themselves.
#
# A RUNNING_HEADER also closes one, but is deliberately absent from
# REGION_OPEN_KINDS: کلیات vol 2 prints the current collection's name atop
# every page, and a page header is page furniture, not evidence that a new
# foreword begins. Without it in REGION_CLOSE_KINDS, the essay region opened
# earlier in the book had nothing to stop it once body_start had already
# moved past the essay's own closing separator (exactly چہار دریا's
# situation, being a later collection, not the book's front matter) — it ran
# to the end of the book, and all 89 pages of چہار دریا, a whole published
# collection, vanished into one `reviews` piece. A new page of a poetry
# collection is definitively not still the foreword.
REGION_OPEN_KINDS = (SEPARATOR, TOC, HEADING)
REGION_CLOSE_KINDS = (SEPARATOR, HEADING, RUNNING_HEADER)

# تجاوز prints the essay's title first and its author second; باغِ نشاط
# prints them the other way round, so position alone cannot tell them apart —
# and taking the first line blind titled باغِ نشاط's essay "ڈاکٹر شاہد اشرف",
# its critic's name.
#
# An academic honorific does distinguish them: a critic is introduced as
# ڈاکٹر or پروفیسر, and a title is not. That is a real convention of Urdu
# literary criticism, not a guess about these two files. When exactly one
# heading line opens with an honorific it is the byline and the other is the
# title; anything else still keeps every line in the body, takes the first as
# the title, and raises the flag for a human, because attributing the wrong
# person to criticism of the poet's work is not a mistake worth risking.
HONORIFICS = ("ڈاکٹر", "پروفیسر", "سیّد", "سید", "پیر", "مولانا")


def _split_byline(heading_lines: list[str]) -> tuple[str, str, bool]:
    """Return `(title, author, resolved)` for an essay's heading lines."""
    bylines = [
        line for line in heading_lines
        if line.strip().startswith(HONORIFICS)
    ]
    others = [line for line in heading_lines if line not in bylines]
    if len(bylines) == 1 and others:
        return others[0], bylines[0], True
    return (heading_lines[0] if heading_lines else ""), "", False


def _is_ghazal_shaped(run: list[Paragraph]) -> bool:
    """True when most of the run pairs cleanly into shers.

    Measured by greedy pairing, NOT by positional parity. Parity — asking
    whether geometry == 1 falls on odd indices — is fragile: one unpairable
    line shifts the parity of everything after it, so conformance collapses to
    ~50% from the first anomaly onward. باغِ نشاط has 8 such lines in 1276 and
    was misfiled as a single nazm; تجاوز has zero, which is the only reason
    parity appeared to work there.

    Greedy pairing resyncs after each anomaly, so the measurement stays local:
    باغِ نشاط scores 634 clean pairs of 642 (98.8%) and تجاوز 817 of 817.
    A nazm, whose lines do not alternate at all, produces mostly half shers
    and falls far below the threshold.
    """
    if len(run) < 2:
        return False
    shers = pair_shers(run)
    clean = sum(1 for _, second in shers if second)
    return clean / len(shers) >= GHAZAL_SHAPE_THRESHOLD


def _ghazal_body(shers: list[tuple[str, str]]) -> str:
    return "\n\n".join(
        "\n".join(line for line in sher if line) for sher in shers
    )


def collections_at(paragraphs: list[Paragraph], kinds: list[str]) -> list[str]:
    """The collection in effect at each paragraph.

    A running page header names the collection from that page onward. A
    piece must take the name in force where its own first line sits: a verse
    run can span two collections when one book's poems run straight into the
    next with nothing between them, and stamping such a run from a single
    running variable gives every poem in it the last name seen.
    """
    current = ""
    out: list[str] = []
    for para, kind in zip(paragraphs, kinds):
        if kind == RUNNING_HEADER:
            current = para.text
        out.append(current)
    return out


# --- کلیات جلد ۱: the books it gathers, and how it delimits them -----------
#
# `collections_at` reads a poem's collection off the page headers, and both
# کلیات volumes have them. That is NOT enough for جلد ۱, and the reason is
# specific: موسم is the volume's first collection and its name is never
# printed as a paragraph before its poems — the first موسم paragraph in the
# book is at index 9796, in the back-of-book فہرست, long after its 130
# ghazals are done. Every other collection's name is printed once, on its
# title page, where its poems begin. With headers alone the 130 موسم poems
# are backfilled with the earliest header that does exist, عناصر, which then
# reads 231 poems instead of the 100 its own فہرست declares. The title pages
# below are what name موسم and where عناصر actually starts. This is what
# this path contributes over the general one, and the whole of it.
#
# It delimits those books the way the printed books themselves do. Each one
# opens, INSIDE the body, with its own title page: an imprint (month, year,
# publisher, city, in parentheses) and a dedication, usually followed by an
# epigraph couplet and a دیباچہ. Segmentation has no category for a title
# page, so a block falls out as whatever its shape suggests — `reviews` at
# order 4, `nazms` at 135, 238, 332 and 438, `ghazals` at 455. Its KIND
# therefore carries no information. Those two printed lines do.

# The imprint. The year's digits do not survive InPage's separate number
# stream, so what reaches the text is the hamza that follows them (decoded as
# ئ, InPage 0xA3 — the same one classify.YEAR accepts) inside a bracketed run
# carrying at least one Urdu comma: "(جون ئ،اورینٹ پبلشرز،لاہور)". One
# bracket may be missing where the piece boundary fell through it — order
# 238 reads "ئ،سارنگ پبلی کیشنز،لاہور)" — so the opening paren is optional.
COLLECTION_IMPRINT = re.compile(r"^\(?[^()]{0,60}ئ\s*[،,][^()]{0,60}\)$")

# The dedication: a whole line reading "<someone> کے نام" or "<someone> کے
# لیے", optionally exclaimed.
COLLECTION_DEDICATION = re.compile(r"^.{0,60}?(?:کے نام|کے لیے)\s*!?$")


def collection_boundary_dedication(piece: Segment) -> str:
    """The dedication line of `piece` if it is a collection's title page.

    BOTH lines are required, and that is the whole of the detection. A
    dedication alone is not evidence of anything: a ghazal whose radif is
    کے لیے ends every second misra on it, and کلیات جلد ۱ holds 20 such
    ghazals — reading them as boundaries would cut the volume into 26
    "collections", most of them one poem long. Every block in the volume
    prints both lines, so requiring both costs nothing and is exact:
    measured across all four books in the corpus, imprint AND dedication
    together select 6 pieces in کلیات جلد ۱ and nothing at all in تجاوز,
    باغِ نشاط or کلیات جلد ۲.

    The title is searched as well as the body: the block at order 332 was cut
    such that its imprint became the piece's title and only the dedication
    stayed in the body.
    """
    lines = [piece.title.strip()] + [
        line.strip() for line in piece.body.split("\n") if line.strip()
    ]
    if not any(COLLECTION_IMPRINT.match(line) for line in lines):
        return ""
    return next(
        (line for line in lines if COLLECTION_DEDICATION.match(line)), ""
    )


# The NAME is never taken from the block itself — a title page's lines run
# together unpredictably once segmented, and guessing one wrong misattributes
# a whole published book of this poet's work to another with no gate
# downstream able to see it. It is read from this table, keyed by the
# dedication the block prints (the one line of a title page unique to its
# book), and every entry carries the evidence that established it, in the
# manner of codepage.py. Do not add an entry you cannot justify here.
#
# A block whose dedication is not in this table is REPORTED and its poems are
# left unattributed: an unnamed collection is truthful, a guessed name is not.
#
# The decisive evidence for the whole table is the volume's own title page.
# Paragraph 4 of کلیات جلد ۱, under مزامیر / (کلیاتِ غلام حسین ساجدؔ) /
# (جلداوّل), reads:
#
#     (موسم، عناصر، کتابِ صبح، آیندہ، معاملہ اور رُوداد)
#
# Six names, in this order — the book stating its own contents. The six title
# pages found in the body are six, in this order, and each entry's dedication
# sits on the block introducing the collection at that position. The
# per-entry evidence below is what corroborates each name independently of
# that line, so no name rests on a single reading; the title page is what
# makes the SET closed, and it is why a seventh block appearing here would be
# a finding rather than a name to invent.
KULLIYAT_JILD_1_COLLECTIONS: dict[str, tuple[str, str]] = {
    "مرحوم ماں باپ کے نام": (
        "موسم",
        "the volume's own فہرست (the piece at order 1) opens on موسم and "
        "lists its six sections — بہار، سعیر، برشگال، خزاں، زمہریر at "
        "بیس غزلیں each and قدیم at تیس غزلیں; the block itself prints موسم "
        "as its first line; the essay at order 439 names it first in "
        "‘‘موسم، عناصر، کتابِ صبح اور آئندہ کی شاعری’’ and the poet's own "
        "روداد at order 456 opens ‘‘موسموں کی کتھا کہتے’’",
    ),
    "محمدخالد کے لیے": (
        "عناصر",
        "the فہرست lists عناصر second, with its five sections مٹّی، پانی، "
        "آگ، ہَوا، خواب at بیس غزلیں each; the block prints عناصر and its "
        "subtitle ‘‘(مٹّی، پانی، آگ، ہَوا اورخواب)’’; named again in the "
        "essay at order 439 and in روداد's ‘‘عناصر سے ہم کلامی’’",
    ),
    "ڈاکٹر مرزا حامد بیگ کے لیے": (
        "کتابِ صبح",
        "the فہرست lists کتابِ صبح third; the block prints کتابِ صبح and "
        "the epigraph sher ‘‘وہ کام آئیں گے تزئینِ کتابِ صبح میں ساجدؔ’’; "
        "named again in the essay at order 439",
    ),
    "اپنی بیٹی سنبل نسیم کے لیے": (
        "آیندہ",
        "the block's دیباچہ line reads ‘‘آیندہ تخلیقی وفور کا ایک کرشمہ’’; "
        "the essay at order 439 names it fourth — ‘‘…اور آئندہ کی شاعری’’ — "
        "and روداد at order 456 has ‘‘آیندہ کے خواب بنتے ہوئے’’",
    ),
    "شمس الرحمن فاروقی کے نام": (
        "معاملہ",
        "the block prints معاملہ and quotes ‘‘معاملہ ہے کوئی اور ہی ہمارے "
        "بیچ’’; the دیباچہ immediately after it (order 439, ڈاکٹر نجیب "
        "جمال) is headed ‘‘معاملہ’’ کی غزلیں and discusses their shared "
        "radif — the fifteen ہمارے بیچ ghazals that follow, which are "
        "exactly the fifteen the collection's own فہرست lists (see "
        "tests.test_inpage_pilot.TestHumareBeechCollection)",
    ),
    "راشدہ ساجد کے نام": (
        "روداد",
        "the poet's own preface immediately after the block (order 456) is "
        "headed روداد, signed غلام حسین ساجد, and says ‘‘روداد’’ اُسی دنیا "
        "کی بازیافت کا ثمر ہے; the block carries its own separate imprint "
        "(مارچ، سانجھ پبلی کیشنز، لاہور), which is what shows معاملہ ended "
        "at the fifteenth ہمارے بیچ ghazal rather than running to the end "
        "of the volume. Spelled روداد, as the preface and the running text "
        "print it; the title page's رُوداد is the same word with the pesh "
        "set",
    ),
}

# Which volumes are gatherings delimited this way, keyed by book slug. Keyed
# rather than applied everywhere for the same reason the کلیات-only gates are:
# the table above is evidence about ONE book, and a table of one book's
# dedications must never be consulted for another's.
GATHERED_COLLECTIONS: dict[str, dict[str, tuple[str, str]]] = {
    "kulliyat-jild-1": KULLIYAT_JILD_1_COLLECTIONS,
}


def attribute_gathered_collections(
    segments: list[Segment], table: dict[str, tuple[str, str]],
) -> tuple[list[tuple[int, str]], list[str]]:
    """Stamp each piece with the collection whose title page last preceded it.

    Mutates `segments` — `Segment.collection`, the same field جلد ۲ fills from
    its running headers, so `emit.resolve_book_records` writes one book record
    per gathered book with no change of its own.

    The title-page block itself is left UNATTRIBUTED, deliberately. It is an
    imprint and a dedication, not a poem of the book it opens: four of the six
    blocks segment as `nazms` and one as `ghazals`, so attributing them would
    both put a title page into a book record's contents as if it were poetry
    and add one to each collection's count — عناصر would read 101 against the
    100 its own فہرست declares. Left unattributed they stay staged, still
    flagged, still readable in the report, and out of every contents list.

    Returns `(boundaries, problems)`: `boundaries` is `(order, name)` per
    block in book order, with `name` empty when the table does not attest
    one, and `problems` names each such block for the report.

    An empty `table` is a no-op — تجاوز, باغِ نشاط and کلیات جلد ۲ are not
    gatherings delimited this way, and nothing here may touch what جلد ۲ read
    off its running headers.
    """
    if not table:
        return [], []
    by_dedication = {
        skeleton(dedication): name for dedication, (name, _) in table.items()
    }
    boundaries: list[tuple[int, str]] = []
    problems: list[str] = []
    current = ""
    for piece in segments:
        dedication = collection_boundary_dedication(piece)
        if not dedication:
            piece.collection = current
            continue
        current = by_dedication.get(skeleton(dedication), "")
        boundaries.append((piece.order, current))
        piece.collection = ""
        # A title page is not a poem of the book it opens. Left unattributed
        # it already stays out of every contents list and every count, but it
        # is still a `nazms` or `ghazals` piece and would publish as poetry:
        # an imprint, a dedication to the poet's parents, and an epigraph
        # couplet, presented as three poems of موسم.
        if TITLE_PAGE_FLAG not in piece.flags:
            piece.flags.append(TITLE_PAGE_FLAG)
        if not current:
            problems.append(
                f"the title page at order {piece.order} (dedication "
                f"{dedication!r}) matches no entry in this volume's "
                f"collection table, so the poems after it are left "
                f"UNATTRIBUTED — an unnamed collection is truthful, a "
                f"guessed name is not. Add the entry, with its evidence, to "
                f"segment.KULLIYAT_JILD_1_COLLECTIONS."
            )
    return boundaries, problems


def _position_collection(
    natural: str,
    last_index: int,
    first_header_index: int | None,
    first_header_name: str,
) -> tuple[str, bool]:
    """Backfill a piece's collection from the book's very first running header.

    A running header only ever names the collection from its own page
    onward, so a piece with a natural (non-empty) collection already has
    real evidence and is left alone. A piece with none has none because no
    earlier header exists in the volume to have supplied one — کلیات جلد
    ۲'s 82 opening poems, whose first running header does not appear until
    paragraph 1150 — and the fix is to give it the first header that DOES
    appear, since there is no earlier one to be wrong about.

    Guarded on the piece's own LAST paragraph, not its first: a piece whose
    run continues past that first header (split_ghazals failed to separate
    two collections' poems at the seam, exactly the fixture in
    TestRunningHeadersInAssembly) must keep "" rather than being stamped
    with a header its own earlier lines never saw — that is the same
    "last header wins" bug this fix must not reintroduce by another route.
    """
    if natural or first_header_index is None or last_index >= first_header_index:
        return natural, False
    return first_header_name, True


def segment(
    paragraphs: list[Paragraph],
    dropped_unknowns: list[str] | None = None,
    unreached: list[tuple[str, Paragraph]] | None = None,
    position_attributed: list[Segment] | None = None,
    gathered_collections: dict[str, tuple[str, str]] | None = None,
    collection_boundaries: list[tuple[int, str]] | None = None,
    collection_boundary_problems: list[str] | None = None,
    sections: Iterable[str] = (),
    prose_titles: Iterable[str] = (),
    explicit_pieces: bool = False,
) -> list[Segment]:
    """Assemble classified paragraphs into pieces.

    Heuristic by construction — output goes to staging behind a review report,
    never straight to content/. Nothing is ever dropped: an unpaired line is
    flagged, and a run that fits no pattern still becomes a piece.

    `section` is taken only from a HEADING that sits at or after
    `body_start_index`. A heading before it belongs to the فہرست, which
    lists the book's section names before any poem has been reached; reading
    those as sections gave تجاوز a غزلیں label on all 101 pieces that was
    correct only by coincidence. Pieces formed before the first body heading
    are marked `precedes_first_heading` so the count gate can exclude them
    without depending on the section string.

    `UNKNOWN` paragraphs are the one exception worth naming: each is held as
    `title_candidate` on the chance a nazm immediately follows it with no
    title of its own, but a candidate that is overwritten by a later UNKNOWN,
    or that is still pending when a review/ghazal/EOF makes it moot, reaches
    no piece at all — it is not retained anywhere in the return value. This
    is unchanged behaviour, not a new bug: `dropped_unknowns`, if given a
    list, is appended with the text of every such paragraph so a caller (see
    `cmd_segment`) can surface the count instead of it vanishing silently.

    `unreached` is the general form of that same accounting and is what a
    caller should prefer: given a list, it is appended with `(kind,
    paragraph)` for every paragraph whose text reached no piece at all,
    whatever its kind. Some of that is legitimate — the title page, the
    فہرست, the ۰۰۰ separators, a section heading that becomes `section`
    metadata — but a poem's line appearing there is the loss this pipeline
    exists to prevent, and it was invisible until the count was reported.

    `position_attributed`, given a list, is appended with every piece whose
    `collection` was not read off a running header at all but backfilled
    from the book's first one, because no earlier header exists in the
    volume to have supplied it (see `_position_collection`). This is
    attribution by position, not by the source naming it, and a caller
    (`cmd_segment`) reports the count rather than letting it look identical
    to an ordinary header read.

    `gathered_collections`, given a table (see `GATHERED_COLLECTIONS`),
    re-stamps every piece's `collection` from the volume's own title pages
    (see `attribute_gathered_collections`) before returning — the same step
    `cmd_segment` used to run itself, after calling this function, as a
    second pass over its result. Doing it here instead of there is the
    point: a caller that reaches `segment()` directly — a test, a gate, a
    diagnostic — used to see collections attributed by running header alone
    (کلیات جلد ۱'s موسم backfilled into عناصر, 231 poems where the volume's
    own فہرست declares 100) while `cmd_segment`'s own staged output, one
    step later, told a different story for the same book. Passing the table
    here means there is only one place collections are decided, and every
    caller sees what the pipeline stages. Left `None` (the default), no
    re-stamping happens at all — correct for the three books in the corpus
    that are not gatherings this way, and for any caller measuring the raw
    header-only reading on purpose (see
    `TestKulliyatJild1Collections.test_the_headers_alone_still_cannot_name_موسم`).

    When a table is given, `position_attributed` (if also given) is cleared
    before returning: every piece has just been re-stamped from the title
    pages, so nothing in the book carries a collection attributed by
    position any more, and leaving stale entries there would report موسم's
    130 poems as "attributed by POSITION" when the volume's own title page
    names them.

    `collection_boundaries` and `collection_boundary_problems`, each given a
    list, receive `attribute_gathered_collections`'s two return values — the
    title pages found, in order, and any dedication the table could not
    name. Both are no-ops when `gathered_collections` is `None` or empty.
    """
    if dropped_unknowns is None:
        dropped_unknowns = []
    # Held as (index, text) rather than appended straight to
    # `dropped_unknowns`: an UNKNOWN that looked moot when it was overwritten
    # can still be swept up by an essay region that starts before it, and
    # reporting it as dropped after it reached a piece would be a false
    # alarm. Reconciled against `consumed` at the end.
    pending_drops: list[tuple[int, str]] = []
    headings = heading_map(sections)
    kinds = classify(paragraphs, sections)
    collections = collections_at(paragraphs, kinds)
    # The book's very first running header, if it has one at all — see
    # `_position_collection`. تجاوز, باغِ نشاط and کلیات جلد ۱ have none, so
    # this stays None and nothing below ever fires for them.
    first_header_index = next(
        (i for i, k in enumerate(kinds) if k == RUNNING_HEADER), None
    )
    first_header_name = (
        paragraphs[first_header_index].text if first_header_index is not None else ""
    )
    body_start = body_start_index(paragraphs)
    pieces: list[Segment] = []
    section = ""
    # `section` persists until the next heading, and in a کلیات volume that
    # can be several collections later: عناصر's last section خواب was
    # inherited by all 93 pieces of کتابِ صبح, and موسم's قدیم by the first
    # three of عناصر. A section never crosses a collection boundary — the
    # next collection has its own sections or none.
    #
    # Which collection a heading belongs to cannot be read at the heading:
    # موسم is never named by a page header before its poems, so its pieces
    # are re-stamped from the volume's title pages AFTER assembly. What is
    # stable either way is the FIRST PIECE the heading governs, so each
    # piece records that piece's order and the comparison is made below,
    # once every collection is final.
    section_owner = 0
    section_owner_of: dict[int, int] = {}
    # How many pieces had already been formed when the first BODY heading was
    # reached, or None if the book has no body heading at all. Those pieces
    # precede every section the book declares (باغِ نشاط's epigraph couplet
    # is the one real instance), and `precedes_first_heading` is stamped onto
    # them once the whole book has been read — at add() time there is no way
    # to know whether a heading is still coming.
    pieces_before_first_heading: int | None = None
    title_candidate = ""
    title_candidate_index = -1
    # Every paragraph index whose text reached a piece — body, title or
    # written_note. What is left over is reported through `unreached`.
    consumed: set[int] = set()
    # A COLOPHON reaching the front of the book, before any piece has been
    # formed, has nothing to attach to yet (see the COLOPHON branch below).
    # Held here rather than dropped, and attached to the first piece add()
    # creates, whatever kind it turns out to be.
    pending_colophon = ""
    pending_colophon_index = -1
    # The paragraph just after the last structural boundary (۰۰۰, a فہرست
    # line, a section heading), and the end of the last piece formed. An
    # essay region starts at whichever is later: the boundary tells us where
    # the essay's own heading lines begin, and the piece end stops a region
    # from reaching back over verse already emitted.
    boundary = 0
    emitted_end = 0

    def add(
        kind: str, title: str, body: str, flags: list[str], collection: str,
    ) -> Segment:
        nonlocal pending_colophon, pending_colophon_index, section_owner
        if len(title) > MAX_TITLE_LENGTH:
            flags = flags + ["over-long-title"]
        piece = Segment(
            kind=kind,
            title=title,
            body=body,
            order=len(pieces) + 1,
            section=section,
            collection=collection,
            flags=flags,
        )
        if pending_colophon:
            piece.written_note = pending_colophon
            consumed.add(pending_colophon_index)
            pending_colophon = ""
            pending_colophon_index = -1
        if section:
            if not section_owner:
                section_owner = piece.order
            section_owner_of[piece.order] = section_owner
        pieces.append(piece)
        return piece

    index = 0
    while index < len(paragraphs):
        kind = kinds[index]
        para = paragraphs[index]

        if kind == RUNNING_HEADER:
            # Page furniture: it names the collection (already captured for
            # every paragraph by `collections`, computed up front) and forms
            # no piece of its own. It does END the verse run it interrupts —
            # see the VERSE branch below for the measurement.
            index += 1
            continue

        if kind == HEADING:
            # Only a heading inside the body names a section. Before the body
            # start the same words are the فہرست listing its own section
            # names, and taking `section` from there labelled whole books off
            # a table of contents: تجاوز's only two headings are at
            # paragraphs 1 and 16 against a body start of 85, and all 101 of
            # its pieces inherited غزلیں from them. That label happened to be
            # right, but nothing in the evidence said so.
            if index >= body_start:
                section = headings[skeleton(para.text)]
                section_owner = 0
                if pieces_before_first_heading is None:
                    pieces_before_first_heading = len(pieces)
            boundary = index + 1
            index += 1
            continue

        if kind == COLOPHON:
            if pieces:
                # A second colophon attaching to the same piece is appended,
                # not overwritten — the same "never drop it" rule as
                # pending_colophon below. No book in the corpus today has
                # adjacent colophons, so this path is covered by a synthetic
                # test rather than a measured one.
                current = pieces[-1].written_note
                pieces[-1].written_note = (
                    f"{current} {para.text}" if current else para.text
                )
                consumed.add(index)
            else:
                # Nothing exists yet to attach this to. Never drop it: hold
                # it until add() creates the next piece.
                pending_colophon = para.text
                pending_colophon_index = index
            index += 1
            continue

        if kind == UNKNOWN:
            # A dedication belongs to the poem above it. `classify` refuses to
            # bridge one into a verse run — bridging paired `(نذرِ سوداؔ)`
            # with the maqtaa's closing misra and tore اِعادہ's
            # باغِ سبز مرا ghazal in two — so it arrives here instead, right
            # after the piece it was set under.
            if pieces and DEDICATION.match(para.text.strip()):
                pieces[-1].dedication = para.text.strip()
                consumed.add(index)
                index += 1
                continue
            # A candidate still pending when a new one arrives never reached
            # a piece — see the docstring's note on dropped_unknowns.
            if title_candidate:
                pending_drops.append((title_candidate_index, title_candidate))
            title_candidate = para.text
            title_candidate_index = index
            index += 1
            continue

        if kind == PROSE:
            start, end = _essay_region(
                kinds, index, boundary, emitted_end, body_start
            )
            # The review takes the collection in force at its own first
            # paragraph — `collections`, precomputed once up front, already
            # accounts for any running header inside the region (the
            # critic's quotations span pages too) without needing to be
            # walked again here. Backfilled from the book's first header
            # only when the whole region ends before it (see
            # `_position_collection`).
            review_collection, attributed = _position_collection(
                collections[start], end - 1, first_header_index, first_header_name,
            )
            piece = _add_review(
                add, paragraphs[start:end], kinds[start:end], index, paragraphs,
                review_collection, frozenset(prose_titles),
            )
            if attributed and position_attributed is not None:
                position_attributed.append(piece)
            consumed.update(
                i for i in range(start, end) if kinds[i] != RUNNING_HEADER
            )
            if title_candidate:
                pending_drops.append((title_candidate_index, title_candidate))
            title_candidate = ""
            title_candidate_index = -1
            emitted_end = end
            index = end
            continue

        if kind == VERSE:
            start = index
            # A RUNNING_HEADER ends the run. It used to be read through, on
            # the reasoning that 972 of them in کلیات vol 2 would cut a
            # ghazal at every page turn — but that count is of the whole
            # book, and almost all of it is the back-of-book فہرست, where
            # each index line prints its collection's name. Measured where
            # it matters, a header sits BETWEEN two verse paragraphs 4 times
            # in کلیات جلد ۱ (عناصر، کتابِ صبح، معاملہ، روداد) and twice in
            # جلد ۲ (نیند میں چلتے ہوئے، چہار دریا) — six sites in the whole
            # corpus, and every one of them is a collection's title page,
            # exactly where a piece must end. Reading through them welded
            # موسم's last ghazal onto عناصر's title page (which then took
            # the ghazal's own کے لیے radif for عناصر's dedication and lost
            # the attribution of all 100 of its poems) and welded the نظم
            # جادو onto نیند میں چلتے ہوئے's title poem.
            # `explicit_pieces` is set for a source that marks its own piece
            # boundaries — InPage 3 sets an ornament between poems, and a
            # blank line between shers. There a running header really is
            # nothing but page furniture: اِعادہ prints an …… ornament at the
            # top of all 104 of its pages, and breaking the run at each one
            # cut a ghazal at every page turn. In an InPage 1 کلیات the same
            # kind is evidence of a collection's title page, which is exactly
            # where a piece must end — so the two must not share a rule.
            while index < len(paragraphs) and (
                kinds[index] == VERSE
                or (explicit_pieces and kinds[index] == RUNNING_HEADER)
            ):
                index += 1
            # `run` and `run_collections` are built in the same pass, kept
            # parallel: `split_ghazals` returns groups of shers, each 1 or 2
            # lines long, and a cursor stepping over `run_collections` in
            # lockstep with those groups is what lets each piece take the
            # collection where its OWN first line sits, rather than the
            # collection in force once the whole run has been scanned.
            # Built in one pass so all three stay parallel. Only under
            # `explicit_pieces` can the span hold anything but VERSE — a page
            # ornament read through — and dropping those from `run` alone
            # would shift the cursor that walks the other two, giving each
            # piece the collection and source position of a different piece.
            keep = [
                i for i in range(start, index) if kinds[i] == VERSE
            ]
            run: list[Paragraph] = [paragraphs[i] for i in keep]
            run_collections: list[str] = [collections[i] for i in keep]
            run_indices: list[int] = keep
            if _is_ghazal_shaped(run):
                # A ghazal is titled by its matlaa, never by title_candidate —
                # a pending candidate here is moot and reaches no piece.
                if title_candidate:
                    pending_drops.append(
                        (title_candidate_index, title_candidate)
                    )
                cursor = 0
                # Orphans are rejoined BEFORE the run is split into ghazals,
                # so a maqtaa whose second misra lost its geometry marker is
                # one sher everywhere downstream: `split_ghazals` no longer
                # has to read that bare second misra as a candidate matlaa,
                # the ghazal's rhyme is measured with it included, and the
                # line-count cursor below counts it as the two lines it is.
                # Where the source states its own boundaries there is nothing
                # for rhyme to find: اِعادہ's ornament already says where each
                # of its hundred poems ends, and splitting again on rhyme took
                # it to 204.
                shers = merge_orphan_shers(pair_shers(run))
                groups = [shers] if explicit_pieces else split_ghazals(shers)
                for group in groups:
                    # `group_end` counts the lines the SOURCE holds, so it is
                    # taken before the dedication is lifted out of the body —
                    # the cursor walks the run's own lines and must not skip
                    # one just because it stopped being verse.
                    group_end = cursor + sum(
                        2 if second else 1 for _, second in group
                    )
                    group, dedication = _lift_dedication(group)
                    flags = ["half-sher"] if any(not s[1] for s in group) else []
                    # Backfilled from the book's first header only when
                    # THIS group's own last line still precedes it — a
                    # group whose text runs past the header keeps its
                    # natural collection (see `_position_collection`).
                    piece_collection, attributed = _position_collection(
                        run_collections[cursor], run_indices[group_end - 1],
                        first_header_index, first_header_name,
                    )
                    cursor = group_end
                    piece = add(
                        "ghazals", group[0][0], _ghazal_body(group), flags,
                        piece_collection,
                    )
                    piece.dedication = dedication
                    if attributed and position_attributed is not None:
                        position_attributed.append(piece)
            else:
                title = title_candidate or run[0].text
                if title_candidate:
                    consumed.add(title_candidate_index)
                piece_collection, attributed = _position_collection(
                    run_collections[0], run_indices[-1],
                    first_header_index, first_header_name,
                )
                piece = add(
                    "nazms", title, "\n".join(p.text for p in run), [],
                    piece_collection,
                )
                if attributed and position_attributed is not None:
                    position_attributed.append(piece)
            consumed.update(range(start, index))
            title_candidate = ""
            title_candidate_index = -1
            emitted_end = index
            continue

        if kind in (SEPARATOR, TOC):
            boundary = index + 1
        index += 1

    # A candidate still pending at end of book (paragraphs ran out right
    # after the last UNKNOWN) never reached a piece either.
    if title_candidate:
        pending_drops.append((title_candidate_index, title_candidate))

    if pieces_before_first_heading is not None:
        for piece in pieces[:pieces_before_first_heading]:
            piece.precedes_first_heading = True

    dropped_unknowns.extend(
        text for i, text in pending_drops if i not in consumed
    )
    if unreached is not None:
        unreached.extend(
            (kinds[i], para)
            for i, para in enumerate(paragraphs)
            if i not in consumed
        )
    if gathered_collections:
        boundaries, problems = attribute_gathered_collections(
            pieces, gathered_collections
        )
        if collection_boundaries is not None:
            collection_boundaries.extend(boundaries)
        if collection_boundary_problems is not None:
            collection_boundary_problems.extend(problems)
        if position_attributed is not None:
            position_attributed.clear()
    # Every collection is final now, so a section can be checked against the
    # collection its heading actually governed (see `section_owner_of`).
    by_order = {piece.order: piece for piece in pieces}
    for piece in pieces:
        owner = section_owner_of.get(piece.order)
        if owner and by_order[owner].collection != piece.collection:
            piece.section = ""
    return pieces


def segment_book(book_slug: str, paragraphs: list[Paragraph], **kwargs):
    """Segment `paragraphs` with everything known about `book_slug`.

    The one place a book's per-book arguments are assembled. They used to be
    assembled in `cmd_segment` alone, so a direct `segment()` call — a test,
    a gate, a diagnostic — silently ran a DIFFERENT segmentation: first over
    `gathered_collections` (a direct call reported عناصر with 231 poems
    where the pipeline staged 100), and again over `sections`, where the
    pipeline read موسم's six section title pages as headings and a direct
    call read them as verse.

    Both tables are keyed by slug and default to empty, so a book neither
    names is segmented exactly as it was before either existed.
    """
    return segment(
        paragraphs,
        gathered_collections=GATHERED_COLLECTIONS.get(book_slug, {}),
        sections=SECTION_NAMES_BY_BOOK.get(book_slug, ()),
        prose_titles=PROSE_TITLES_BY_BOOK.get(book_slug, ()),
        **kwargs,
    )


def _essay_region(
    kinds: list[str],
    prose_index: int,
    boundary: int,
    emitted_end: int,
    body_start: int,
) -> tuple[int, int]:
    """The half-open span of paragraphs the essay at `prose_index` occupies.

    Bounded structurally, not by the prose run: the critic quotes the poet
    throughout, and each quotation is verse sitting before the first ghazal,
    where classify() can only call it FRONT_MATTER. Taking the prose run
    alone therefore stopped at the first quotation, dropped it, and started a
    fresh fragment after it — تجاوز's essay became 5 pieces and lost 5 lines,
    باغِ نشاط's became 10 and lost ~50.

    The span runs from the last structural boundary (so the essay's title and
    author lines come with it) to the next one, never past the body start and
    never back over paragraphs already emitted.
    """
    start = max(boundary, emitted_end)
    end = prose_index
    while end < len(kinds) and kinds[end] not in REGION_CLOSE_KINDS:
        end += 1
    if body_start > prose_index:
        end = min(end, body_start)
    return start, end


# A critic's opinion closes with its own attribution: the critic's name and,
# in the book's own ‘‘…’’ quotes, which collection they are writing about.
# `(مرزا حامد بیگ- ‘‘موسم’’)`, `(شمس الرحمن فاروقی- ‘‘آیندہ’’)`.
ATTRIBUTION = re.compile(r"^\(\s*(?P<who>[^‘]+?)\s*[-–—]?\s*‘‘(?P<book>[^’]+)’’\s*\)$")

# How many attributions make a region an anthology rather than an essay that
# happens to cite someone. Measured across all four books: exactly one region
# carries any at all — کلیات جلد ۱'s آرا, with ten — and every other essay in
# every book has zero. Three is well clear of both.
ANTHOLOGY_MIN_ATTRIBUTIONS = 3


def _attribution(line: str) -> tuple[str, str] | None:
    """`(critic, book)` if this line closes a critic's opinion."""
    match = ATTRIBUTION.match(line.strip())
    if not match:
        return None
    return match.group("who").strip(), match.group("book").strip()


from .classify import DEDICATION  # noqa: E402  (kept beside its use)


def _lift_dedication(
    group: list[tuple[str, str]]
) -> tuple[list[tuple[str, str]], str]:
    """Take a trailing `(نذرِ …)` out of a ghazal's body and return it.

    Three ghazals in جلد ۱ close on a tribute — to غالب, to فراقؔ, to دردؔ.
    Each is a short bracketed line, so `pair_shers` had nothing to pair it
    with and the poem ended on a half sher: a flag saying a misra was
    missing, when nothing was missing at all.

    Lifted rather than dropped. The poet chose to dedicate these three, and
    the site shows it under the poem the way it already shows the colophon.
    """
    if len(group) < 2:
        return group, ""
    first, second = group[-1]
    if second or not DEDICATION.match(first.strip()):
        return group, ""
    return group[:-1], first.strip()


def _split_anthology(
    add,
    region: list[Paragraph],
    region_kinds: list[str],
    collection: str,
) -> list[Segment] | None:
    """Emit one piece per critic where a region is an anthology of opinions.

    کلیات جلد ۱ closes with آرا — ten critics on the poet's books, each
    opinion signed with its author and the collection it discusses. Staged as
    one region it is a single unbrowsable page; split, each is a piece by a
    named critic about a named book, which is what the archive's `reviews`
    collection is for. شمس الرحمن فاروقی on آیندہ becomes something you can
    link to.

    Returns None where the region is an ordinary essay, so every other essay
    in every book takes the untouched path.

    Whatever follows the last attribution is emitted as its own piece: in this
    book that is تعارف, the poet's life and bibliography, which the printed
    index lists as a separate section and which no attribution closes.
    """
    # Walked with the kinds alongside, not over the flattened body, so each
    # date attaches to the opinion it actually closes. Two of the ten carry
    # no date at all; taking the colophons in order and handing them out one
    # per piece put every date on the wrong critic.
    kept = [
        (para.text, kind)
        for para, kind in zip(region, region_kinds)
        if kind != RUNNING_HEADER
    ]
    if sum(1 for text, _ in kept if _attribution(text)) < ANTHOLOGY_MIN_ATTRIBUTIONS:
        return None

    pieces: list[Segment] = []
    lines: list[str] = []
    dates: list[str] = []

    def flush(title: str, author: str, book: str) -> None:
        body = [line for line in lines if line.strip()]
        if not body:
            return
        piece = add(
            "reviews", (title or body[0])[:MAX_TITLE_LENGTH],
            "\n\n".join(body), [], collection,
        )
        piece.reviewed_author = author
        piece.reviewed_book = book
        piece.written_note = " ".join(dates)
        pieces.append(piece)

    for text, kind in kept:
        if kind == COLOPHON:
            # A critic dates their opinion BELOW their signature, so a date
            # arriving with nothing yet gathered closes the piece just
            # emitted rather than opening the next one. Getting this wrong
            # shifted every date by one critic — and two of the ten are
            # undated, so the error did not even stay a constant offset.
            if not lines and pieces:
                pieces[-1].written_note = (
                    f"{pieces[-1].written_note} {text}".strip()
                )
            else:
                dates.append(text)
            continue
        signed = _attribution(text)
        # The attribution itself stays in the body: it is how the book prints
        # the piece, and dropping a critic's signature would be editing them.
        lines.append(text)
        if signed:
            flush(signed[0], signed[0], signed[1])
            lines, dates = [], []

    # Whatever follows the last attribution: in this book تعارف, which the
    # printed index lists as its own section and which no attribution closes.
    flush("", "", "")
    return pieces


def _add_review(
    add,
    region: list[Paragraph],
    region_kinds: list[str],
    prose_index: int,
    paragraphs: list[Paragraph],
    collection: str,
    prose_titles: frozenset[str] = frozenset(),
) -> Segment:
    """Emit one `reviews` piece for a whole essay region, in source order."""
    # A running header inside the region is page furniture, exactly as it
    # is everywhere else — it names the collection (already resolved by the
    # caller, from where the region itself starts) and must not become
    # literal essay text.
    body_lines = [
        p.text for p, k in zip(region, region_kinds)
        if k not in (COLOPHON, RUNNING_HEADER)
    ]
    anthology = _split_anthology(add, region, region_kinds, collection)
    if anthology:
        return anthology[0]

    first_prose = next(
        (i for i, k in enumerate(region_kinds) if k == PROSE), 0
    )
    heading_lines = [
        p.text
        for p, k in zip(region[:first_prose], region_kinds[:first_prose])
        if k not in (COLOPHON, RUNNING_HEADER)
    ]
    # موسم's پیش لفظ opens straight after the collection's title page, with
    # only a separator before the title page and nothing between the two. The
    # region therefore begins at the title page and the essay's heading lines
    # arrive with the imprint, the dedication and the epigraph couplet in
    # front of them — so the block read as a title page, and refusing title
    # pages refused محمد خالد's criticism with it.
    #
    # Where the printed index's name for the essay appears among those
    # heading lines, everything before it is the title page and is emitted as
    # its own piece. Only the FIRST such line counts, and only when something
    # precedes it: every other essay in the book already starts at its own
    # title, and must take the untouched path.
    opens_at = next(
        (
            i for i, line in enumerate(heading_lines)
            if i and line.strip() in prose_titles
        ),
        0,
    )
    if opens_at:
        title_page = add(
            "nazms", heading_lines[0][:MAX_TITLE_LENGTH],
            "\n".join(heading_lines[:opens_at]), [TITLE_PAGE_FLAG], "",
        )
        del title_page
        body_lines = body_lines[opens_at:]
        heading_lines = heading_lines[opens_at:]
    title, author, resolved = _split_byline(heading_lines)
    if not title:
        title = paragraphs[prose_index].text
    flags = [] if resolved or not heading_lines else [BYLINE_FLAG]
    piece = add(
        "reviews", title[:MAX_TITLE_LENGTH], "\n\n".join(body_lines), flags,
        collection,
    )
    piece.reviewed_author = author
    for p, k in zip(region, region_kinds):
        if k != COLOPHON:
            continue
        piece.written_note = (
            f"{piece.written_note} {p.text}" if piece.written_note else p.text
        )
    return piece


def pair_shers(run: list[Paragraph]) -> list[tuple[str, str]]:
    """Pair a verse run into shers using the recorded second-misra geometry.

    A trailing line with no partner is returned with an empty second misra
    rather than discarded — losing a line of poetry is never acceptable, and
    the caller flags the half sher for review.
    """
    shers: list[tuple[str, str]] = []
    index = 0
    while index < len(run):
        first = run[index]
        if (
            index + 1 < len(run)
            and run[index + 1].geometry == SECOND_MISRA_GEOMETRY
        ):
            shers.append((first.text, run[index + 1].text))
            index += 2
        else:
            shers.append((first.text, ""))
            index += 1
    return shers


def merge_orphan_shers(
    shers: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Rejoin two adjacent half shers into the one sher they were.

    `pair_shers` reads the second misra off `geometry == 1`, and some second
    misras in the source simply do not carry the marker. The line then pairs
    with nothing, its partner pairs with nothing either, and one couplet is
    emitted as two half shers side by side.

    Measured across the whole corpus, every such adjacency is one sher: کلیات
    جلد ۲ has 45 of them and باغِ نشاط 1, and all 46 sit at the very last
    position of their ghazal, 44 of them carrying the takhallus ساجدؔ. They
    are maqtaas — the closing sher — whose second misra lost its marker. There
    is not one mid-poem adjacency anywhere in the four books, so the rule is
    stated generally (two adjacent half shers are one sher) rather than
    restricted to the close: nothing in the evidence contradicts it, and a
    positional restriction would only be a guess about text not yet seen.

    Merging is greedy and left to right, the same discipline `pair_shers`
    itself follows: three half shers in a row become one sher and one half
    sher, and the odd line out stays flagged rather than being welded onto a
    couplet it does not belong to. A lone half sher is left exactly as it is —
    a genuinely single line is a real thing (a فرد, a truncated poem) and must
    keep reaching the reviewer.

    No line is ever moved between shers or dropped; the merged sher holds both
    original lines verbatim, in order.

    Deliberately NOT applied inside `_is_ghazal_shaped`. That gate measures
    how cleanly a run pairs in order to tell a ghazal from a nazm, and a
    nazm's run is mostly half shers — merging them pairwise first would score
    every nazm 100% clean and file the whole lot as ghazals.
    """
    merged: list[tuple[str, str]] = []
    index = 0
    while index < len(shers):
        first, second = shers[index]
        if (
            not second
            and index + 1 < len(shers)
            and not shers[index + 1][1]
        ):
            merged.append((first, shers[index + 1][0]))
            index += 2
        else:
            merged.append((first, second))
            index += 1
    return merged


def _rhyme_key(text: str) -> str:
    """The form a rhyme is compared in: letters only, sound-folded."""
    return FINAL_HE.sub("ا", skeleton(text).translate(RHYME_FOLD))


def _common_suffix(left: str, right: str) -> str:
    count = 0
    while (
        count < len(left)
        and count < len(right)
        and left[-1 - count] == right[-1 - count]
    ):
        count += 1
    return left[len(left) - count:] if count else ""


def _shared_rhyme(lines: list[str]) -> str:
    if not lines:
        return ""
    rhyme = lines[0]
    for line in lines[1:]:
        rhyme = _common_suffix(rhyme, line)
    return rhyme.lstrip()


def run_rhyme(shers: list[tuple[str, str]], index: int) -> str:
    """The qafia+radif the run starting at `index` shares, or "".

    Read from the SECOND misras — the only lines every sher of a ghazal
    rhymes on — of this sher and the few that follow it. Established forward
    like this, the rhyme belongs to the ghazal being opened rather than to the
    candidate sher alone, which is what stops an ordinary sher whose first
    misra happens to end on a common word (ہے, سے, تھا) from reading as an
    opening.

    At the end of a run there is nothing to look ahead to. There the sher's
    own two misras are used, which is the self-contained test — measured as
    changing no piece count in either pilot book, since it can apply at most
    once per verse run.
    """
    seconds = [
        _rhyme_key(second) for _, second in shers[index:index + RHYME_WINDOW]
        if second
    ]
    if len(seconds) >= 2:
        return _shared_rhyme(seconds)
    first, second = shers[index]
    return _common_suffix(_rhyme_key(first), _rhyme_key(second)).lstrip()


def is_matla(first: str, second: str, rhyme: str | None = None) -> bool:
    """True when the first misra ends in the ghazal's rhyme — a matlaa.

    Only the matlaa rhymes across both its lines; every later sher rhymes on
    the second line alone. `rhyme` is the run's established qafia+radif (see
    `run_rhyme`); passing None falls back to whatever the pair itself shares,
    which is the older self-contained reading.
    """
    if not first or not second:
        return False
    if rhyme is None:
        rhyme = _common_suffix(_rhyme_key(first), _rhyme_key(second)).lstrip()
    if len(rhyme) < MIN_RHYME:
        return False
    return _rhyme_key(first).endswith(rhyme)


def _same_zameen(established: str, opening: str) -> bool:
    """True when two rhymes are the same zameen, one merely stated longer.

    A group of one or two shers has not yet worn its accidental letters away,
    so its rhyme reads longer than the ghazal's real one (a lone سنگ سے before
    ترنگ سے and انگ سے reduce it to نگ سے). Either being a suffix of the other
    means they are the same rhyme seen at two resolutions.
    """
    return bool(established) and bool(opening) and (
        established.endswith(opening) or opening.endswith(established)
    )


def _is_maqta(sher: tuple[str, str]) -> bool:
    return any(TAKHALLUS in _rhyme_key(misra) for misra in sher if misra)


# How many shers must agree before a group's rhyme is settled enough to
# convict a later sher of abandoning it. Below three, the shared suffix is
# still carrying accidental letters — the same effect `_same_zameen`
# describes — and a legitimate qafia change reads as the ghazal ending.
SETTLED_SHERS = 3

# A trailing group this short, carrying the maqtaa, after a group carrying
# none, is that group's ending rather than a poem — see `_rejoin_maqta_tails`.
MAQTA_TAIL = 2


def _rhyme_exhausted(
    current: list[tuple[str, str]], second: str
) -> bool:
    """True when this sher leaves the ghazal so far with no rhyme at all.

    Every sher of a ghazal rhymes; when one stops, the ghazal has ended.
    `split_ghazals` only ever STARTED a group, at a matlaa, and never ended
    one, so a ghazal whose successor opens on a single-letter qafia ran
    straight on into it: موسم's برشگال ran two ghazals together across a ر
    rhyme, زمہریر and قدیم across ے. Those openings cannot be caught by
    `is_matla`, whose MIN_RHYME floor of 2 exists to stop ordinary shers
    ending on ہے or سے from reading as matlaas — and lowering it fires 31
    false openings in جلد ۱ alone. The evidence at those joins is not the
    weak new rhyme but the strong old one running out.

    The test is on what SURVIVES, not on what matches. Comparing the sher
    against the group's established suffix convicts a legitimate qafia
    change — سنگ سے، رنگ سے، دل سے share only سے, and a sher failing to end
    in نگ سے is still in the ghazal. Asking instead whether the group has
    any rhyme LEFT once the sher joins separates the two cleanly: a qafia
    change leaves the radif standing, a new ghazal leaves nothing. Measured
    both ways — the matching form moves تجاوز (+3) and باغِ نشاط (+4), both
    promoted; this one moves neither.
    """
    if len(current) < SETTLED_SHERS or not second:
        return False
    keys = [_rhyme_key(s) for _, s in current if s]
    if len(_shared_rhyme(keys)) < MIN_RHYME:
        return False
    return len(_shared_rhyme(keys + [_rhyme_key(second)])) < MIN_RHYME


def _rhyme_is_forward(shers: list[tuple[str, str]], index: int) -> bool:
    """True when `run_rhyme` read this rhyme from the shers that FOLLOW.

    At the end of a run there is nothing to look ahead to and `run_rhyme`
    falls back to the candidate sher's own two misras, which over-reads: four
    shers rhyming شمس give ر شمس for the last one, because its two misras
    happen to share the ر before it. That reading is too weak to REFUSE a
    husn-e-matlaa on, so `_carries` is asked only where the rhyme was
    established forward.
    """
    return len([s for _, s in shers[index:index + RHYME_WINDOW] if s]) >= 2


def _carries(current: list[tuple[str, str]], rhyme: str) -> bool:
    """True when the ghazal so far already rhymes the way `rhyme` does.

    The husn-e-matlaa test asks whether an opening sher opens on the rhyme
    the current ghazal is ALREADY in. `_same_zameen` answers that from the
    group's shared suffix, and that suffix degenerates: کتابِ صبح's
    ¬375 ghazal rhymes شک ہے، اجرک ہے، حق ہے، تک ہے، ٹھنڈک ہے, whose common
    suffix is not ک ہے but a bare ہے — the qafia varies too much to survive
    the intersection. Any new ghazal ending ہے then looks like the same
    zameen, and ¶376's وری ہے ghazal was swallowed whole by ¶375's.

    Asking instead whether any sher ALREADY WRITTEN ends on that rhyme
    restores what the test meant. A husn-e-matlaa is a second opening on the
    ghazal's own rhyme, so the shers around it carry it by definition; a new
    poem's rhyme appears for the first time at its matlaa. تجاوز's
    وحشت ہے / محبّت ہے inside the قیامت ہے ghazal still reads as husn — the
    ghazal's own shers end ت ہے — and both promoted books come out
    byte-identical.
    """
    if not rhyme:
        return False
    return any(
        _rhyme_key(second).endswith(rhyme) for _, second in current if second
    )


def _rejoin_maqta_tails(
    groups: list[list[tuple[str, str]]],
) -> list[list[tuple[str, str]]]:
    """Give back a tail that is only a maqtaa cut off its own ghazal.

    A ghazal does not end two shers before its takhallus. عناصر's مٹّی
    ghazal rhymes میری مٹی سے and closes میری مٹی ہے — the same zameen with
    a different final particle, which `_rhyme_exhausted` cannot see because
    a common-SUFFIX test collapses to ے when the difference sits at the very
    end. What gives it away is not the rhyme but the takhallus: a short
    trailing group carrying the maqtaa, after a group carrying none, is that
    group's ending.

    Kept as a pass over the finished groups rather than a guard inside the
    loop, because the loop cannot see how long the tail will turn out to be:
    at the break, what remains is the rest of the whole verse run, which
    holds every later ghazal of the section too.
    """
    if not groups:
        return groups
    merged = [groups[0]]
    for group in groups[1:]:
        if (
            len(group) <= MAQTA_TAIL
            and any(_is_maqta(sher) for sher in group)
            and not any(_is_maqta(sher) for sher in merged[-1])
        ):
            merged[-1] = merged[-1] + group
        else:
            merged.append(group)
    return merged


def split_ghazals(
    shers: list[tuple[str, str]],
) -> list[list[tuple[str, str]]]:
    """Group shers into ghazals, starting a new one at each matlaa.

    A matlaa alone is not enough to break the run. Two further readings of
    the same evidence decide whether the break is real:

    * A sher that opens on the rhyme the current ghazal is already in is its
      husn-e-matlaa — a second opening sher, which belongs to the same
      ghazal — not the start of a new one. تجاوز has one
      (وحشت ہے / محبّت ہے inside the قیامت ہے ghazal).
    * Unless the sher before it is the maqtaa, in which case the previous
      ghazal has closed and a like-rhymed opening really is a new poem.

    A length outlier is NOT evidence of fusion here, and the one place it
    looks most like it is the place it is least true. کلیات جلد ۱ carries a
    whole collection — معاملہ, named on the volume's title page and on its
    own; ہمارے بیچ is its radif, not its title — written in a single radif:
    fifteen ghazals
    of 15 to 71 shers, against a book-wide norm of 5 to 15. The obvious
    reading — that a shared radif defeated the rhyme test and welded them —
    is wrong twice over. The fifteen ghazals carry fifteen DIFFERENT qafia
    (ا, ی, یں, ر, اں, ب, ت, ن, ل, ار, و, ن, ان, م), so `run_rhyme` separates
    them cleanly, and the collection's own فہرست lists exactly fifteen
    entries which the fifteen pieces open on in order. Inside them there is
    no further boundary to find: across all 142 lines of the longest, not one
    first misra ends on ہمارے بیچ, and no separator falls between them. They
    are simply long. See TestHumareBeechCollection, which locks this.

    The correction that suggests itself — require a matlaa's own two misras
    to share more than the run's radif, deriving the radif from the following
    shers — was measured and is far worse. At a genuine matlaa the pair's
    shared suffix IS the following shers' shared suffix, so "strictly longer"
    is never satisfied: تجاوز collapsed from 100 pieces to 29, باغِ نشاط from
    86 to 23, and 8 of the 11 known ghazals broke.
    """
    groups: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    matla_before = False
    for index, (first, second) in enumerate(shers):
        rhyme = run_rhyme(shers, index)
        opens = is_matla(first, second, rhyme)
        exhausted = _rhyme_exhausted(current, second)
        if (opens or exhausted) and current:
            established = _shared_rhyme(
                [_rhyme_key(s) for _, s in current if s]
            )
            husn = (
                opens
                and not exhausted
                and (
                    _carries(current, rhyme)
                    or not _rhyme_is_forward(shers, index)
                )
                and _same_zameen(established, rhyme)
                and (len(current) > 1 or matla_before)
                and not _is_maqta(current[-1])
            )
            if not husn:
                groups.append(current)
                current = []
        current.append((first, second))
        matla_before = opens
    if current:
        groups.append(current)
    return _rejoin_maqta_tails(groups)
