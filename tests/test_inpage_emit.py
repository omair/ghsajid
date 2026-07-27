import json
import shutil
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from tools.inpage.emit import write_book, write_segment, write_segments
from tools.inpage.models import Book, Segment
from tools.inpage.promote import promote
from tools.inpage.report import render


class TestWriteSegment(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_writes_frontmatter_without_a_published_date(self):
        segment = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="الف\nب", order=3)
        path = write_segment(segment, "tajawuz", self.root)
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("published:", text)
        self.assertIn('source_book: "tajawuz"', text)
        self.assertIn("book_order: 3", text)

    def test_slug_matches_the_migrate_slugifier(self):
        segment = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="الف\nب", order=1)
        path = write_segment(segment, "tajawuz", self.root)
        self.assertEqual(path.name, "raat-ak-lehar-ruki-pani-mein.md")


class TestWriteSegments(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_writes_both_poems_on_slug_collision(self):
        # Different titles that slugify identically once diacritics/whitespace
        # are stripped — same underlying string here, forced for the test.
        first = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="اول", order=1)
        second = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="دوم", order=2)
        paths, problems = write_segments([first, second], "tajawuz", self.root)

        self.assertEqual(len(paths), 2)
        self.assertEqual(paths[0].name, "raat-ak-lehar-ruki-pani-mein.md")
        self.assertEqual(paths[1].name, "raat-ak-lehar-ruki-pani-mein-2.md")
        self.assertIn("اول", paths[0].read_text(encoding="utf-8"))
        self.assertIn("دوم", paths[1].read_text(encoding="utf-8"))
        self.assertTrue(problems)
        self.assertIn("collision", problems[0])

    def test_no_collision_no_problems(self):
        first = Segment(kind="ghazals", title="پہلی نظم", body="اول", order=1)
        second = Segment(kind="nazms", title="دوسری نظم", body="دوم", order=2)
        paths, problems = write_segments([first, second], "tajawuz", self.root)
        self.assertEqual(len(paths), 2)
        self.assertEqual(problems, [])

    def test_deterministic_on_a_fresh_root(self):
        first = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="اول", order=1)
        second = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="دوم", order=2)

        root_a = Path(tempfile.mkdtemp())
        root_b = Path(tempfile.mkdtemp())
        try:
            names_a = [p.name for p in write_segments([first, second], "tajawuz", root_a)[0]]
            names_b = [p.name for p in write_segments([first, second], "tajawuz", root_b)[0]]
            self.assertEqual(names_a, names_b)
        finally:
            shutil.rmtree(root_a)
            shutil.rmtree(root_b)


class TestWriteBook(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_omits_an_unknown_year(self):
        book = Book(title="تجاوز", slug="tajawuz", publisher="رنگ ادب")
        text = write_book(book, self.root).read_text(encoding="utf-8")
        self.assertNotIn("year:", text)


class TestPromote(unittest.TestCase):
    def setUp(self):
        self.staging = Path(tempfile.mkdtemp())
        self.content = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.staging)
        shutil.rmtree(self.content)

    def test_refuses_without_an_approved_report(self):
        (self.staging / "tajawuz").mkdir(parents=True)
        (self.staging / "tajawuz" / "report.md").write_text("approved: false\n", encoding="utf-8")
        written, problems = promote("tajawuz", self.staging, self.content)
        self.assertEqual(written, [])
        self.assertTrue(problems)

    def _stage_approved(self, book_slug, segments):
        """Write segments + an approved, current report into staging."""
        book_staging = self.staging / book_slug
        for segment in segments:
            write_segment(segment, book_slug, book_staging)
        segments_path = book_staging / "segments.json"
        segments_path.write_text(
            json.dumps([asdict(s) for s in segments]), encoding="utf-8"
        )
        report_text = render(book_slug, segments, []).replace(
            "approved: false", "approved: true"
        )
        (book_staging / "report.md").write_text(report_text, encoding="utf-8")
        return book_staging

    def test_skips_existing_piece_with_identical_text(self):
        segment = Segment(kind="ghazals", title="پہلی نظم", body="اول\nدوم", order=1)
        self._stage_approved("tajawuz", [segment])

        existing = write_segment(segment, "tajawuz", self.content)
        before = existing.read_bytes()

        written, problems = promote("tajawuz", self.staging, self.content)

        self.assertEqual(written, [])
        self.assertTrue(any("already in the archive, skipped" in p for p in problems))
        self.assertEqual(existing.read_bytes(), before)

    def test_reports_but_does_not_overwrite_differing_text(self):
        staged_segment = Segment(kind="ghazals", title="پہلی نظم", body="اول\nدوم", order=1)
        self._stage_approved("tajawuz", [staged_segment])

        archived_segment = Segment(kind="ghazals", title="پہلی نظم", body="سوم\nچہارم", order=1)
        existing = write_segment(archived_segment, "tajawuz", self.content)
        before = existing.read_bytes()

        written, problems = promote("tajawuz", self.staging, self.content)

        self.assertEqual(written, [])
        self.assertTrue(any("text differs from the archive" in p for p in problems))
        self.assertEqual(existing.read_bytes(), before)

    def test_copies_book_record_when_absent(self):
        segment = Segment(kind="ghazals", title="پہلی نظم", body="اول\nدوم", order=1)
        book_staging = self._stage_approved("tajawuz", [segment])
        book = Book(title="تجاوز", slug="tajawuz", contents=[segment])
        write_book(book, book_staging)

        written, problems = promote("tajawuz", self.staging, self.content)

        target = self.content / "books" / "tajawuz.yaml"
        self.assertTrue(target.exists())
        self.assertIn(target, written)
        self.assertFalse(any("book record" in p for p in problems))

    def test_does_not_overwrite_an_existing_book_record(self):
        segment = Segment(kind="ghazals", title="پہلی نظم", body="اول\nدوم", order=1)
        book_staging = self._stage_approved("tajawuz", [segment])
        book = Book(title="تجاوز", slug="tajawuz", contents=[segment])
        write_book(book, book_staging)

        target = self.content / "books" / "tajawuz.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('title: "تجاوز"\nyear: 1987\npublisher: "hand entered"\n', encoding="utf-8")
        before = target.read_bytes()

        written, problems = promote("tajawuz", self.staging, self.content)

        self.assertNotIn(target, written)
        self.assertTrue(any("book record" in p and "skipped" in p for p in problems))
        self.assertEqual(target.read_bytes(), before)

    def test_slug_collision_both_poems_reach_staging_and_are_promoted(self):
        first = Segment(kind="ghazals", title="پہلی نظم", body="اول", order=1)
        second = Segment(kind="ghazals", title="پہلی نظم", body="دوم", order=2)
        book_staging = self.staging / "tajawuz"
        _, staging_problems = write_segments([first, second], "tajawuz", book_staging)
        self.assertTrue(any("collision" in p for p in staging_problems))

        segments_path = book_staging / "segments.json"
        segments_path.write_text(
            json.dumps([asdict(s) for s in (first, second)]), encoding="utf-8"
        )
        report_text = render("tajawuz", [first, second], []).replace(
            "approved: false", "approved: true"
        )
        (book_staging / "report.md").write_text(report_text, encoding="utf-8")

        written, problems = promote("tajawuz", self.staging, self.content)

        names = sorted(p.name for p in written)
        self.assertEqual(names, ["pahli-nazm-2.md", "pahli-nazm.md"])
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
