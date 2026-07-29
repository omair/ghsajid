import collections
import re
from dataclasses import replace
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.inpage import __main__ as cli
from tools.inpage.checks import (
    COLLECTION_INDEX_BASELINE, DECLARED_COLLECTION_COUNTS, GARBAGE_FLAG,
    KULLIYAT_VOLUMES,
    TOC_FIRST_LINE_BASELINE, collection_index_errors, completeness_errors,
    UNPUBLISHABLE, conservation_errors, declared_collection_count_errors,
    flag_decode_garbage, flag_first_line_index, flag_single_line_pieces,
    roundtrip_errors,
    segmentation_groundtruth_errors, toc_count_errors,
    toc_first_line_baseline_errors,
)
from tools.inpage.classify import running_headers, toc_count
from tools.inpage.decode import decode
from tools.inpage.emit import resolve_book_records
from tools.inpage.groundtruth import corpus_lexicon, skeleton
from tools.inpage.ole import read_text_stream
from tools.inpage.printed_index import (
    SECTION_NAMES_BY_BOOK,
    VOLUME_1 as PRINTED_VOLUME_1,
)
from tools.inpage.segment import (
    GATHERED_COLLECTIONS, KULLIYAT_JILD_1_COLLECTIONS,
    attribute_gathered_collections, collection_boundary_dedication, segment,
    segment_book,
)

TAJAWUZ = Path("inp/TAJAWUZ.INP")
BAGH = Path("inp/BAGH E NISHAT KI TARAF.INP")
KULLIYAT = {
    "kulliyat-jild-1": Path("inp/MAZAMEER (1).INP"),
    "kulliyat-jild-2": Path("inp/MAZAMEER (2).INP"),
}


@unittest.skipUnless(TAJAWUZ.exists(), "inp/ sources not present")
class TestPilot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = read_text_stream(TAJAWUZ)
        cls.paragraphs = decode(cls.data)

    def test_every_code_is_mapped(self):
        self.assertEqual(completeness_errors(self.data), [])

    def test_every_paragraph_round_trips(self):
        self.assertEqual(roundtrip_errors(self.paragraphs), [])

    def test_segmentation_finds_pieces(self):
        segments = segment(self.paragraphs)
        self.assertGreater(len(segments), 20)

    def test_no_segment_is_empty(self):
        for s in segment(self.paragraphs):
            self.assertTrue(s.body.strip(), f"piece {s.order} has no body")


class PilotSegmentation:
    """The two gates a book must clear before a human is asked to review it.

    Subclassed once per pilot book: both books declare their own piece count
    in their own فہرست, so neither number is a judgement call and neither is
    written into the segmenter.
    """

    source: Path
    declared: int

    @classmethod
    def setUpClass(cls):
        cls.paragraphs = decode(read_text_stream(cls.source))
        cls.segments = segment(cls.paragraphs)

    def test_the_fihrist_declares_the_piece_count(self):
        self.assertEqual(toc_count(self.paragraphs), self.declared)

    def test_piece_count_matches_the_fihrist(self):
        self.assertEqual(toc_count_errors(self.paragraphs, self.segments), [])

    def test_no_verse_line_is_lost(self):
        self.assertEqual(conservation_errors(self.paragraphs, self.segments), [])

    def test_the_collection_index_floor_does_not_run(self):
        # تجاوز and باغِ نشاط are single published books, not gatherings, so
        # neither slug is keyed into COLLECTION_INDEX_BASELINE at all — the
        # same `.get(book_slug, {})` cmd_segment uses for every other
        # کلیات-only gate.
        book_slug = "tajawuz" if self.source == TAJAWUZ else "bagh-e-nishat-ki-taraf"
        self.assertNotIn(book_slug, COLLECTION_INDEX_BASELINE)
        self.assertEqual(
            collection_index_errors(
                self.paragraphs, self.segments,
                COLLECTION_INDEX_BASELINE.get(book_slug, {}),
            ),
            [],
        )


@unittest.skipUnless(TAJAWUZ.exists(), "inp/ sources not present")
class TestPilotSegmentationTajawuz(PilotSegmentation, unittest.TestCase):
    source = TAJAWUZ
    declared = 100


@unittest.skipUnless(BAGH.exists(), "inp/ sources not present")
class TestPilotSegmentationBaghENishat(PilotSegmentation, unittest.TestCase):
    source = BAGH
    declared = 85


