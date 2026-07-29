"""The فہرست of مزامیر جلد اوّل, transcribed from the printed book.

The decoder cannot recover any of this. InPage stores digits outside the
text stream, so every page number, every date and every count in the
printed index is stripped before `decode` ever sees a character — which is
why `Book.year` was empty for all six collections and why ten of the twelve
collections across both volumes had no count to gate against.

Transcribed 2026-07-28 from photographs of the physical copy (front matter
pages 5–22, complete, no gaps). Two kinds of entry appear, and the
difference matters:

  * موسم and عناصر index their *sections*, declaring each section's poem
    count in words — `(بیس غزلیں)`, `(تیس غزلیں)`. Words, not digits, so
    the decoder loses them but a reader cannot misread them.
  * کتابِ صبح, آیندہ, معاملہ and روداد index every poem by its opening
    misra with a page number. That is a census: it says how many poems
    there are AND which ones.

`START_PAGE` and the section ranges are recorded because they are
independently checkable: a collection's running page header appears once
per page, so the number of headers `classify.running_headers` counts must
equal the collection's span. That check already passes to within one page.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .flags import BYLINE_FLAG


@dataclass(frozen=True)
class Section:
    """A named division within a collection, with its declared poem count.

    `hamd` records whether the section opens with a حمد listed as its own
    index entry. In موسم every section does; in عناصر none does. The حمد is
    a separate poem from the section's `ghazals`, not one of them — reading
    it as one is what made موسم's count appear to close exactly when six
    poems were in fact missing.
    """

    name: str
    ghazals: int
    hamd: bool = False
    first_page: int | None = None
    last_page: int | None = None

    @property
    def poems(self) -> int:
        return self.ghazals + (1 if self.hamd else 0)


@dataclass(frozen=True)
class PrintedCollection:
    """One of the six books مزامیر جلد اوّل gathers."""

    name: str
    year: int
    start_page: int
    # Exactly one of these two is populated, per the two index styles above.
    sections: tuple[Section, ...] = ()
    poem_pages: tuple[int, ...] = ()
    # Devotional pieces indexed separately from the غزلیں run, as
    # `(حمد)` / `(نعت)` / `(سلام)` labels in the printed index.
    devotional_pages: tuple[int, ...] = ()
    # Prose the collection carries: forewords, afterwords. Not poems.
    prose: tuple[tuple[str, str, int], ...] = ()
    # Prose entries the index lists as ONE section but which stage as many
    # pieces. روداد's آرا is ten critics' opinions, each signed and dated;
    # the index counts the section, the archive wants the critics. Named here
    # so `apply_printed_titles` does not try to match one printed entry
    # against ten staged pieces and report a disagreement that is not one.
    anthologies: tuple[str, ...] = ()

    @property
    def poems(self) -> int:
        """Verse pieces the printed index declares, devotional included."""
        if self.sections:
            return sum(s.poems for s in self.sections)
        return len(self.poem_pages) + len(self.devotional_pages)


VOLUME_1_TITLE = "مزامیر"
VOLUME_1_SUBTITLE = "کلّیاتِ غلام حسین ساجدؔ (جلد اوّل)"

MAUSAM = PrintedCollection(
    name="موسم",
    year=1985,
    start_page=23,
    prose=(("پیش لفظ", "محمد خالد", 25),),
    sections=(
        Section("بہار", 20, hamd=True, first_page=33, last_page=53),
        Section("سعیر", 20, hamd=True, first_page=55, last_page=77),
        Section("برشگال", 20, hamd=True, first_page=79, last_page=107),
        Section("خزاں", 20, hamd=True, first_page=109, last_page=137),
        Section("زمہریر", 20, hamd=True, first_page=139, last_page=165),
        # The one section that breaks the pattern: تیس, thirty, not twenty.
        Section("قدیم", 30, hamd=True, first_page=167, last_page=203),
    ),
)

ANASIR = PrintedCollection(
    name="عناصر",
    year=1993,
    start_page=205,
    prose=(
        ("اعتذار", "غلام حسین ساجد", 207),
        ("ابتدائیہ", "ڈاکٹر مرزا حامد بیگ", 209),
    ),
    sections=(
        Section("مٹّی", 20, first_page=223, last_page=247),
        Section("پانی", 20, first_page=249, last_page=273),
        Section("آگ", 20, first_page=275, last_page=303),
        Section("ہَوا", 20, first_page=305, last_page=327),
        Section("خواب", 20, first_page=329, last_page=352),
    ),
)

KITAB_E_SUBH = PrintedCollection(
    name="کتابِ صبح",
    year=1998,
    start_page=353,
    prose=(("نقیبِ ساعتِ آیندہ", "سیّد عامر سہیل", 355),),
    poem_pages=(
        371, 372, 373, 374, 375, 376, 377, 378, 380, 381,
        382, 383, 384, 385, 386, 387, 389, 390, 391, 392,
        393, 394, 395, 396, 397, 398, 399, 400, 403, 404,
        405, 408, 410, 411, 412, 413, 415, 417, 419, 423,
        425, 426, 427, 428, 430, 432, 434, 435, 436, 437,
        439, 441, 443, 444, 446, 447, 448, 450, 452, 454,
        456, 458, 459, 461, 462, 464, 465, 466, 467, 468,
        469, 470, 471, 472, 473, 474, 475, 477, 479, 480,
        481, 483, 484, 485, 486, 487, 488, 489, 490, 491,
        492, 493, 494, 496, 497, 498, 499,
    ),
)

AYINDA = PrintedCollection(
    name="آیندہ",
    year=2004,
    start_page=501,
    prose=(("آیندہ… تخلیقی وفور کا ایک کرشمہ", "ریاض احمد", 503),),
    devotional_pages=(513, 514, 515, 516),   # حمد, نعت, نعت, سلام
    poem_pages=(
        519, 520, 521, 522, 524, 525, 526, 527, 528, 529,
        530, 531, 532, 533, 534, 535, 536, 537, 538, 539,
        540, 541, 542, 543, 544, 545, 546, 547, 548, 549,
        550, 551, 552, 553, 554, 555, 556, 557, 559, 560,
        561, 562, 563, 564, 565, 566, 567, 568, 569, 570,
        571, 572, 573, 574, 575, 576, 577, 579, 580, 581,
        582, 584, 586, 588, 590, 591, 592, 593, 595, 596,
        598, 599, 600, 601, 602, 605, 607, 608, 609, 611,
        612, 614, 615, 616, 617, 618, 619, 621, 623, 625,
        626, 628, 630, 632, 634, 636, 637, 638, 640, 642,
    ),
)

MUAMLA = PrintedCollection(
    name="معاملہ",
    year=2006,
    start_page=643,
    prose=(("دیباچہ", "ڈاکٹر نجیب جمال", 645),),
    # Fifteen ghazals, every one on the radif ہمارے بیچ — the whole book is
    # one radif by design. No rhyme-based rule can find the boundaries
    # between them; these page numbers are the only evidence there is.
    poem_pages=(
        655, 666, 671, 675, 679, 683, 686, 695,
        700, 706, 711, 715, 723, 727, 731,
    ),
)

RODAD = PrintedCollection(
    name="روداد",
    year=2010,
    start_page=735,
    prose=(
        ("روداد", "غلام حسین ساجد", 737),
        ("آرا", "", 901),
        ("تعارف", "", 911),
    ),
    anthologies=("آرا",),
    devotional_pages=(739, 740, 741, 742),   # نعت, نعت, نعت, سلام
    poem_pages=(
        745, 746, 747, 748, 749, 750, 751, 752, 753, 754,
        756, 757, 759, 761, 763, 765, 766, 767, 769, 770,
        771, 772, 773, 774, 775, 776, 777, 778, 780, 782,
        784, 785, 786, 788, 789, 791, 792, 793, 794, 796,
        797, 798, 800, 801, 803, 805, 807, 809, 811, 812,
        814, 815, 816, 817, 818, 819, 820, 821, 822, 823,
        825, 826, 827, 828, 830, 831, 832, 833, 834, 835,
        836, 837, 838, 839, 840, 841, 843, 844, 846, 848,
        850, 852, 854, 855, 857, 859, 861, 864, 866, 868,
        869, 870, 872, 873, 874, 876, 877, 878, 879, 880,
        881, 882, 883, 884, 885, 886, 887, 888, 889, 890,
        891, 892, 893, 894, 895, 896, 897, 898, 899, 900,
    ),
)

VOLUME_1: tuple[PrintedCollection, ...] = (
    MAUSAM, ANASIR, KITAB_E_SUBH, AYINDA, MUAMLA, RODAD,
)

# Keyed by the collection name the running page headers carry, which is what
# `Segment.collection` holds — so `checks` can look a collection up by the
# same string the segmenter attributed it with.
BY_NAME: dict[str, PrintedCollection] = {c.name: c for c in VOLUME_1}

YEARS: dict[str, int] = {c.name: c.year for c in VOLUME_1}

def apply_printed_titles(
    segments: list, book_slug: str, unpublishable: frozenset[str]
) -> list[str]:
    """Title each essay from the printed فہرست, and name its author.

    Segmentation cannot title an essay. It has only the block's own lines to
    work from, and those give it the author's name (کتابِ صبح's foreword is
    staged as "سیّد عامر سہیل"), the collection's name (موسم's as "موسم"), or
    a stray fragment of the page before it (عناصر's اعتذار as "(محمدخالد)",
    which is موسم's foreword's byline). The printed index names all eight,
    with their authors, and is the only thing here that actually knows.

    Matched by POSITION within a collection, never by guessing at the text:
    the index lists a collection's prose in the order the book prints it, and
    segmentation emits pieces in that same order. Where the two disagree on
    how many there are, nothing is renamed and the disagreement is reported —
    a wrong byline on a critic's essay is worse than none.

    Pieces flagged unpublishable are skipped: they are not the book's prose.
    """
    if book_slug not in ("kulliyat-jild-1",):
        return []
    problems: list[str] = []
    for collection in VOLUME_1:
        # An anthology's pieces name themselves — the critic signs each one —
        # so they are neither matched nor counted here, and neither is the
        # single index entry that covers them all.
        staged = [
            piece for piece in segments
            if piece.kind == "reviews"
            and piece.collection == collection.name
            and not (unpublishable & set(piece.flags))
            and not piece.reviewed_author
        ]
        expected = [
            entry for entry in collection.prose
            if entry[0] not in collection.anthologies
        ]
        if len(staged) != len(expected):
            problems.append(
                f"{collection.name}: the printed فہرست lists "
                f"{len(expected)} unattributed prose piece(s) "
                f"({', '.join(title for title, _, _ in expected)}) but "
                f"{len(staged)} were staged — left untitled, name them by hand"
            )
            continue
        for piece, (title, author, _) in zip(staged, expected):
            piece.title = title
            piece.reviewed_author = author
            # The byline flag asks a human to confirm an attribution
            # segmentation had to guess at from an honorific. The printed
            # index is better evidence than the guess, so the question is
            # answered and the flag comes down — leaving it up would send a
            # reviewer to check something already settled by the book.
            if BYLINE_FLAG in piece.flags:
                piece.flags.remove(BYLINE_FLAG)
    return problems


# Section names to hand `classify` for a given book slug — see
# `classify.heading_map` for why these are passed per book instead of joining
# the global SECTION_HEADINGS set. A slug that is absent gets `()`, which
# classifies exactly as the pipeline did before this table existed; that is
# what keeps تجاوز and باغِ نشاط byte-identical.
SECTION_NAMES_BY_BOOK: dict[str, tuple[str, ...]] = {
    "kulliyat-jild-1": tuple(s.name for c in VOLUME_1 for s in c.sections),
}

# What each collection's verse count must be. Supersedes the two entries
# `checks.DECLARED_COLLECTION_COUNTS` carried for موسم and عناصر, which
# counted غزلیں only and so read six swallowed حمد as a clean pass.
DECLARED_POEMS: dict[str, int] = {c.name: c.poems for c in VOLUME_1}
