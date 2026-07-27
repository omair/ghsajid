import unittest
from pathlib import Path

EXPORT = Path("data/export.xml")

INPAGE_SOURCES = [
    Path("inp/TAJAWUZ.INP"),
    Path("inp/BAGH E NISHAT KI TARAF.INP"),
    Path("inp/MAZAMEER (1).INP"),
    Path("inp/MAZAMEER (2).INP"),
]


class TestExportPresent(unittest.TestCase):
    def test_export_is_present(self):
        self.assertTrue(EXPORT.exists(), "run: cp <download> data/export.xml")
        self.assertGreater(EXPORT.stat().st_size, 1_000_000)


class TestInPageSourcesPresent(unittest.TestCase):
    def test_inpage_sources_are_present(self):
        for path in INPAGE_SOURCES:
            self.assertTrue(
                path.exists(),
                f"missing {path}: these are local-only book scans/files, not "
                "committed to the repo; supply them under inp/ before running "
                "the InPage ground-truth gate",
            )


if __name__ == "__main__":
    unittest.main()
