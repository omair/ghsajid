"""Tests for the tools.inpage.__main__ CLI wiring — staging lifecycle."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.inpage import __main__ as cli
from tools.inpage.models import Segment

TAJAWUZ = Path("inp/TAJAWUZ.INP")


class TestBookContentsAndSlugs(unittest.TestCase):
    """Finding 1: a book record must not carry `reviews` rows.

    src/content.config.ts's books schema only allows kind: ghazals | nazms,
    so passing every segment straight through to Book.contents (as
    cmd_segment used to) would write a `reviews` row into e.g.
    باغِ نشاط's books/*.yaml — the first real `promote` would then either
    fail schema validation or trip resolveBook's dead-reference throw, since
    `promote` deliberately skips reviews pieces.
    """

    def test_reviews_are_excluded_and_order_is_preserved(self):
        ghazal_1 = Segment(kind="ghazals", title="a", body="a", order=1)
        review = Segment(kind="reviews", title="r", body="r", order=2)
        nazm = Segment(kind="nazms", title="n", body="n", order=3)
        ghazal_2 = Segment(kind="ghazals", title="b", body="b", order=4)
        segments = [ghazal_1, review, nazm, ghazal_2]
        slugs = ["ghazal-1", "review", "nazm", "ghazal-2"]

        contents, resolved = cli.book_contents_and_slugs(segments, slugs)

        self.assertEqual(contents, [ghazal_1, nazm, ghazal_2])
        self.assertEqual(resolved, ["ghazal-1", "nazm", "ghazal-2"])
        self.assertTrue(all(s.kind != "reviews" for s in contents))


@unittest.skipUnless(TAJAWUZ.exists(), "inp/ sources not present")
class TestCmdSegmentStaging(unittest.TestCase):
    def setUp(self):
        self.staging_root = Path(tempfile.mkdtemp())
        self._patcher = mock.patch.object(cli, "STAGING", self.staging_root)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        shutil.rmtree(self.staging_root)

    def test_rerunning_segment_clears_a_stale_orphan_piece(self):
        cli.cmd_segment("tajawuz")
        book_staging = self.staging_root / "tajawuz"

        # Simulate a leftover piece from a previous run whose title/slug the
        # current segmentation no longer produces.
        orphan = book_staging / "ghazals" / "an-orphan-from-a-previous-run.md"
        orphan.parent.mkdir(parents=True, exist_ok=True)
        orphan.write_text("---\ntitle: \"orphan\"\n---\n\nبچا ہوا\n", encoding="utf-8")

        cli.cmd_segment("tajawuz")

        self.assertFalse(orphan.exists(), "stale piece from a prior run must not survive re-segmentation")
        self.assertTrue((book_staging / "report.md").exists())
        self.assertTrue((book_staging / "segments.json").exists())

    def test_rerunning_segment_is_still_safe_and_produces_a_report(self):
        cli.cmd_segment("tajawuz")
        cli.cmd_segment("tajawuz")
        book_staging = self.staging_root / "tajawuz"
        self.assertTrue((book_staging / "report.md").exists())


if __name__ == "__main__":
    unittest.main()
