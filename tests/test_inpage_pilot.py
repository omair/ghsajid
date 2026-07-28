import collections
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.inpage import __main__ as cli
from tools.inpage.checks import (
    COLLECTION_INDEX_BASELINE, DECLARED_COLLECTION_COUNTS, KULLIYAT_VOLUMES,
    TOC_FIRST_LINE_BASELINE, collection_index_errors, completeness_errors,
    conservation_errors, declared_collection_count_errors, roundtrip_errors,
    segmentation_groundtruth_errors, toc_count_errors,
    toc_first_line_baseline_errors,
)
from tools.inpage.classify import running_headers, toc_count
from tools.inpage.decode import decode
from tools.inpage.emit import resolve_book_records
from tools.inpage.groundtruth import skeleton
from tools.inpage.ole import read_text_stream
from tools.inpage.segment import (
    GATHERED_COLLECTIONS, KULLIYAT_JILD_1_COLLECTIONS,
    attribute_gathered_collections, collection_boundary_dedication, segment,
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
            segments = segment(paragraphs)
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
                self.assertEqual(conservation_errors(paragraphs, segments), [])


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
        cls.segments = segment(paragraphs)
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
# موسم and عناصر are the two the volume's own فہرست counts: بہار / سعیر /
# برشگال / خزاں / زمہریر at بیس غزلیں each plus قدیم at تیس غزلیں is 130, and
# مٹّی / پانی / آگ / ہَوا / خواب at بیس غزلیں each is 100. Two independent
# structures — the title pages and the declared counts — agree to the poem.
JILD_1_COLLECTIONS = (
    ("موسم", 4, 130, 5, 134),
    ("عناصر", 135, 100, 137, 237),
    ("کتابِ صبح", 238, 92, 240, 331),
    ("آیندہ", 332, 104, 334, 437),
    ("معاملہ", 438, 15, 440, 454),
    ("روداد", 455, 124, 457, 581),
)

# What کلیات جلد ۲ reads off its running page headers. Held here so a change
# to جلد ۱'s title-page path that leaked into the header path fails loudly.
# Spelled exactly as the source prints them, diacritics and all — InPage puts
# the pesh of ہست و بُود and گُلِ سیمیا before its letter rather than over it,
# and the header text is taken verbatim.
#
# نیند میں چلتے ہوئے reads 92, not the 90 it read while a page header was
# read straight through a verse run: the header at paragraph 1150 is that
# collection's title page, and reading through it welded the نظم جادو onto
# the collection's own title poem (‘‘مجھے مدّت سے گہری نیند میں چلنے کی عادت
# ہے’’) as one piece belonging to no collection. Ending the run at the header
# separates them and gives each its name. This is the only piece in the
# volume the change moves.
JILD_2_COLLECTIONS = {
    "نیند میں چلتے ہوئے": 92,
    "چہار دریا": 51,
    "ہست و  ُبود": 100,
    "اِعادہ": 102,
    "حقیقت": 76,
    "ُگلِ سیمیا": 141,
}


def _distribution(segments):
    return collections.Counter(
        s.collection for s in segments if s.kind in ("ghazals", "nazms")
    )


@unittest.skipUnless(
    KULLIYAT["kulliyat-jild-1"].exists(), "inp/ sources not present"
)
class TestKulliyatJild1Collections(unittest.TestCase):
    """The six books کلیات جلد ۱ gathers, against the real volume."""

    @classmethod
    def setUpClass(cls):
        paragraphs = decode(read_text_stream(KULLIYAT["kulliyat-jild-1"]))
        cls.segments = segment(paragraphs)
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
        self.assertEqual(header_only["عناصر"], 231)

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
                    if s.collection == name and s.kind in ("ghazals", "nazms")
                ]
                self.assertEqual(counts[name], poems)
                self.assertEqual((orders[0], orders[-1]), (first, last))

    def test_mausam_yields_the_130_the_fihrist_declares(self):
        self.assertEqual(_distribution(self.segments)["موسم"], 130)

    def test_anasir_yields_the_100_the_fihrist_declares(self):
        self.assertEqual(_distribution(self.segments)["عناصر"], 100)

    def test_the_declared_count_gate_is_silent(self):
        self.assertEqual(
            declared_collection_count_errors(
                self.segments,
                DECLARED_COLLECTION_COUNTS["kulliyat-jild-1"],
            ),
            [],
        )

    def test_only_the_title_pages_are_left_unattributed(self):
        unattributed = [
            s for s in self.segments
            if not s.collection and s.kind in ("ghazals", "nazms")
        ]
        self.assertEqual(
            [s.order for s in unattributed], [135, 238, 332, 438, 455]
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
        cls.segments = segment(paragraphs)

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
        segments = segment(
            paragraphs, gathered_collections=GATHERED_COLLECTIONS.get(book_slug, {}),
        )
        records, problems = resolve_book_records(segments, book_slug)
        self.assertEqual(problems, [])
        return {
            slug: sum(
                1 for s in segments
                if s.kind in ("ghazals", "nazms") and s.collection == collection
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
