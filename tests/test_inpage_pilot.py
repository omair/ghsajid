import unittest
from pathlib import Path

from tools.inpage.checks import (
    completeness_errors, conservation_errors, roundtrip_errors,
    toc_count_errors,
)
from tools.inpage.classify import toc_count
from tools.inpage.decode import decode
from tools.inpage.ole import read_text_stream
from tools.inpage.segment import segment

TAJAWUZ = Path("inp/TAJAWUZ.INP")
BAGH = Path("inp/BAGH E NISHAT KI TARAF.INP")


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


if __name__ == "__main__":
    unittest.main()
