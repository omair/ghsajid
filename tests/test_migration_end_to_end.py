import unittest
from pathlib import Path

from tools.migrate.__main__ import build_pieces
from tools.migrate.wxr import parse_posts

EXPORT = Path("data/export.xml")


class TestFullMigration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.survivors, cls.redirects, cls.removed = build_pieces(parse_posts(EXPORT))

    def test_produces_the_expected_file_count(self):
        self.assertEqual(len(self.survivors), 96)

    def test_kind_counts_match_the_spec(self):
        counts: dict[str, int] = {}
        for p in self.survivors:
            counts[p.kind] = counts.get(p.kind, 0) + 1
        self.assertEqual(
            counts,
            {"memoir": 53, "ghazals": 21, "reviews": 9, "nazms": 4, "videos": 9},
        )

    def test_both_duplicates_are_redirected(self):
        self.assertEqual(len(self.redirects), 2)

    def test_memoir_parts_are_numbered_one_to_fiftythree(self):
        parts = sorted(p.extra["part"] for p in self.survivors if p.kind == "memoir")
        self.assertEqual(parts, list(range(1, 54)))

    def test_punjabi_pieces_carry_shahmukhi_script(self):
        punjabi = [p for p in self.survivors if p.language == "punjabi"]
        self.assertTrue(punjabi)
        self.assertTrue(all(p.script == "shahmukhi" for p in punjabi))

    def test_reviews_are_split_into_book_and_author(self):
        reviews = [p for p in self.survivors if p.kind == "reviews"]
        parsed = [r for r in reviews if r.extra.get("reviewed_author")]
        self.assertEqual(len(parsed), 7)   # 2 titles do not match the pattern

    def test_ghazal_colophons_move_to_frontmatter(self):
        noted = [
            p for p in self.survivors
            if p.kind == "ghazals" and p.extra.get("written_note")
        ]
        self.assertEqual(len(noted), 2)
        self.assertTrue(any("بستی کبیر سنپال" in p.extra["written_note"] for p in noted))

    def test_no_ghazal_ends_with_a_stray_single_line(self):
        for p in self.survivors:
            if p.kind != "ghazals":
                continue
            stanzas = [s for s in p.body.split("\n\n") if s.strip()]
            if len(stanzas) > 1:
                self.assertTrue(
                    all(len(s.split("\n")) % 2 == 0 for s in stanzas),
                    f"{p.slug} has an odd sher",
                )

    def test_no_slug_is_empty_or_duplicated(self):
        keys = [(p.kind, p.slug) for p in self.survivors]
        self.assertTrue(all(slug for _, slug in keys))
        self.assertEqual(len(set(keys)), len(keys))


if __name__ == "__main__":
    unittest.main()
