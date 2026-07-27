import unittest
from pathlib import Path

from tools.inpage.checks import completeness_errors, roundtrip_errors
from tools.inpage.decode import decode
from tools.inpage.ole import read_text_stream
from tools.inpage.segment import segment

TAJAWUZ = Path("inp/TAJAWUZ.INP")


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


if __name__ == "__main__":
    unittest.main()
