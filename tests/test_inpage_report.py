import unittest

from tools.inpage.models import Segment
from tools.inpage.report import is_approved, render, segmentation_hash

SEGMENTS = [
    Segment(kind="ghazals", title="جسم کی خوشبو الگ ہے", body="الف\nب", order=1),
    Segment(kind="ghazals", title="بستر لگا ہوا", body="ج", order=2, flags=["odd-line-count"]),
]


class TestRender(unittest.TestCase):
    def test_lists_every_segment_with_its_first_line(self):
        text = render("tajawuz", SEGMENTS, [])
        self.assertIn("جسم کی خوشبو الگ ہے", text)
        self.assertIn("بستر لگا ہوا", text)

    def test_shows_flags_so_they_cannot_be_missed(self):
        self.assertIn("odd-line-count", render("tajawuz", SEGMENTS, []))

    def test_starts_unapproved(self):
        self.assertIn("approved: false", render("tajawuz", SEGMENTS, []))

    def test_includes_gate_output(self):
        self.assertIn("unmapped char codes", render("tajawuz", SEGMENTS, ["unmapped char codes: 0x02"]))


class TestApproval(unittest.TestCase):
    def test_unapproved_report_is_not_approved(self):
        self.assertFalse(is_approved(render("tajawuz", SEGMENTS, []), SEGMENTS))

    def test_approved_report_is_approved(self):
        text = render("tajawuz", SEGMENTS, []).replace("approved: false", "approved: true")
        self.assertTrue(is_approved(text, SEGMENTS))

    def test_approval_does_not_survive_resegmentation(self):
        text = render("tajawuz", SEGMENTS, []).replace("approved: false", "approved: true")
        changed = SEGMENTS + [Segment(kind="ghazals", title="نیا", body="ہ", order=3)]
        self.assertFalse(is_approved(text, changed))

    def test_hash_is_stable_for_the_same_segmentation(self):
        self.assertEqual(segmentation_hash(SEGMENTS), segmentation_hash(list(SEGMENTS)))

    def test_title_with_embedded_approval_line_cannot_spoof_approval(self):
        spoofed = [
            Segment(kind="ghazals", title="foo\napproved: true", body="الف\nب", order=1),
            Segment(kind="ghazals", title="بستر لگا ہوا", body="ج", order=2),
        ]
        text = render("tajawuz", spoofed, [])
        self.assertNotIn("\napproved: true", text)
        self.assertFalse(is_approved(text, spoofed))

    def test_report_missing_approval_section_is_not_approved(self):
        text = render("tajawuz", SEGMENTS, []).replace("approved: false", "approved: true")
        text = text.split("## Approval")[0]
        self.assertFalse(is_approved(text, SEGMENTS))

    def test_report_missing_approved_line_is_not_approved(self):
        text = render("tajawuz", SEGMENTS, [])
        text = "\n".join(line for line in text.splitlines() if not line.startswith("approved:"))
        self.assertFalse(is_approved(text, SEGMENTS))

    def test_report_missing_hash_line_is_not_approved(self):
        text = render("tajawuz", SEGMENTS, []).replace("approved: false", "approved: true")
        text = "\n".join(line for line in text.splitlines() if not line.startswith("segmentation:"))
        self.assertFalse(is_approved(text, SEGMENTS))


class TestSegmentationHash(unittest.TestCase):
    def test_changes_when_body_content_shifts_but_length_is_unchanged(self):
        shifted = [
            Segment(kind="ghazals", title="جسم کی خوشبو الگ ہے", body="ب\nالف", order=1),
            Segment(kind="ghazals", title="بستر لگا ہوا", body="ج", order=2, flags=["odd-line-count"]),
        ]
        self.assertEqual(len(shifted[0].body), len(SEGMENTS[0].body))
        self.assertNotEqual(segmentation_hash(SEGMENTS), segmentation_hash(shifted))

    def test_changes_when_title_changes(self):
        changed = [
            Segment(kind="ghazals", title="ایک الگ عنوان", body="الف\nب", order=1),
            Segment(kind="ghazals", title="بستر لگا ہوا", body="ج", order=2, flags=["odd-line-count"]),
        ]
        self.assertNotEqual(segmentation_hash(SEGMENTS), segmentation_hash(changed))

    def test_changes_when_order_changes(self):
        changed = [
            Segment(kind="ghazals", title="جسم کی خوشبو الگ ہے", body="الف\nب", order=5),
            Segment(kind="ghazals", title="بستر لگا ہوا", body="ج", order=2, flags=["odd-line-count"]),
        ]
        self.assertNotEqual(segmentation_hash(SEGMENTS), segmentation_hash(changed))


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
        self.assertIn("ghazals", render("tajawuz", pieces, []))

    def test_verse_is_counted_in_sher(self):
        pieces = [Segment(kind="ghazals", title="مطلع", body="الف\nب\n\nج\nد", order=1)]
        self.assertIn("2 sher", render("tajawuz", pieces, []))

    def test_prose_is_not_counted_in_sher(self):
        pieces = [Segment(kind="reviews", title="مضمون", body="ا" * 300, order=1)]
        rendered = render("tajawuz", pieces, [])
        self.assertNotIn("sher", rendered)
        self.assertIn("reviews", rendered)
