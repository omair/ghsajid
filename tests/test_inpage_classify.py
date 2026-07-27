import unittest

from tools.inpage import classify
from tools.inpage.models import Paragraph


def para(text, geometry=50):
    return Paragraph(text=text, geometry=geometry, raw=text, codes=[])


# Two alternating verse-length paragraphs — this is what starts the body.
BODY = [para("ا" * 36, 73), para("ب" * 36, 1)]


class TestBodyStart(unittest.TestCase):
    def test_finds_the_first_alternating_verse_pair(self):
        paras = [para("سرورق", 20)] + BODY
        self.assertEqual(classify.body_start_index(paras), 1)

    def test_returns_length_when_no_verse_run_exists(self):
        paras = [para("سرورق", 20), para("ناشر", 32)]
        self.assertEqual(classify.body_start_index(paras), len(paras))

    def test_requires_the_second_paragraph_to_have_geometry_one(self):
        paras = [para("ا" * 36, 73), para("ب" * 36, 77)]
        self.assertEqual(classify.body_start_index(paras), len(paras))


class TestKinds(unittest.TestCase):
    def kinds(self, paras):
        return classify.classify(paras)

    def test_separator_wins_over_toc(self):
        # ۰۰۰ is digits-only, so order matters.
        self.assertEqual(self.kinds([para("۰۰۰", 1)] + BODY)[0], classify.SEPARATOR)

    def test_digits_and_dots_are_toc(self):
        self.assertEqual(self.kinds([para("۹۳۔۹۴۔", 83)] + BODY)[0], classify.TOC)

    def test_section_heading_is_recognised_with_diacritics(self):
        self.assertEqual(self.kinds([para("گُل سیمیا", 7)] + BODY)[0], classify.HEADING)

    def test_year_line_is_a_colophon(self):
        # The year's trailing hamza decodes as ئ, not ء.
        self.assertEqual(
            self.kinds([para("۱۷، مئی ۲۰۱۰ئ۔ لاہور", 1)] + BODY)[0], classify.COLOPHON
        )

    def test_long_paragraph_is_prose(self):
        self.assertEqual(self.kinds([para("ا" * 300, 67)] + BODY)[0], classify.PROSE)

    def test_verse_length_inside_the_body_is_verse(self):
        self.assertEqual(self.kinds(BODY)[0], classify.VERSE)

    def test_verse_length_before_the_body_is_front_matter(self):
        paras = [para("رنگِ ادب پبلی کیشنز کراچی", 81)] + BODY
        self.assertEqual(self.kinds(paras)[0], classify.FRONT_MATTER)

    def test_short_paragraph_inside_the_body_is_unknown(self):
        # A nazm title candidate — resolved during assembly, not here.
        paras = BODY + [para("یاد", 1)]
        self.assertEqual(self.kinds(paras)[-1], classify.UNKNOWN)

    def test_every_paragraph_gets_exactly_one_kind(self):
        paras = [para("۰۰۰", 1), para("ناشر", 32)] + BODY
        self.assertEqual(len(self.kinds(paras)), len(paras))


if __name__ == "__main__":
    unittest.main()
