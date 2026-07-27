import unittest
from pathlib import Path

from tools.inpage.groundtruth import (
    EXPECTED_LINES_TOTAL,
    KNOWN_GHAZALS,
    MIN_LINES_MATCHED,
    MIN_WHOLE_GHAZALS,
    line_match_report,
    skeleton,
)
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

    def test_codepage_meets_the_committed_baseline(self):
        """Gate C: a baseline regression gate, not verbatim reproduction.

        The site text and the printed کلیات are different editions, so exact
        whole-ghazal reproduction is not the bar. Instead this asserts the
        codepage still reproduces at least as many ground-truth lines
        letter-for-letter as it did when the baseline was measured — a wrong
        codepage entry breaks hundreds of lines at once and still fails this,
        while edition variance (already present in the baseline) does not.
        """
        report = line_match_report(self.paragraphs)
        total = sum(len(results) for results in report.values())
        matched = sum(sum(results) for results in report.values())
        whole = sum(1 for results in report.values() if results and all(results))

        unmatched = {
            slug: [i for i, ok in enumerate(results) if not ok]
            for slug, results in report.items()
            if not all(results)
        }

        self.assertEqual(total, EXPECTED_LINES_TOTAL, "ground-truth line count changed unexpectedly")
        self.assertGreaterEqual(
            matched,
            MIN_LINES_MATCHED,
            f"only {matched}/{total} ground-truth lines reproduce (baseline: "
            f"{MIN_LINES_MATCHED}/{EXPECTED_LINES_TOTAL}); unmatched line indices per slug: {unmatched}",
        )
        self.assertGreaterEqual(
            whole,
            MIN_WHOLE_GHAZALS,
            f"only {whole} ghazals reproduce whole (baseline: {MIN_WHOLE_GHAZALS})",
        )


if __name__ == "__main__":
    unittest.main()
