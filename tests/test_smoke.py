import unittest
from pathlib import Path

EXPORT = Path("data/export.xml")


class TestExportPresent(unittest.TestCase):
    def test_export_is_present(self):
        self.assertTrue(EXPORT.exists(), "run: cp <download> data/export.xml")
        self.assertGreater(EXPORT.stat().st_size, 1_000_000)


if __name__ == "__main__":
    unittest.main()
