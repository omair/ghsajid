import json
import tempfile
import unittest
from pathlib import Path

from tools.migrate.emit import (
    existing_origin,
    frontmatter,
    write_container,
    write_piece,
    write_postmap,
)
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

    def test_origin_defaults_to_tool(self):
        self.assertIn('origin: "tool"', frontmatter(piece()))

    def test_origin_human_is_rendered(self):
        self.assertIn('origin: "human"', frontmatter(piece(origin="human")))

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

    def test_write_piece_stamps_tool_origin_by_default(self):
        path = write_piece(piece(), self.root)
        self.assertEqual(existing_origin(path), "tool")

    def test_write_piece_never_overwrites_a_human_file(self):
        # A person's own piece sits where the generator would write. It must be
        # left byte-for-byte untouched, and the write reports the skip as None.
        path = self.root / "ghazals" / "abc.md"
        path.parent.mkdir(parents=True)
        human = '---\ntitle: "دستی"\norigin: "human"\n---\n\nمصرعِ آدمی\n'
        path.write_text(human, encoding="utf-8")

        result = write_piece(piece(body="regenerated"), self.root)

        self.assertIsNone(result)
        self.assertEqual(path.read_text(encoding="utf-8"), human)

    def test_write_piece_overwrites_a_tool_file(self):
        write_piece(piece(body="first"), self.root)
        result = write_piece(piece(body="second"), self.root)
        self.assertIsNotNone(result)
        self.assertIn("second", result.read_text(encoding="utf-8"))

    def test_existing_origin_is_none_when_absent(self):
        self.assertIsNone(existing_origin(self.root / "nope.md"))

    def test_existing_origin_ignores_a_body_without_frontmatter(self):
        # A file that does not open with a `---` fence but whose body contains
        # `---`-delimited text with an origin-like line must not be mistaken
        # for a protected human piece.
        path = self.root / "loose.md"
        path.write_text(
            "just prose\n\n---\norigin: human\n---\nmore\n", encoding="utf-8"
        )
        self.assertIsNone(existing_origin(path))

    def test_container_keeps_a_human_added_chapter(self):
        # A human memoir chapter on disk must survive regeneration of the
        # container from the export's (tool) survivors.
        (self.root / "memoir").mkdir(parents=True)
        (self.root / "memoir" / "dars-gah-2.md").write_text(
            '---\ntitle: "نیا باب"\nslug: "dars-gah-2"\norigin: "human"\npart: 2\n---\n\nمتن\n',
            encoding="utf-8",
        )
        tool_part = piece(kind="memoir", slug="dars-gah-1", extra={"part": 1})
        path = write_container([tool_part], self.root)
        text = path.read_text(encoding="utf-8")
        self.assertIn("dars-gah-1", text)
        self.assertIn("dars-gah-2", text)
        self.assertLess(text.index("dars-gah-1"), text.index("dars-gah-2"))

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
