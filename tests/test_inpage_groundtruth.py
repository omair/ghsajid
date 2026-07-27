import unittest
from pathlib import Path

from tools.inpage.groundtruth import KNOWN_GHAZALS, find_in, site_text, skeleton
from tools.inpage.decode import decode
from tools.inpage.ole import read_text_stream

KULLIYAT = [Path("inp/MAZAMEER (1).INP"), Path("inp/MAZAMEER (2).INP")]


class TestSkeleton(unittest.TestCase):
    def test_strips_diacritics_and_punctuation(self):
        self.assertEqual(skeleton("ماورائے سراغ ہوں مَیں بھی۔"), skeleton("ماورائے سراغ ہوں میں بھی"))

    def test_keeps_letters_and_word_boundaries(self):
        self.assertEqual(skeleton("دل ، جاں"), "دل جاں")


@unittest.skipUnless(all(p.exists() for p in KULLIYAT), "inp/ sources not present")
class TestGroundTruth(unittest.TestCase):
    """The regression guard on the codepage.

    The 11 slugs are named explicitly rather than discovered at runtime, so
    deleting or renaming one is a visible failure instead of a silently
    smaller check.
    """

    @classmethod
    def setUpClass(cls):
        cls.paragraphs = []
        for path in KULLIYAT:
            cls.paragraphs.extend(decode(read_text_stream(path)))

    def test_all_eleven_known_ghazals_are_named(self):
        self.assertEqual(len(KNOWN_GHAZALS), 11)

    def test_every_known_ghazal_decodes_to_its_committed_skeleton(self):
        missing = []
        for slug in KNOWN_GHAZALS:
            want = skeleton(site_text(slug))
            if find_in(self.paragraphs, want) is None:
                missing.append(slug)
        self.assertEqual(missing, [], f"codepage does not reproduce: {missing}")


if __name__ == "__main__":
    unittest.main()