@unittest.skipUnless(
    all(path.exists() for path in KULLIYAT.values()), "inp/ sources not present"
)
class TestKulliyatGroundTruth(unittest.TestCase):
    """The 11 independently-sourced ghazals, against the real volumes.

    Checked across BOTH volumes at once, which is the only honest framing:
    the ghazals are spread over the two books, and neither volume alone
    contains all 11.
    """

    @classmethod
    def setUpClass(cls):
        cls.per_book = {}
        cls.segments = []
        for slug, path in KULLIYAT.items():
            paragraphs = decode(read_text_stream(path))
            segments = segment_book(slug, paragraphs)
            cls.per_book[slug] = (paragraphs, segments)
            cls.segments.extend(segments)

    def test_every_known_ghazal_is_exactly_one_piece(self):
        self.assertEqual(segmentation_groundtruth_errors(self.segments), [])

    def test_each_volume_gates_its_own_share(self):
        # The per-book wiring cmd_segment uses. A volume asked for the whole
        # 11 would report the other volume's ghazals as lost.
        for slug, (_, segments) in self.per_book.items():
            with self.subTest(slug=slug):
                self.assertEqual(
                    segmentation_groundtruth_errors(
                        segments, KULLIYAT_VOLUMES[slug]
                    ),
                    [],
                )

    def test_the_partial_index_still_meets_its_floor(self):
        # Only iterates the slugs actually keyed into TOC_FIRST_LINE_BASELINE
        # (جلد ۲ alone — see that dict's own comment): جلد ۱'s whole-volume
        # entry was retired in favour of the per-collection floor below, so
        # asserting it here too would be the overlapping gate the brief warns
        # against, checking the same regression two different ways.
        for slug in TOC_FIRST_LINE_BASELINE:
            paragraphs, segments = self.per_book[slug]
            with self.subTest(slug=slug):
                self.assertEqual(
                    toc_first_line_baseline_errors(
                        paragraphs, segments, TOC_FIRST_LINE_BASELINE[slug]
                    ),
                    [],
                )

    def test_the_collection_index_floors_hold_on_jild_1(self):
        # جلد ۱'s four uncounted collections (کتابِ صبح، روداد، معاملہ،
        # آیندہ) each floored against the volume's own front matter +
        # reviews — the per-collection gate that superseded the old
        # whole-volume TOC_FIRST_LINE_BASELINE entry for this book.
        paragraphs, segments = self.per_book["kulliyat-jild-1"]
        self.assertEqual(
            collection_index_errors(
                paragraphs, segments,
                COLLECTION_INDEX_BASELINE["kulliyat-jild-1"],
            ),
            [],
        )

    def test_the_collection_index_floor_does_not_run_on_jild_2(self):
        # measured 3-22% per collection — too low to floor, hence no entry.
        self.assertNotIn("kulliyat-jild-2", COLLECTION_INDEX_BASELINE)

    def test_no_verse_line_is_lost(self):
        for slug, (paragraphs, segments) in self.per_book.items():
            with self.subTest(slug=slug):
                self.assertEqual(
                    conservation_errors(
                        paragraphs, segments,
                        SECTION_NAMES_BY_BOOK.get(slug, ()),
                    ),
                    [],
                )

    def test_no_review_swallows_a_collection(self):
        # کلیات جلد ۲ ¶1272 is a 356-character parenthetical aside inside a
        # نظم, with verse either side of it. PROSE_MIN called it prose, PROSE
        # is what opens a critic's essay region, and the region ran to the
        # next running header — 1,749 verse paragraphs, 42 colophons and 30
        # unknowns swallowed into ONE 3,617-line `reviews` piece at order 34,
        # holding poetry from several collections. ¶1855 did the same for a
        # further 1,269 paragraphs.
        #
        # The ceiling is measured, not chosen for comfort: the longest piece
        # that is genuinely a critic's essay is جلد ۲'s ڈاکٹر مسعود اقبال
        # (653 lines, dedication and all), and جلد ۱'s longest is 191. 800
        # sits clear of the real maximum and far under any swallow — the two
        # that were there were 3,617 and 2,489.
        for slug, (_, segments) in self.per_book.items():
            for piece in segments:
                if piece.kind != "reviews":
                    continue
                with self.subTest(slug=slug, order=piece.order):
                    self.assertLess(len(piece.body.splitlines()), 800)


