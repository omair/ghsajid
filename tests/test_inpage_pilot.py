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


if __name__ == "__main__":
    unittest.main()
