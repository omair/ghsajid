import shutil
import tempfile
import unittest
from pathlib import Path

from tools.inpage.emit import write_book, write_segments
from tools.inpage.models import Book, Segment
from tools.inpage.report import is_approved, render, segmentation_hash

SEGMENTS = [
    Segment(kind="ghazals", title="جسم کی خوشبو الگ ہے", body="الف\nب", order=1),
    Segment(kind="ghazals", title="بستر لگا ہوا", body="ج", order=2, flags=["odd-line-count"]),
]


class TestRender(unittest.TestCase):
    def test_lists_every_segment_with_its_first_line(self):
        text = render("tajawuz", SEGMENTS, [], None)
        self.assertIn("جسم کی خوشبو الگ ہے", text)
        self.assertIn("بستر لگا ہوا", text)

    def test_shows_flags_so_they_cannot_be_missed(self):
        self.assertIn("odd-line-count", render("tajawuz", SEGMENTS, [], None))

    def test_starts_unapproved(self):
        self.assertIn("approved: false", render("tajawuz", SEGMENTS, [], None))

    def test_includes_gate_output(self):
        self.assertIn("unmapped char codes", render("tajawuz", SEGMENTS, ["unmapped char codes: 0x02"], None))


class TestApproval(unittest.TestCase):
    def test_unapproved_report_is_not_approved(self):
        self.assertFalse(
            is_approved(render("tajawuz", SEGMENTS, [], None), SEGMENTS, None, "")
        )

    def test_approved_report_is_approved(self):
        text = render("tajawuz", SEGMENTS, [], None).replace("approved: false", "approved: true")
        self.assertTrue(is_approved(text, SEGMENTS, None, ""))

    def test_approval_does_not_survive_resegmentation(self):
        text = render("tajawuz", SEGMENTS, [], None).replace("approved: false", "approved: true")
        changed = SEGMENTS + [Segment(kind="ghazals", title="نیا", body="ہ", order=3)]
        self.assertFalse(is_approved(text, changed, None, ""))

    def test_hash_is_stable_for_the_same_segmentation(self):
        self.assertEqual(segmentation_hash(SEGMENTS, None, ""), segmentation_hash(list(SEGMENTS), None, ""))

    def test_title_with_embedded_approval_line_cannot_spoof_approval(self):
        spoofed = [
            Segment(kind="ghazals", title="foo\napproved: true", body="الف\nب", order=1),
            Segment(kind="ghazals", title="بستر لگا ہوا", body="ج", order=2),
        ]
        text = render("tajawuz", spoofed, [], None)
        self.assertNotIn("\napproved: true", text)
        self.assertFalse(is_approved(text, spoofed, None, ""))

    def test_report_missing_approval_section_is_not_approved(self):
        text = render("tajawuz", SEGMENTS, [], None).replace("approved: false", "approved: true")
        text = text.split("## Approval")[0]
        self.assertFalse(is_approved(text, SEGMENTS, None, ""))

    def test_report_missing_approved_line_is_not_approved(self):
        text = render("tajawuz", SEGMENTS, [], None)
        text = "\n".join(line for line in text.splitlines() if not line.startswith("approved:"))
        self.assertFalse(is_approved(text, SEGMENTS, None, ""))

    def test_report_missing_hash_line_is_not_approved(self):
        text = render("tajawuz", SEGMENTS, [], None).replace("approved: false", "approved: true")
        text = "\n".join(line for line in text.splitlines() if not line.startswith("segmentation:"))
        self.assertFalse(is_approved(text, SEGMENTS, None, ""))


class TestSegmentationHash(unittest.TestCase):
    def test_changes_when_body_content_shifts_but_length_is_unchanged(self):
        shifted = [
            Segment(kind="ghazals", title="جسم کی خوشبو الگ ہے", body="ب\nالف", order=1),
            Segment(kind="ghazals", title="بستر لگا ہوا", body="ج", order=2, flags=["odd-line-count"]),
        ]
        self.assertEqual(len(shifted[0].body), len(SEGMENTS[0].body))
        self.assertNotEqual(segmentation_hash(SEGMENTS, None, ""), segmentation_hash(shifted, None, ""))

    def test_changes_when_title_changes(self):
        changed = [
            Segment(kind="ghazals", title="ایک الگ عنوان", body="الف\nب", order=1),
            Segment(kind="ghazals", title="بستر لگا ہوا", body="ج", order=2, flags=["odd-line-count"]),
        ]
        self.assertNotEqual(segmentation_hash(SEGMENTS, None, ""), segmentation_hash(changed, None, ""))

    def test_changes_when_order_changes(self):
        changed = [
            Segment(kind="ghazals", title="جسم کی خوشبو الگ ہے", body="الف\nب", order=5),
            Segment(kind="ghazals", title="بستر لگا ہوا", body="ج", order=2, flags=["odd-line-count"]),
        ]
        self.assertNotEqual(segmentation_hash(SEGMENTS, None, ""), segmentation_hash(changed, None, ""))