# The collection معاملہ, in کلیات جلد ۱ — ہمارے بیچ is its radif, not its
# name; the volume's title page and معاملہ's own title page both name it — is
# written entirely in one radif:
# every one of its ghazals ends every second misra on ہمارے بیچ. Its ghazals
# are also extraordinarily long — 15 to 71 shers, where the poet's norm is
# 5 to 15 — and that combination makes them look exactly like a segmentation
# failure. They are not. The collection's own فہرست, printed at paragraphs
# 175-179 of the volume, lists fifteen entries and no more, and the fifteen
# pieces the segmenter produces open on those fifteen lines in that order.
#
# This is a lock against a plausible-sounding "fix". Reading the length alone
# as fusion, and splitting inside these ghazals on any rhyme heuristic, would
# manufacture boundaries the book does not have and cannot be caught by the
# ground-truth gate, because none of the 11 known ghazals lives here.
HUMARE_BEECH_MATLAAS = (
    "نہیں ہے کوئی اگر سلسلہ ہمارے بیچ",
    "خیالِ وصل نہ آتا کبھی ہمارے بیچ",
    "ظہور کرنے لگی پھر زمیں ہمارے بیچ",
    "اُگی تھی دھوپ کسی موڑ پر ہمارے بیچ",
    "فروغ پانے لگیں تلخیاں ہمارے بیچ",
    "بنے گا کوئی تعلّق نہ جب ہمارے بیچ",
    "ہو گا شگفت جب گلِ حیرت ہمارے بیچ",
    "کچھ روز سے ذرا سی ہے اَن بن ہمارے بیچ",
    # The فہرست misprints this one as کونیل; the body reads کونپل, and the
    # body is the poem. Every other entry matches the matlaa verbatim.
    "پھوٹی ہے کوئی نور کی کونپل ہمارے بیچ",
    "رہتی ہے اب تھوڑی سی تکرار ہمارے بیچ",
    "دیے جلانے لگا ہے لہو ہمارے بیچ",
    "کیسے جگہ بنائے وہ دریا ہمارے بیچ",
    "کِھلا گیا ہے کوئی گل بدن ہمارے بیچ",
    "ختم ہوا پھر ملنے کا امکان ہمارے بیچ",
    "وہی زمیں، وہی باغِ ارم ہمارے بیچ",
)

# The longest piece in کلیات جلد ۱ — the first ہمارے بیچ ghazal. Held as an
# exact ceiling rather than a round number so that a change producing a
# LONGER piece, which would be real fusion, fails here.
LONGEST_PIECE_SHERS = 71


def _sher_count(piece) -> int:
    return len([b for b in piece.body.split("\n\n") if b.strip()])


@unittest.skipUnless(
    KULLIYAT["kulliyat-jild-1"].exists(), "inp/ sources not present"
)
class TestHumareBeechCollection(unittest.TestCase):
    """The long-ghazal collection that must NOT be split further."""

    @classmethod
    def setUpClass(cls):
        paragraphs = decode(read_text_stream(KULLIYAT["kulliyat-jild-1"]))
        cls.segments = segment_book("kulliyat-jild-1", paragraphs)
        cls.poems = [s for s in cls.segments if s.kind in ("ghazals", "nazms")]

    def test_the_collection_is_exactly_its_fihrist(self):
        opened = [
            s.body.split("\n")[0] for s in self.poems
            if s.body.split("\n")[0].rstrip().endswith("ہمارے بیچ")
        ]
        self.assertEqual(tuple(opened), HUMARE_BEECH_MATLAAS)

    def test_the_collection_is_contiguous(self):
        orders = [
            s.order for s in self.poems
            if s.body.split("\n")[0].rstrip().endswith("ہمارے بیچ")
        ]
        self.assertEqual(orders, list(range(orders[0], orders[0] + 15)))

    def test_no_piece_is_longer_than_the_longest_real_ghazal(self):
        longest = max(self.poems, key=_sher_count)
        self.assertEqual(_sher_count(longest), LONGEST_PIECE_SHERS)
        self.assertEqual(longest.body.split("\n")[0], HUMARE_BEECH_MATLAAS[0])

    def test_every_long_piece_is_an_accounted_for_ghazal(self):
        # Fifteen pieces run past 20 shers. Fourteen are ہمارے بیچ ghazals
        # the فہرست names; the fifteenth is a 23-sher ghazal that closes on
        # the takhallus, which is the book itself saying the ghazal ended
        # there. Nothing else in the volume is long.
        long = [s for s in self.poems if _sher_count(s) > 20]
        self.assertEqual(len(long), 15)
        radif = [
            s for s in long
            if s.body.split("\n")[0].rstrip().endswith("ہمارے بیچ")
        ]
        self.assertEqual(len(radif), 14)
        (other,) = [s for s in long if s not in radif]
        self.assertEqual(other.body.split("\n")[0], "جب سے اُس شوخ سے ملا ہوں مَیں")
        self.assertIn("ساجد", other.body.split("\n\n")[-1])


