import json
import shutil
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from tools.inpage.emit import _piece, write_book, write_segment, write_segments
from tools.inpage.models import Book, Segment
from tools.inpage.promote import promote
from tools.inpage.report import render
from tools.migrate.emit import frontmatter


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

    def test_a_normal_titles_slug_is_unchanged_by_the_cap(self):
        # A title short enough to be unaffected by MAX_SLUG_LENGTH must
        # produce the byte-identical slug it always has.
        segment = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="الف\nب", order=1)
        path = write_segment(segment, "tajawuz", self.root)
        self.assertEqual(path.name, "raat-ak-lehar-ruki-pani-mein.md")

    def test_written_note_survives_into_the_emitted_frontmatter(self):
        # A colophon attached in segment.py must actually reach the file a
        # human reviews, not just live on the Segment in memory.
        note = "۱۷، مئی ۲۰۱۰ئ۔ لاہور"
        segment = Segment(
            kind="ghazals", title="پہلی نظم", body="اول\nدوم", order=1,
            written_note=note,
        )
        piece = _piece(segment, "tajawuz")
        text = frontmatter(piece)
        self.assertIn(f"written_note: {json.dumps(note, ensure_ascii=False)}", text)

    def test_an_over_long_title_produces_a_capped_slug(self):
        # A misdetected paragraph run with no line break produced a "title"
        # ~1400 characters long in the پہلا pilot run; its slug was long
        # enough to raise OSError on write. The slug must be capped at
        # MAX_SLUG_LENGTH (80), truncated at a `-` boundary.
        long_title = "غلام حسین ساجد " * 100
        segment = Segment(kind="ghazals", title=long_title, body="الف\nب", order=1)
        path = write_segment(segment, "tajawuz", self.root)
        slug = path.stem
        self.assertLessEqual(len(slug), 80)
        self.assertNotIn("--", slug)
        self.assertFalse(slug.endswith("-"))


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
        paths, slugs, problems = write_segments([first, second], "tajawuz", self.root)

        self.assertEqual(len(paths), 2)
        self.assertEqual(paths[0].name, "raat-ak-lehar-ruki-pani-mein.md")
        self.assertEqual(paths[1].name, "raat-ak-lehar-ruki-pani-mein-2.md")
        self.assertEqual(slugs, ["raat-ak-lehar-ruki-pani-mein", "raat-ak-lehar-ruki-pani-mein-2"])
        self.assertIn("اول", paths[0].read_text(encoding="utf-8"))
        self.assertIn("دوم", paths[1].read_text(encoding="utf-8"))
        self.assertTrue(problems)
        self.assertIn("collision", problems[0])

    def test_no_collision_no_problems(self):
        first = Segment(kind="ghazals", title="پہلی نظم", body="اول", order=1)
        second = Segment(kind="nazms", title="دوسری نظم", body="دوم", order=2)
        paths, slugs, problems = write_segments([first, second], "tajawuz", self.root)
        self.assertEqual(len(paths), 2)
        self.assertEqual(slugs[0], "pahli-nazm")
        self.assertEqual(len(slugs), 2)
        self.assertNotEqual(slugs[0], slugs[1])
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
        text = write_book(book, [], self.root).read_text(encoding="utf-8")
        self.assertNotIn("year:", text)

    def test_uses_the_slugs_write_segments_resolved_on_collision(self):
        # write_segments disambiguates a collision to <slug>-2; write_book
        # must record that same resolved slug rather than re-deriving its
        # own (independently unaware of the counter) and listing the base
        # slug twice, which would make one contents row point at the wrong
        # poem and orphan the "-2" file from the book record entirely.
        first = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="اول", order=1)
        second = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="دوم", order=2)
        staging_root = Path(tempfile.mkdtemp())
        try:
            _, slugs, _ = write_segments([first, second], "tajawuz", staging_root)
            book = Book(title="تجاوز", slug="tajawuz", contents=[first, second])
            text = write_book(book, slugs, self.root).read_text(encoding="utf-8")
        finally:
            shutil.rmtree(staging_root)

        self.assertEqual(slugs, [
            "raat-ak-lehar-ruki-pani-mein",
            "raat-ak-lehar-ruki-pani-mein-2",
        ])
        lines = [line for line in text.splitlines() if "slug:" in line and "  - {" in line]
        self.assertEqual(len(lines), 2)
        self.assertIn('slug: "raat-ak-lehar-ruki-pani-mein"', lines[0])
        self.assertIn('slug: "raat-ak-lehar-ruki-pani-mein-2"', lines[1])
        self.assertNotIn(lines[0], lines[1])


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
        write_book(book, ["pahli-nazm"], book_staging)

        written, problems = promote("tajawuz", self.staging, self.content)

        target = self.content / "books" / "tajawuz.yaml"
        self.assertTrue(target.exists())
        self.assertIn(target, written)
        self.assertFalse(any("book record" in p for p in problems))

    def test_does_not_overwrite_an_existing_book_record(self):
        segment = Segment(kind="ghazals", title="پہلی نظم", body="اول\nدوم", order=1)
        book_staging = self._stage_approved("tajawuz", [segment])
        book = Book(title="تجاوز", slug="tajawuz", contents=[segment])
        write_book(book, ["pahli-nazm"], book_staging)

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
        _, _, staging_problems = write_segments([first, second], "tajawuz", book_staging)
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

    def test_orphaned_staging_file_from_a_prior_run_is_not_promoted(self):
        # Regression for the stale-orphan bug: a book is segmented (2 pieces),
        # then re-segmented after a fix down to 1 piece. The approval gate
        # binds to segments.json, but promote must ALSO refuse to copy
        # whatever .md files are still sitting in staging from the first run
        # — it may only copy what the approved segments.json names.
        first = Segment(kind="ghazals", title="پہلی نظم", body="اول", order=1)
        second = Segment(kind="ghazals", title="دوسری نظم", body="دوم", order=2)
        book_staging = self.staging / "tajawuz"
        write_segments([first, second], "tajawuz", book_staging)  # first run: 2 pieces

        # Re-segment down to just `first` — `second`'s .md is now an orphan.
        segments_path = book_staging / "segments.json"
        segments_path.write_text(
            json.dumps([asdict(first)]), encoding="utf-8"
        )
        report_text = render("tajawuz", [first], []).replace(
            "approved: false", "approved: true"
        )
        (book_staging / "report.md").write_text(report_text, encoding="utf-8")

        written, problems = promote("tajawuz", self.staging, self.content)

        names = sorted(p.name for p in written)
        self.assertEqual(names, ["pahli-nazm.md"])
        self.assertFalse((self.content / "ghazals" / "dosri-nazm.md").exists())
        self.assertFalse(any("dosri" in p for p in problems))

    def test_piece_named_in_segments_json_but_missing_from_disk_is_reported(self):
        segment = Segment(kind="ghazals", title="پہلی نظم", body="اول\nدوم", order=1)
        book_staging = self.staging / "tajawuz"
        book_staging.mkdir(parents=True)
        segments_path = book_staging / "segments.json"
        segments_path.write_text(json.dumps([asdict(segment)]), encoding="utf-8")
        report_text = render("tajawuz", [segment], []).replace(
            "approved: false", "approved: true"
        )
        (book_staging / "report.md").write_text(report_text, encoding="utf-8")
        # Deliberately never wrote pahli-nazm.md into staging.

        written, problems = promote("tajawuz", self.staging, self.content)

        self.assertEqual(written, [])
        self.assertTrue(any("missing" in p and "pahli-nazm" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
