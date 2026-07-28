import unittest
from pathlib import Path

from tools.inpage.checks import (
    KULLIYAT_VOLUMES, TOC_FIRST_LINE_BASELINE,
    completeness_errors, conservation_errors,
    roundtrip_errors, segmentation_groundtruth_errors, toc_count_errors,
    toc_first_line_baseline_errors,
)
from tools.inpage.classify import toc_count
from tools.inpage.decode import decode
from tools.inpage.ole import read_text_stream
from tools.inpage.segment import segment

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
        for slug, (paragraphs, segments) in self.per_book.items():
            with self.subTest(slug=slug):
                self.assertEqual(
                    toc_first_line_baseline_errors(
                        paragraphs, segments, TOC_FIRST_LINE_BASELINE[slug]
                    ),
                    [],
                )

    def test_no_verse_line_is_lost(self):
        for slug, (paragraphs, segments) in self.per_book.items():
            with self.subTest(slug=slug):
                self.assertEqual(conservation_errors(paragraphs, segments), [])


# The collection ہمارے بیچ, in کلیات جلد ۱, is written entirely in one radif:
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


if __name__ == "__main__":
    unittest.main()
