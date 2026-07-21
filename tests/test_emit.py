import json
import tempfile
import unittest
from pathlib import Path

from tools.migrate.emit import frontmatter, write_container, write_piece, write_postmap
from tools.migrate.models import Piece


def piece(**kw):
    base = dict(
        kind="ghazals", slug="abc", title="عنوان", language="urdu",
        script="nastaliq", published="2020-03-25", body="مصرع",
    )
    base.update(kw)
    return Piece(**base)


class TestFrontmatter(unittest.TestCase):
    def test_has_required_fields(self):
        fm = frontmatter(piece())
        self.assertIn('title: "عنوان"', fm)
        self.assertIn('slug: "abc"', fm)
        self.assertIn('language: "urdu"', fm)
        self.assertIn('script: "nastaliq"', fm)
        self.assertIn("published: 2020-03-25", fm)

    def test_omits_empty_optional_fields(self):
        fm = frontmatter(piece())
        self.assertNotIn("published_in", fm)
        self.assertNotIn("tags", fm)

    def test_renders_lists(self):
        fm = frontmatter(piece(extra={"published_in": ["caarwan.com"]}))
        self.assertIn('published_in: ["caarwan.com"]', fm)

    def test_escapes_embedded_quotes(self):
        fm = frontmatter(piece(title='کتاب "شعور"'))
        self.assertIn(r'title: "کتاب \"شعور\""', fm)

    def test_quoted_values_are_parseable_scalars(self):
        # YAML double-quoted scalars are JSON strings, so a valid emission
        # must round-trip through json.loads. This catches escaping bugs that
        # a substring assertion cannot.
        for title in ['کتاب "شعور"', "back\\slash", "پہلا\tدوسرا", "plain"]:
            line = frontmatter(piece(title=title)).splitlines()[0]
            value = line[len("title: "):]
            self.assertEqual(json.loads(value), title)


class TestWrite(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_piece_creates_file_at_kind_path(self):
        path = write_piece(piece(), self.root)
        self.assertEqual(path, self.root / "ghazals" / "abc.md")
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        self.assertTrue(text.rstrip().endswith("مصرع"))

    def test_write_container_lists_parts_in_order(self):
        parts = [
            piece(kind="memoir", slug="dars-gah-2", extra={"part": 2}),
            piece(kind="memoir", slug="dars-gah-1", extra={"part": 1}),
        ]
        path = write_container(parts, self.root)
        text = path.read_text(encoding="utf-8")
        self.assertEqual(path, self.root / "containers" / "dars-gah.yaml")
        self.assertLess(text.index("dars-gah-1"), text.index("dars-gah-2"))

    def test_write_postmap_emits_json_keyed_by_post_id(self):
        out = self.root / "_postmap.json"
        write_postmap({94: "/dars-gah/14"}, out)
        self.assertEqual(json.loads(out.read_text()), {"94": "/dars-gah/14"})


if __name__ == "__main__":
    unittest.main()