# کلیات جلد ۱ gathers six separately-published books, each introduced inside
# the body by its own title page — an imprint and a dedication. Its page
# headers name five of the six, but never موسم, the first (see
# test_the_headers_alone_still_cannot_name_موسم), so the title pages are what
# resolve the volume. The ranges below are the poems BETWEEN them; the
# title page itself is neither book's poem and is left unattributed.
#
# موسم and عناصر are the two the volume's own فہرست counts. عناصر's مٹّی /
# پانی / آگ / ہَوا / خواب at بیس غزلیں each is 100.
#
# موسم is 136, NOT the 130 this table read until the printed فہرست was
# transcribed. بہار / سعیر / برشگال / خزاں / زمہریر at بیس غزلیں each plus
# قدیم at تیس غزلیں is 130 GHAZALS — and each of those six sections also
# opens with a حمد, listed as its own index entry. A declared غزلیں count is
# not a collection's poem total, and reading it as one made a six-poem
# shortfall look like an exact pass. See tools/inpage/printed_index.py.
# Counts are the printed فہرست's, and the pieces are counted the way the site
# publishes them — pieces flagged UNPUBLISHABLE (the volume's own index, an
# orphaned byline, end-of-stream scratch) are staged and reported but are not
# poems, so they are not counted here either.
JILD_1_COLLECTIONS = (
    ("موسم", 4, 136, 6, 141),
    ("عناصر", 142, 100, 147, 246),
    ("کتابِ صبح", 247, 97, 249, 345),
    ("آیندہ", 346, 104, 348, 451),
    ("معاملہ", 452, 15, 454, 468),
    ("روداد", 469, 124, 471, 594),
)
# روداد reads 123, not the 124 it read while a short line enclosed by two
# verse lines still classified UNKNOWN and broke the run (see
# classify._bridge_lines_enclosed_by_verse). The one piece the change removes from
# this volume is the last: order 581, whose entire body was
# ‘‘ب گینیگایںقرا ۔ ا  کج’’ — the scratch material at the end of the stream,
# flagged both likely-decode-garbage and single-line-piece. It is now a line
# of order 580 rather than a poem of its own. Every other piece in جلد ۱ is
# byte-identical, and موسم's 130 and عناصر's 100 — the two counts the
# volume's own فہرست declares — are untouched.

# What کلیات جلد ۲ reads off its running page headers. Held here so a change
# to جلد ۱'s title-page path that leaked into the header path fails loudly.
# Spelled exactly as the source prints them, diacritics and all — InPage puts
# the pesh of ہست و بُود and گُلِ سیمیا before its letter rather than over it,
# and the header text is taken verbatim.
#
# Every count here fell when a short line enclosed by two verse lines stopped
# breaking the verse run (see classify._bridge_lines_enclosed_by_verse). جلد ۲ is
# where the volume's free verse lives — 214 of its 576 pieces were نظمیں —
# and a نظم's lines are much shorter than a ghazal's misra, so 255 of its
# paragraphs were falling out of their own poem's run and being emitted as
# separate pieces. Reassembling them is the whole point of that change:
#
#     collection            was    now      نظمیں was/now   غزلیں was/now
#     نیند میں چلتے ہوئے     92     21         91 → 20          1 → 1
#     چہار دریا              51     51          1 →  1         50 → 50
#     ہست و  ُبود           100     98         95 → 93          5 → 5
#     اِعادہ                102    101          2 →  1        100 → 100
#     حقیقت                  76     70          9 →  3         67 → 67
#     ُگلِ سیمیا            141    127         16 →  2        125 → 125
#
# The GHAZAL count of every collection is unchanged, to the poem. That is the
# control on the whole change: a ghazal's misras run 28-42 characters and
# never fall under VERSE_MIN, so no ghazal has an enclosed short line to
# bridge, and every piece that moved is free verse — which is exactly the
# defect. چہار دریا, 50 ghazals and one نظم, does not move at all.
#
# The 33 one-line "poems" this volume used to emit are down to 5, and the
# paragraphs reaching no piece at all from 103 to 45. The cost is stated in
# tests.test_inpage_segment.TestSegmentBook.
# test_a_short_line_enclosed_by_verse_joins_the_poem: a نظم's TITLE printed
# with verse on both sides is read as a line too, so consecutive نظمیں can
# now share a piece. Nothing is lost either way — conservation is silent —
# and staged output is reviewed by a human before promotion.
#
# Before that, نیند میں چلتے ہوئے moved 90 → 92 when a page header stopped
# being read straight through a verse run: the header at paragraph 1150 is
# that collection's title page, and reading through it welded the نظم جادو
# onto the collection's own title poem (‘‘مجھے مدّت سے گہری نیند میں چلنے کی
# عادت ہے’’) as one piece belonging to no collection.
#
# نیند میں چلتے ہوئے then moved 21 → 31 when a colophon stopped being missed
# because InPage had stripped its digits (see classify._is_colophon). A
# colophon CLOSES the poem it follows, so 52 unrecognised ones in this volume
# were welding consecutive نظمیں into single pieces: the largest نظم piece was
# 365 lines and is now 234, and the ten pieces this collection gains are whole
# poems with their own titles and their own dates — جنگ کے دِنوںمیں,
# اُنچاس برس کے بعد, کچھ لفظ تھے, سمندر پی لِیا اُس نے, ابھی صبح ہو گی,
# ٹی وی پر, افسانۂ شہر, ڈیزی کَٹر, گُلزار سے, جادو.
#
# The other five collections do not move by a single poem, and neither does
# any collection's ghazal count (348 across the volume, before and after).
# That is the control again: a colophon ends a نظم, and only a نظم — so a
# change that moved a ghazal count would be a change doing something else.
#
# نیند میں چلتے ہوئے then moved 31 → 72 when a prose-LENGTH paragraph enclosed
# by verse stopped opening a critic's essay region (see
# classify._bridge_lines_enclosed_by_verse). This is the same defect as the
# short-line one above, at the other end of the ghazal-calibrated length
# scale: ¶1272 is a 356-character parenthetical aside inside a نظم, PROSE_MIN
# called it prose, and prose is what OPENS an essay region — so that one line
# swallowed 1,749 verse paragraphs, 42 colophons and 30 unknowns into a single
# 3,617-line `reviews` piece at order 34, holding poetry from several
# collections. ¶1855, the aside of the نظم اور یہ دِل, did the same to a
# further 1,269 paragraphs. The volume's `reviews` count falls 14 → 13 (the
# two swallows go, the essay one of them had eaten comes back), its نظمیں rise
# 130 → 171, and the largest `reviews` piece is now 653 lines — the ڈاکٹر
# مسعود اقبال essay, which is genuinely that long.
#
# Only this one collection moves, and again only in نظمیں: its 71 نظمیں were
# 30, and every other collection's نظمیں and غزلیں are unchanged to the poem
# (348 ghazals across the volume, as before). The swallowed span lay inside
# نیند میں چلتے ہوئے, which is where this volume's free verse lives.
# UNVERIFIED, and deliberately labelled so. جلد ۲ declares no count anywhere
# in its source and its printed فہرست has not been transcribed, so unlike
# جلد ۱'s numbers these are a record of what the pipeline currently reads,
# not of what the book contains. اِعادہ +2, حقیقت +3 and گُلِ سیمیا +1
# against the previous reading are `_rhyme_exhausted` finding ghazals that
# ran together across a bare qafia — the same defect it fixes in موسم, where
# the printed فہرست confirms every one of the six. Nothing here confirms
# these six. What IS checked for this volume is the segmentation ground
# truth: its share of the 11 WordPress ghazals must still be one piece each
# (TestKulliyatGroundTruth), and that holds.
JILD_2_COLLECTIONS = {
    "نیند میں چلتے ہوئے": 72,
    "چہار دریا": 51,
    "ہست و  ُبود": 98,
    # 102 against the 100 its own 2017 edition declares — see
    # DECLARED_COLLECTION_COUNTS. Two known causes remain, both recorded in
    # the report: the book's dedication page counts as a poem, and one ghazal
    # on the radif اد is split in two.
    "اِعادہ": 102,
    "حقیقت": 73,
    "ُگلِ سیمیا": 128,
}