class TestHashCoversTheStagedBytes(unittest.TestCase):
    """The approval must bind to the bytes `promote` will actually copy.

    The hash used to digest segments.json alone while `promote` copied the
    staged .md files, so editing an approved staged file promoted text no
    report had ever described — and the hash still matched.
    """

    def setUp(self):
        self.staging = Path(tempfile.mkdtemp())
        self.segments = [
            Segment(kind="ghazals", title="پہلی نظم", body="اول\nدوم", order=1),
        ]
        _, slugs, _ = write_segments(self.segments, "tajawuz", self.staging)
        write_book(
            Book(title="تجاوز", slug="tajawuz", contents=self.segments),
            slugs,
            self.staging,
        )
        self.piece = self.staging / "ghazals" / "pahli-nazm.md"
        self.record = self.staging / "books" / "tajawuz.yaml"

    def tearDown(self):
        shutil.rmtree(self.staging)

    def _hash(self):
        return segmentation_hash(self.segments, self.staging, "tajawuz")

    def test_editing_a_staged_piece_changes_the_hash(self):
        before = self._hash()
        self.piece.write_text(
            self.piece.read_text(encoding="utf-8") + "\nسوم\n", encoding="utf-8"
        )
        self.assertNotEqual(before, self._hash())

    def test_editing_the_staged_book_record_changes_the_hash(self):
        before = self._hash()
        self.record.write_text(
            self.record.read_text(encoding="utf-8").replace("تجاوز", "کچھ اور"),
            encoding="utf-8",
        )
        self.assertNotEqual(before, self._hash())

    def test_an_untouched_tree_hashes_the_same_twice(self):
        self.assertEqual(self._hash(), self._hash())

    def test_a_missing_staged_piece_is_not_the_same_as_a_present_one(self):
        before = self._hash()
        self.piece.unlink()
        self.assertNotEqual(before, self._hash())

    def test_the_staged_hash_differs_from_the_segments_only_hash(self):
        self.assertNotEqual(segmentation_hash(self.segments, None, ""), self._hash())

    def test_approval_does_not_survive_an_edit_to_a_staged_piece(self):
        text = render("tajawuz", self.segments, [], self.staging).replace(
            "approved: false", "approved: true"
        )
        self.assertTrue(
            is_approved(text, self.segments, self.staging, "tajawuz")
        )
        self.piece.write_text("---\ntitle: \"x\"\n---\n\nبدلا ہوا\n", encoding="utf-8")
        self.assertFalse(
            is_approved(text, self.segments, self.staging, "tajawuz")
        )

    def test_approval_does_not_survive_an_edit_to_the_book_record(self):
        text = render("tajawuz", self.segments, [], self.staging).replace(
            "approved: false", "approved: true"
        )
        self.record.write_text(
            'title: "کوئی اور کتاب"\nslug: "tajawuz"\ncontents:\n', encoding="utf-8"
        )
        self.assertFalse(
            is_approved(text, self.segments, self.staging, "tajawuz")
        )


if __name__ == "__main__":
    unittest.main()


class TestPieceLineShowsKind(unittest.TestCase):
    """A reviewer must be able to tell prose from a ghazal at a glance.

    The line used to print only [section], which is the last heading seen, so
    a `reviews` piece displayed as [غزلیں] and a 3358-character essay was
    labelled "2 sher". That misread cost a real review pass.
    """

    def test_kind_is_shown_for_each_piece(self):
        pieces = [Segment(kind="ghazals", title="مطلع", body="الف\nب", order=1)]
        self.assertIn("ghazals", render("tajawuz", pieces, [], None))

    def test_verse_is_counted_in_sher(self):
        pieces = [Segment(kind="ghazals", title="مطلع", body="الف\nب\n\nج\nد", order=1)]
        self.assertIn("2 sher", render("tajawuz", pieces, [], None))

    def test_prose_is_not_counted_in_sher(self):
        pieces = [Segment(kind="reviews", title="مضمون", body="ا" * 300, order=1)]
        rendered = render("tajawuz", pieces, [], None)
        self.assertNotIn("sher", rendered)
        self.assertIn("reviews", rendered)
