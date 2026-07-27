import shutil
import tempfile
import unittest
from pathlib import Path

from tools.inpage.emit import write_book, write_segment
from tools.inpage.models import Book, Segment
from tools.inpage.promote import promote


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


if __name__ == "__main__":
    unittest.main()
