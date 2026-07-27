import unittest

from tools.inpage.models import Paragraph
from tools.inpage.segment import segment


def para(text, geometry):
    return Paragraph(text=text, geometry=geometry, codes=[])


class TestSegment(unittest.TestCase):
    def test_a_section_heading_opens_a_section(self):
        paras = [para("غزلیں", 15), para("پہلا مصرع", 63), para("دوسرا مصرع", 65)]
        segments = segment(paras)
        self.assertEqual(segments[0].section, "غزلیں")

    def test_a_geometry_reset_starts_a_new_piece(self):
        paras = [
            para("الف", 63), para("ب", 65),
            para("ج", 63), para("د", 65),
        ]
        segments = segment(paras)
        self.assertEqual(len(segments), 2)

    def test_piece_is_titled_by_its_first_line(self):
        paras = [para("جسم کی خوشبو الگ ہے", 63), para("خواب کی دنیا الگ ہے", 65)]
        self.assertEqual(segment(paras)[0].title, "جسم کی خوشبو الگ ہے")

    def test_pieces_are_numbered_in_book_order(self):
        paras = [para("الف", 63), para("ب", 65), para("ج", 63), para("د", 65)]
        self.assertEqual([s.order for s in segment(paras)], [1, 2])

    def test_an_odd_line_count_is_flagged_not_dropped(self):
        paras = [para("الف", 63), para("ب", 65), para("ج", 67)]
        self.assertIn("odd-line-count", segment(paras)[0].flags)

    def test_body_joins_lines_into_couplets(self):
        paras = [para("الف", 63), para("ب", 65), para("ج", 67), para("د", 69)]
        self.assertEqual(segment(paras)[0].body, "الف\nب\n\nج\nد")

    def test_a_heading_with_a_diacritic_is_still_recognised(self):
        # گُل سیمیا carries a pesh on the گ; skeleton() strips it before
        # comparison, so this must still open the گل سیمیا section.
        paras = [para("گُل سیمیا", 15), para("پہلا مصرع", 63), para("دوسرا مصرع", 65)]
        segments = segment(paras)
        self.assertEqual(segments[0].section, "گل سیمیا")


if __name__ == "__main__":
    unittest.main()