def _flag_all(segments):
    """Run the flag checks cmd_segment runs, in its order.

    A test that flags only for garbage measures a different archive from the
    one the pipeline stages — the count gate, the book records and `promote`
    all read every UNPUBLISHABLE flag, not one of them.
    """
    flag_decode_garbage(segments, corpus_lexicon())
    flag_single_line_pieces(segments)
    flag_first_line_index(segments)


def _distribution(segments):
    """Poems per collection, the way the site counts them.

    Pieces flagged UNPUBLISHABLE are staged and named in the report but never
    reach content/, so counting them here would measure something the archive
    does not publish — and did: عناصر's orphaned byline was counted as its
    hundredth poem, which hid a ghazal genuinely missing from ہَوا.
    """
    return collections.Counter(
        s.collection for s in segments
        if s.kind in ("ghazals", "nazms")
        and not (UNPUBLISHABLE & set(s.flags))
    )


@unittest.skipUnless(
    KULLIYAT["kulliyat-jild-1"].exists(), "inp/ sources not present"
)
class TestKulliyatJild1Collections(unittest.TestCase):
    """The six books کلیات جلد ۱ gathers, against the real volume."""

    @classmethod
    def setUpClass(cls):
        paragraphs = decode(read_text_stream(KULLIYAT["kulliyat-jild-1"]))
        cls.segments = segment_book("kulliyat-jild-1", paragraphs)
        _flag_all(cls.segments)
        cls.boundaries, cls.problems = attribute_gathered_collections(
            cls.segments, KULLIYAT_JILD_1_COLLECTIONS
        )

    def test_the_volumes_own_title_page_names_the_same_six_in_order(self):
        # The evidence the whole table rests on: paragraph 4 of the volume,
        # under مزامیر / (کلیاتِ غلام حسین ساجدؔ) / (جلداوّل), lists the six
        # books it gathers. If the source ever stops saying this, the table
        # has lost its warrant and must not be trusted on faith.
        paragraphs = decode(read_text_stream(KULLIYAT["kulliyat-jild-1"]))
        title_page = skeleton(" ".join(p.text for p in paragraphs[:6]))
        listed = [name for name, _, _, _, _ in JILD_1_COLLECTIONS]
        positions = [title_page.find(skeleton(name)) for name in listed]
        for name, at in zip(listed, positions):
            with self.subTest(collection=name):
                self.assertNotEqual(at, -1, f"{name} is not on the title page")
        self.assertEqual(positions, sorted(positions), "and in this order")

    def test_the_volume_does_print_page_headers_after_all(self):
        # This used to assert the opposite. `running_headers` recognised
        # only names on a hardcoded list, and none of جلد ۱'s six are on it,
        # so the volume looked headerless and 941 of its paragraphs fell
        # through to UNKNOWN. Detected by repetition instead, all six come
        # out — which is what makes the title-page path below a supplement
        # rather than the volume's only source of attribution.
        paragraphs = decode(read_text_stream(KULLIYAT["kulliyat-jild-1"]))
        self.assertEqual(
            running_headers(paragraphs),
            {name for name, _, _, _, _ in JILD_1_COLLECTIONS},
        )

    def test_the_headers_alone_still_cannot_name_موسم(self):
        # Why `attribute_gathered_collections` stays. موسم is the volume's
        # FIRST collection and its name is never printed as a paragraph of
        # its own before its poems — the first موسم paragraph in the book is
        # at index 9796, in the back-of-book فہرست, long after موسم's 130
        # ghazals are done. Every other collection's name is printed once,
        # on its title page, where its poems begin. So the header path
        # backfills موسم's poems with the first header it CAN see — عناصر —
        # and reads 231 poems into عناصر unless the title pages correct it.
        paragraphs = decode(read_text_stream(KULLIYAT["kulliyat-jild-1"]))
        header_only = _distribution(segment(paragraphs))
        self.assertEqual(header_only["موسم"], 0)
        self.assertEqual(header_only["عناصر"], 243)

    def test_every_title_page_is_found_and_named(self):
        self.assertEqual(
            self.boundaries,
            [(order, name) for name, order, _, _, _ in JILD_1_COLLECTIONS],
        )
        self.assertEqual(self.problems, [])

    def test_each_collection_holds_its_own_poems(self):
        counts = _distribution(self.segments)
        for name, _, poems, first, last in JILD_1_COLLECTIONS:
            with self.subTest(collection=name):
                orders = [
                    s.order for s in self.segments
                    if s.collection == name
                    and s.kind in ("ghazals", "nazms")
                    and not (UNPUBLISHABLE & set(s.flags))
                ]
                self.assertEqual(counts[name], poems)
                self.assertEqual((orders[0], orders[-1]), (first, last))

    def test_mausam_yields_the_136_the_fihrist_declares(self):
        # 130 غزلیں plus the حمد each of its six sections opens with.
        self.assertEqual(_distribution(self.segments)["موسم"], 136)

    def test_anasir_yields_the_100_the_fihrist_declares(self):
        self.assertEqual(_distribution(self.segments)["عناصر"], 100)

    def test_every_collection_matches_the_printed_fihrist_exactly(self):
        # All six, poem for poem, against the printed فہرست.
        #
        # `flag_decode_garbage` runs first because the count gate reads its
        # flags — the same order cmd_segment uses. جلد ۱'s stream ends in
        # nine lines of scratch that segment as a `nazm` inside روداد, and
        # counting it made روداد read 125 against a declared 124.
        _flag_all(self.segments)
        self.assertEqual(
            declared_collection_count_errors(
                self.segments, DECLARED_COLLECTION_COUNTS["kulliyat-jild-1"]
            ),
            [],
        )

    def test_the_count_gate_depends_on_the_garbage_flag_running_first(self):
        # The ordering above is load-bearing, so it is asserted rather than
        # left as a comment: unflagged, the scratch piece counts as one of
        # روداد's poems and the gate reports a book that is in fact complete.
        unflagged = [
            replace(piece, flags=[]) for piece in self.segments
        ]
        errors = declared_collection_count_errors(
            unflagged, DECLARED_COLLECTION_COUNTS["kulliyat-jild-1"]
        )
        self.assertEqual(len(errors), 2, errors)
        joined = " ".join(errors)
        # روداد gains the scratch nazm, عناصر the orphaned byline — and the
        # byline is the one that mattered, because counting it made عناصر
        # read a complete 100 while ہَوا was a ghazal short.
        self.assertIn("روداد", joined)
        self.assertIn("عناصر", joined)

    def test_every_section_of_موسم_and_عناصر_matches_the_printed_fihrist(self):
        # The finer gate the printed index made possible. A total can pass
        # while a poem is missing from one section and duplicated in another —
        # these eleven cannot.
        #
        # All eleven, with no exemption. ہَوا held 19 until the rhyme
        # comparison learned that ق and ک rhyme in Urdu — its twentieth ghazal
        # opens حق ہَوا نے against a دستک/ٹھنڈک/کالک run, and was read as a
        # continuation of the poem above it.
        counts = collections.Counter(
            (s.collection, s.section) for s in self.segments
            if s.kind in ("ghazals", "nazms")
        )
        for collection in PRINTED_VOLUME_1:
            for section in collection.sections:
                with self.subTest(section=section.name):
                    self.assertEqual(
                        counts[(collection.name, section.name)], section.poems
                    )

    def test_only_the_title_pages_are_left_unattributed(self):
        unattributed = [
            s for s in self.segments
            if not s.collection and s.kind in ("ghazals", "nazms")
        ]
        self.assertEqual(
            [s.order for s in unattributed], [4, 142, 247, 346, 452, 469]
        )

    def test_six_book_records_are_written_under_this_volume(self):
        records, problems = resolve_book_records(
            self.segments, "kulliyat-jild-1"
        )
        self.assertEqual(problems, [])
        self.assertEqual(
            [name for name, _ in records],
            [name for name, _, _, _, _ in JILD_1_COLLECTIONS],
        )

    def test_the_known_ghazals_are_untouched_by_attribution(self):
        self.assertEqual(
            segmentation_groundtruth_errors(
                self.segments, KULLIYAT_VOLUMES["kulliyat-jild-1"]
            ),
            [],
        )


