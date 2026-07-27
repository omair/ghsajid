"""Tests for the tools.inpage.__main__ CLI wiring — staging lifecycle."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.inpage import __main__ as cli

TAJAWUZ = Path("inp/TAJAWUZ.INP")


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
