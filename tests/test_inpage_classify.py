import unittest

from tools.inpage import classify
from tools.inpage.models import Paragraph


def para(text, geometry=50):
    return Paragraph(text=text, geometry=geometry, raw=text, codes=[])


# Four alternating verse-length paragraphs (two shers) — this is what starts
# the body. A single sher is not enough: see test_a_sher_shaped_publisher_
# block_does_not_start_the_body below for why.
BODY = [
    para("ا" * 36, 73),
    para("ب" * 36, 1),
    para("ج" * 36, 74),
    para("د" * 36, 1),
]


class TestBodyStart(unittest.TestCase):
    def test_finds_the_first_alternating_verse_run(self):
        paras = [para("سرورق", 20)] + BODY
        self.assertEqual(classify.body_start_index(paras), 1)

    def test_returns_length_when_no_verse_run_exists(self):
        paras = [para("سرورق", 20), para("ناشر", 32)]
        self.assertEqual(classify.body_start_index(paras), len(paras))

    def test_requires_the_alternation_to_hold_for_the_whole_run(self):
        paras = [
            para("ا" * 36, 73),
            para("ب" * 36, 77),  # breaks the alternation: not geometry 1
            para("ج" * 36, 74),
            para("د" * 36, 1),
        ]
        self.assertEqual(classify.body_start_index(paras), len(paras))

    def test_a_sher_shaped_publisher_block_does_not_start_the_body(self):
        # تجاوز's own front matter: رنگِ ادب پبلی کیشنز (19 chars, geometry
        # 81) followed by its کراچی office address (38 chars, geometry 1) —
        # one alternating pair, coincidentally sher-shaped. A 2-paragraph
        # rule would start the body here, swallowing the فہرست that precedes
        # it. Four paragraphs of real alternation are required instead, so
        # the body should start where BODY actually begins.
        publisher = [
            para("رنگِ ادب پبلی کیشنز", 81),
            para("آفس نمبرکتاب مارکیٹ ،اُردو بازار،کراچی", 1),
        ]
        front_matter = [para("ناشر", 32)]
        paras = publisher + front_matter + BODY
        self.assertEqual(
            classify.body_start_index(paras), len(publisher) + len(front_matter)
        )


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


class TestTocCount(unittest.TestCase):
    def test_reads_the_highest_entry_number(self):
        paras = [para("۱۔۲۔۳۔", 80), para("۴۔۵۔", 86)] + BODY
        self.assertEqual(classify.toc_count(paras), 5)

    def test_ignores_the_zeroes_of_a_separator(self):
        paras = [para("۱۔۲۔", 80), para("۰۰۰", 1)] + BODY
        self.assertEqual(classify.toc_count(paras), 2)

    def test_returns_none_when_there_is_no_toc(self):
        self.assertIsNone(classify.toc_count(list(BODY)))

    def test_ignores_numbers_after_the_body_starts(self):
        paras = [para("۱۔۲۔", 80)] + BODY + [para("۹۹۔", 40)]
        self.assertEqual(classify.toc_count(paras), 2)


if __name__ == "__main__":
    unittest.main()