@unittest.skipUnless(
    KULLIYAT["kulliyat-jild-2"].exists(), "inp/ sources not present"
)
class TestKulliyatJild2IsUnaffected(unittest.TestCase):
    """جلد ۲ reads its collections off running headers, and must keep doing so."""

    @classmethod
    def setUpClass(cls):
        paragraphs = decode(read_text_stream(KULLIYAT["kulliyat-jild-2"]))
        cls.segments = segment_book("kulliyat-jild-2", paragraphs)

    def test_the_header_distribution_is_unchanged(self):
        counts = _distribution(self.segments)
        self.assertEqual(
            {name: counts[name] for name in JILD_2_COLLECTIONS},
            JILD_2_COLLECTIONS,
        )

    def test_the_volume_is_not_keyed_into_the_title_page_table(self):
        self.assertNotIn("kulliyat-jild-2", GATHERED_COLLECTIONS)

    def test_no_title_page_block_is_found_in_it(self):
        self.assertEqual(
            [s.order for s in self.segments
             if collection_boundary_dedication(s)],
            [],
        )


@unittest.skipUnless(TAJAWUZ.exists(), "inp/ sources not present")
class TestSingleBooksAttributeNothing(unittest.TestCase):
    """تجاوز and باغِ نشاط are single published books, not gatherings."""

    def test_no_collection_is_attributed(self):
        for path in (TAJAWUZ, BAGH):
            with self.subTest(source=path.name):
                segments = segment(decode(read_text_stream(path)))
                self.assertEqual(
                    set(s.collection for s in segments), {""}
                )
                self.assertEqual(
                    [s.order for s in segments
                     if collection_boundary_dedication(s)],
                    [],
                )


