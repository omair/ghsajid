import json
import unittest
from pathlib import Path

MAP = Path("functions/_postmap.json")


@unittest.skipUnless(MAP.exists(), "run: python3 -m tools.migrate")
class TestPostmap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(MAP.read_text(encoding="utf-8"))

    def test_every_post_has_a_destination(self):
        self.assertEqual(len(self.data), 98)
        self.assertTrue(all(v.startswith("/") for v in self.data.values()))

    def test_the_merged_ghazal_shares_its_destination(self):
        # 98 posts collapse onto 97 pages, so exactly one URL appears twice.
        destinations = list(self.data.values())
        self.assertEqual(len(destinations) - len(set(destinations)), 1)

    def test_keys_are_numeric_post_ids(self):
        self.assertTrue(all(k.isdigit() for k in self.data))


if __name__ == "__main__":
    unittest.main()
