"""Tests for the tools.inpage.__main__ CLI wiring — staging lifecycle."""

import re
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


class TestCmdPromoteValidatesItsSlug(unittest.TestCase):
    """`promote` must reject a slug that is not a known book.

    cmd_segment validates via _load; cmd_promote did not, so
    `promote ../../x` joined an arbitrary path onto out/staging and read
    whatever it found there as an approved staging tree.
    """

    def test_an_unknown_slug_exits(self):
        with self.assertRaises(SystemExit) as caught:
            cli.cmd_promote("no-such-book")
        self.assertIn("unknown book", str(caught.exception))

    def test_a_traversal_slug_exits(self):
        with self.assertRaises(SystemExit) as caught:
            cli.cmd_promote("../../x")
        self.assertIn("unknown book", str(caught.exception))

    def test_it_rejects_before_touching_the_filesystem(self):
        with mock.patch.object(cli, "promote") as promoted:
            with self.assertRaises(SystemExit):
                cli.cmd_promote("../../x")
        promoted.assert_not_called()


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


class TestCmdRestampValidatesItsSlug(unittest.TestCase):
    """`restamp` must reject an unknown book slug, same as segment/promote."""

    def test_an_unknown_slug_exits(self):
        with self.assertRaises(SystemExit) as caught:
            cli.cmd_restamp("no-such-book")
        self.assertIn("unknown book", str(caught.exception))

    def test_it_rejects_before_touching_the_filesystem(self):
        with mock.patch.object(cli, "restamp_report") as restamped:
            with self.assertRaises(SystemExit):
                cli.cmd_restamp("../../x")
        restamped.assert_not_called()


@unittest.skipUnless(TAJAWUZ.exists(), "inp/ sources not present")
class TestCmdRestamp(unittest.TestCase):
    """restamp reads only what segment already staged, and never re-segments.

    Rather than run segment against the real book (forbidden — out/staging/
    holds a live, partially-approved tree), this points cli.STAGING at a
    temp dir the test controls, and cmd_segment writes into that instead.
    """

    def setUp(self):
        self.staging_root = Path(tempfile.mkdtemp())
        self._patcher = mock.patch.object(cli, "STAGING", self.staging_root)
        self._patcher.start()
        cli.cmd_segment("tajawuz")
        self.book_staging = self.staging_root / "tajawuz"
        self.report_path = self.book_staging / "report.md"

    def tearDown(self):
        self._patcher.stop()
        shutil.rmtree(self.staging_root)

    def _approve(self):
        text = self.report_path.read_text(encoding="utf-8")
        self.report_path.write_text(
            text.replace("approved: false", "approved: true"), encoding="utf-8"
        )

    def test_restamp_on_an_untouched_tree_keeps_the_hash_and_forces_unapproved(self):
        self._approve()
        before = self.report_path.read_text(encoding="utf-8")
        before_hash = re.search(r"segmentation:\s*([0-9a-f]{16})", before).group(1)

        cli.cmd_restamp("tajawuz")

        after = self.report_path.read_text(encoding="utf-8")
        after_hash = re.search(r"segmentation:\s*([0-9a-f]{16})", after).group(1)
        self.assertEqual(before_hash, after_hash)
        # Check the literal line the gate reads, not a raw substring — the
        # approval instructions legitimately mention "approved: true" as an
        # example of the required literal.
        approval_at = after.rfind("## Approval")
        section = after[approval_at:]
        self.assertRegex(section, r"(?m)^approved: false\s*$")
        self.assertNotRegex(section, r"(?m)^approved: true\s*$")

    def test_restamp_never_rewrites_a_staged_piece(self):
        pieces_dir = self.book_staging / "ghazals"
        piece_path = next(pieces_dir.glob("*.md"))
        before_bytes = piece_path.read_bytes()

        cli.cmd_restamp("tajawuz")

        self.assertEqual(before_bytes, piece_path.read_bytes())

    def test_restamp_rejects_an_unknown_book_slug(self):
        with self.assertRaises(SystemExit) as caught:
            cli.cmd_restamp("no-such-book")
        self.assertIn("unknown book", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