# One نظم of کلیات جلد ۲, paragraphs 865-884, in source order. Half of these
# lines are shorter than a ghazal's misra — سُکڑ کر is 7 characters against a
# measured VERSE_MIN of 15 — so every one of them used to classify UNKNOWN,
# break the verse run, and cut the poem into fragments that segment() emitted
# as separate pieces. They are printed here verbatim so the test asserts the
# poem, not a count.
SHATTERED_NAZM = [
    "سو اُس لمحے",
    "مرا دِل ڈوبتا تھا",
    "زمیں میرے برابر سے، مِری قامت سے اُٹھ کر",
    "چھتوں کو اور محرابوں کو چُھو کر",
    "فناہے، سب فنا ہے",
    "اوّل و آخر فنا ہے، کا ترانہ گا رہی تھی",
    "مری ظلمت سے میری روشنی",
    "گہنا رہی تھی",
    "مِرا دِل ڈوبتا تھا",
    "مِرا دِل ڈوبتا تھا اور یاد آنے لگے تھے تُم",
    "کہیں کچھ تھا",
    "جو شاید مشترک تھا",
    "اِس کہانی میں",
    "کشف کی رات",
    "بہت دن بعد",
    "جب مجھ میں کھڑے ہونے کی طاقت بھی نہیں تھی",
    "مِرے کاندھے",
    "اُداسی، رنجِ محرومی کی تہ در تہ دبازت سے",
    "سُکڑ کر",
    "کہیں اندر ہی اندر جُھک رہے تھے",
]


@unittest.skipUnless(
    KULLIYAT["kulliyat-jild-2"].exists(), "inp/ sources not present"
)
class TestFreeVerseReassembles(unittest.TestCase):
    """The نظم above must be ONE piece, with its short lines in place."""

    @classmethod
    def setUpClass(cls):
        paragraphs = decode(read_text_stream(KULLIYAT["kulliyat-jild-2"]))
        cls.segments = segment_book("kulliyat-jild-2", paragraphs)

    def _holders(self):
        """Pieces holding the whole poem.

        `all`, not `any`: three of these lines are short enough to recur
        verbatim elsewhere in the volume (بہت دن بعد is a hemistich of a
        ghazal 61 pieces later), so a per-line holder count reports splits
        that are really coincidences of the language. A shattered poem holds
        no piece here at all, which is the failure this asserts against.
        """
        return [
            piece for piece in self.segments
            if all(line in piece.body for line in SHATTERED_NAZM)
        ]

    def test_the_whole_nazm_is_one_piece(self):
        self.assertEqual(len(self._holders()), 1)

    def test_every_line_survives_in_source_order(self):
        body = [
            line.strip() for line in self._holders()[0].body.split("\n")
            if line.strip()
        ]
        positions = [body.index(line) for line in SHATTERED_NAZM]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(
            [body[i] for i in range(positions[0], positions[-1] + 1)],
            SHATTERED_NAZM,
        )


class TestSegmentDirectCallMatchesThePipeline(unittest.TestCase):
    """The split-brain regression test.

    `segment()` used to set collections two different ways depending on the
    caller: `cmd_segment` ran `attribute_gathered_collections` as a SECOND
    pass over its own result, while a direct `segment()` call — a test, a
    gate, a diagnostic — saw only the running-header reading. For کلیات جلد
    ۱ those disagreed outright: a direct call reported عناصر with 231 poems,
    backfilled from موسم's missing header, where the pipeline actually
    stages 100, the count its own فہرست declares. Now that
    `attribute_gathered_collections` runs INSIDE `segment()` (keyed by the
    `gathered_collections` table `cmd_segment` also uses), the two paths
    must produce identical book records for both volumes — this locks it so
    a future change to one path without the other fails here first, not in
    a report a reviewer has to notice by hand.
    """

    def _pipeline_book_record_counts(self, book_slug: str) -> dict[str, int]:
        """Poems per book record, read back from what `cmd_segment` staged."""
        staging_root = Path(tempfile.mkdtemp())
        try:
            with mock.patch.object(cli, "STAGING", staging_root):
                cli.cmd_segment(book_slug)
            books_dir = staging_root / book_slug / "books"
            return {
                yaml_path.stem: len(
                    re.findall(
                        r"^\s*-\s*\{", yaml_path.read_text(encoding="utf-8"),
                        re.MULTILINE,
                    )
                )
                for yaml_path in books_dir.iterdir()
            }
        finally:
            shutil.rmtree(staging_root)

    def _direct_book_record_counts(self, book_slug: str) -> dict[str, int]:
        """Poems per book record, from calling `segment()` directly."""
        paragraphs = decode(read_text_stream(KULLIYAT[book_slug]))
        segments = segment_book(book_slug, paragraphs)
        # The pipeline runs every flag check before it builds book contents,
        # and `book_contents_and_slugs` leaves an UNPUBLISHABLE piece out — so
        # a direct call that skips the flagging really does describe a
        # different book. Exactly the divergence this class exists to catch,
        # in its newest form.
        _flag_all(segments)
        records, problems = resolve_book_records(segments, book_slug)
        self.assertEqual(problems, [])
        return {
            slug: sum(
                1 for s in segments
                if s.kind in ("ghazals", "nazms")
                and s.collection == collection
                and not (UNPUBLISHABLE & set(s.flags))
            )
            for collection, slug in records
        }

    def test_kulliyat_jild_1(self):
        if not KULLIYAT["kulliyat-jild-1"].exists():
            self.skipTest("inp/ sources not present")
        self.assertEqual(
            self._direct_book_record_counts("kulliyat-jild-1"),
            self._pipeline_book_record_counts("kulliyat-jild-1"),
        )

    def test_kulliyat_jild_2(self):
        if not KULLIYAT["kulliyat-jild-2"].exists():
            self.skipTest("inp/ sources not present")
        self.assertEqual(
            self._direct_book_record_counts("kulliyat-jild-2"),
            self._pipeline_book_record_counts("kulliyat-jild-2"),
        )


if __name__ == "__main__":
    unittest.main()
