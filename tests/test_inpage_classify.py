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

    def test_body_starts_after_the_separator_preceding_the_run(self):
        # باغِ نشاط's shape: the critic's essay is closed by ۰۰۰, and the
        # epigraph couplet the book is named after, plus the opening lines of
        # its نعت, sit between that separator and the first ghazal-shaped
        # run. They are body, not front matter, so the boundary belongs at
        # the separator.
        paras = [
            para("سرورق", 20),
            para("۰۰۰", 1),
            para("باغِ نشاط کی طرف اپنے قدم نہیں بڑھے", 77),
            para("جب سے ہمارے کھوج میں بادِ صبا نہیں رہی", 1),
            para("نعت", 1),
        ] + BODY
        self.assertEqual(classify.body_start_index(paras), 2)

    def test_body_starts_at_the_run_when_no_separator_precedes_it(self):
        paras = [para("سرورق", 20), para("ناشر", 32)] + BODY
        self.assertEqual(classify.body_start_index(paras), 2)

    def test_the_search_for_a_separator_does_not_reach_back_over_prose(self):
        # An unclosed essay: the only ۰۰۰ is the one that opens it. Reaching
        # back to that separator would put the critic's prose inside the
        # poems, so the boundary stays at the run.
        paras = [
            para("سرورق", 20),
            para("۰۰۰", 80),
            para("الف" * 60, 67),
            para("شمع خیالِ سبز کی رنگ جما نہیں رہی", 73),
        ] + BODY
        self.assertEqual(classify.body_start_index(paras), 4)

    def test_only_a_separator_before_the_run_moves_the_boundary(self):
        # A ۰۰۰ *after* the run has nothing to say about where the body
        # begins, and the boundary must not jump forward to it.
        paras = [para("سرورق", 20)] + BODY + [para("۰۰۰", 1)]
        self.assertEqual(classify.body_start_index(paras), 1)

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

    def test_a_colophon_whose_digits_were_stripped_is_a_colophon(self):
        # InPage stores digits separately and they do not always survive
        # decoding. The four-digit rule above misses every such line — 52 of
        # them in کلیات جلد ۲, where a colophon is what closes the نظم it
        # follows. The month name and the year's hamza are what is left.
        self.assertEqual(
            self.kinds([para("یکم دسمبرئ۔ لاہور", 1)] + BODY)[0], classify.COLOPHON
        )

    def test_a_month_with_a_space_before_the_year_marker_is_a_colophon(self):
        # The vanished digits leave a gap of their own: `، اپریل ئ۔ لاہور`.
        self.assertEqual(
            self.kinds([para("، اپریل ئ۔ لاہور", 1)] + BODY)[0], classify.COLOPHON
        )

    def test_a_verse_line_naming_a_month_is_not_a_colophon(self):
        # A month alone is not evidence: a poem may simply name one. Without
        # the year marker in the year's own position this stays verse.
        self.assertEqual(
            self.kinds(BODY + [para("اپریل کی شام ڈھلی تو مجھے یاد آیا", 1)])[-1],
            classify.VERSE,
        )

    def test_a_month_far_from_the_year_marker_is_not_a_colophon(self):
        # ء/ئ is far too common a letter to accept anywhere in the line —
        # کوئی alone carries one. The marker must sit where the year sits,
        # separated from the month only by the digits that vanished and their
        # punctuation. کلیات جلد ۲ ¶1090, a real line of verse, is the
        # measured case: گُلِ غیب کی آگ سے رنگ لیتی ہوئی سُرمئی بے کلی
        # contains both مئی and ئ and must stay verse.
        self.assertEqual(
            self.kinds(
                BODY + [para("گُلِ غیب کی آگ سے رنگ لیتی ہوئی سُرمئی بے کلی", 1)]
            )[-1],
            classify.VERSE,
        )

    def test_a_year_marker_without_a_month_is_not_a_colophon_by_this_path(self):
        # The new path adds nothing on its own to a line with no month name;
        # only the four-digit rule can classify such a line.
        self.assertEqual(
            self.kinds(BODY + [para("کوئی صورت نظر نہیں آتی ئ", 1)])[-1],
            classify.VERSE,
        )

    def test_a_bracketed_publisher_imprint_is_not_a_colophon(self):
        # Shaped like a colophon but printed on a collection's title page:
        # کلیات جلد ۱ has four (¶248, ¶2125, ¶6789, ¶7874), each sitting
        # between the collection's name and its dedication. A publisher is
        # not where a poem was written, and those lines are part of the
        # title-page block `attribute_gathered_collections` reads. A whole
        # line in brackets is the shape that marks them: none of جلد ۲'s 52
        # digit-stripped colophons is bracketed, and every bracketed date
        # that IS a colophon (تجاوز ¶83, جلد ۱ ¶264, ¶5294) kept its four
        # digits and is still caught by the rule above.
        self.assertEqual(
            self.kinds([para("(یکم اکتوبر ئ،اورینٹ پبلشرز،لاہور)", 1)] + BODY)[0],
            classify.FRONT_MATTER,
        )

    def test_a_bracketed_colophon_that_kept_its_digits_is_still_a_colophon(self):
        # تجاوز ¶83. The bracket rule narrows only the new month path.
        self.assertEqual(
            self.kinds([para("(۵-مئی ۲۰۲۳ئ)", 1)] + BODY)[0], classify.COLOPHON
        )

    def test_a_long_line_naming_a_month_and_a_year_is_not_a_colophon(self):
        # The length bound stays: جلد ۱'s biographical note and اعتذار are
        # prose paragraphs of 333-722 characters that name months and carry
        # a stray ئ, and they are essays, not signatures.
        self.assertEqual(
            self.kinds([para("یہ جنوری ئ کی کسی سرد شام کا واقعہ ہے۔ " * 12, 67)]
                       + BODY)[0],
            classify.PROSE,
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

    def test_run_together_misras_inside_the_body_are_verse(self):
        # 67 chars — two misras joined by a comma, as the typesetter
        # sometimes ran them. This must not be discarded as UNKNOWN.
        paras = BODY + [para("ا" * 67, 1)]
        self.assertEqual(self.kinds(paras)[-1], classify.VERSE)

    def test_long_paragraph_inside_the_body_is_still_prose(self):
        paras = BODY + [para("ا" * 300, 1)]
        self.assertEqual(self.kinds(paras)[-1], classify.PROSE)

    def test_very_short_paragraph_inside_the_body_is_still_unknown(self):
        paras = BODY + [para("ا" * 3, 1)]
        self.assertEqual(self.kinds(paras)[-1], classify.UNKNOWN)

    def test_every_paragraph_gets_exactly_one_kind(self):
        paras = [para("۰۰۰", 1), para("ناشر", 32)] + BODY
        self.assertEqual(len(self.kinds(paras)), len(paras))


class TestShortLinesBetweenVerse(unittest.TestCase):
    """VERSE_MIN was measured on ghazals; free verse runs shorter than that.

    A nazm's line can be 7 characters where a misra is 28-42, so length alone
    files it UNKNOWN, the verse run breaks, and segment() emits the fragments
    as separate pieces. Position is the evidence length cannot supply: a short
    paragraph with VERSE on BOTH sides is inside a poem.
    """

    def kinds(self, extra):
        return classify.classify(list(BODY) + list(extra))

    def test_a_short_line_between_two_verse_lines_is_verse(self):
        kinds = self.kinds([para("سُکڑ کر", 1), para("ا" * 30, 1)])
        self.assertEqual(kinds[-2], classify.VERSE)

    def test_a_run_of_three_short_lines_between_verse_lines_is_verse(self):
        # کلیات جلد ۲ ¶877-879 — اِس کہانی میں / کشف کی رات / بہت دن بعد, three
        # consecutive lines of one poem. The gap may be any length.
        kinds = self.kinds([
            para("اِس کہانی میں", 1),
            para("کشف کی رات", 1),
            para("بہت دن بعد", 1),
            para("ا" * 30, 1),
        ])
        self.assertEqual(kinds[-4:-1], [classify.VERSE] * 3)

    def test_a_short_line_touching_verse_on_the_right_only_stays_unknown(self):
        # DECIDED: left as UNKNOWN. A nazm's title sits exactly here — یاد, 3
        # chars, immediately before its poem — and segment() reads UNKNOWN as
        # its one title candidate. Verse on one side is not evidence of
        # anything; verse on both is.
        kinds = self.kinds([
            para("۰۰۰", 1), para("یاد", 1), para("ا" * 30, 1),
        ])
        self.assertEqual(kinds[-2], classify.UNKNOWN)

    def test_a_short_line_touching_verse_on_the_left_only_stays_unknown(self):
        kinds = self.kinds([para("سُکڑ کر", 1), para("۰۰۰", 1)])
        self.assertEqual(kinds[-2], classify.UNKNOWN)

    def test_a_short_line_with_no_verse_neighbour_stays_unknown(self):
        kinds = self.kinds([para("۰۰۰", 1), para("سُکڑ کر", 1), para("۰۰۰", 1)])
        self.assertEqual(kinds[-2], classify.UNKNOWN)

    def test_a_running_header_between_verse_lines_is_not_bridged(self):
        # Page furniture is not a short line of the poem, and it is not
        # UNKNOWN either — the bridge must leave the kind it already has.
        header = [para("موسم", 60)] * (classify.RUNNING_HEADER_MIN + 1)
        kinds = self.kinds([para("ا" * 30, 1)] + header + [para("ب" * 30, 1)])
        self.assertEqual(kinds[-2], classify.RUNNING_HEADER)

    def test_a_short_line_before_the_body_is_still_front_matter(self):
        # The bridge only ever rewrites UNKNOWN, which exists only in the body.
        kinds = classify.classify(
            [para("ا" * 30, 1), para("یاد", 1), para("ب" * 30, 1)] + list(BODY)
        )
        self.assertEqual(kinds[1], classify.FRONT_MATTER)


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


class TestRunningHeaders(unittest.TestCase):
    """کلیات vol 2 prints the collection's name atop all 209 of its pages.

    Treated as section headings they would split a ghazal at every page turn;
    ignored entirely they would lose the only per-page record of which
    collection a poem belongs to.
    """

    def body(self, extra=()):
        # Four alternating verse-length paragraphs start the body.
        run = [para("ا" * 36, 73), para("ب" * 36, 1),
               para("ج" * 36, 75), para("د" * 36, 1)]
        return list(run) + list(extra)

    def test_a_heading_repeated_past_the_threshold_is_a_running_header(self):
        paras = self.body([para("نعت", 60)] * (classify.RUNNING_HEADER_MIN + 1))
        self.assertIn("نعت", classify.running_headers(paras))

    def test_a_heading_at_the_threshold_is_still_a_section_heading(self):
        paras = self.body([para("نعت", 60)] * classify.RUNNING_HEADER_MIN)
        self.assertEqual(classify.running_headers(paras), set())

    def test_a_heading_seen_once_is_a_section_heading(self):
        paras = self.body([para("غزلیں", 60)])
        self.assertEqual(classify.running_headers(paras), set())

    def test_classify_marks_running_headers_distinctly(self):
        paras = self.body([para("نعت", 60)] * (classify.RUNNING_HEADER_MIN + 1))
        kinds = classify.classify(paras)
        self.assertEqual(kinds[-1], classify.RUNNING_HEADER)

    def test_classify_still_marks_a_one_off_heading_as_heading(self):
        paras = self.body([para("غزلیں", 60)])
        self.assertEqual(classify.classify(paras)[-1], classify.HEADING)

    def test_only_body_headings_count(self):
        # A فہرست lists section names too; those are front matter, not pages.
        paras = [para("نعت", 60)] * 20 + self.body()
        self.assertEqual(classify.running_headers(paras), set())

    def test_a_repeated_line_is_a_header_whatever_its_text(self):
        # کلیات جلد ۱ prints موسم، عناصر، کتابِ صبح، آیندہ، معاملہ، روداد
        # atop its pages — none of them a name any list here anticipated.
        # Detection is by repetition, not by recognising the name.
        paras = self.body(
            [para("موسم", 60)] * (classify.RUNNING_HEADER_MIN + 1)
        )
        self.assertIn("موسم", classify.running_headers(paras))
        self.assertEqual(classify.classify(paras)[-1], classify.RUNNING_HEADER)

    def test_the_separator_is_never_a_running_header(self):
        # ۰۰۰ repeats freely (11 times in کلیات جلد ۲) and is punctuation.
        paras = self.body(
            [para(classify.SEPARATOR_TEXT, 60)]
            * (classify.RUNNING_HEADER_MIN + 1)
        )
        self.assertEqual(classify.running_headers(paras), set())
        self.assertEqual(classify.classify(paras)[-1], classify.SEPARATOR)

    def test_a_prose_length_repeat_is_not_a_running_header(self):
        # A page header is a short line. Prose is never page furniture.
        prose = "ا" * classify.PROSE_MIN
        paras = self.body([para(prose, 60)] * (classify.RUNNING_HEADER_MIN + 1))
        self.assertEqual(classify.running_headers(paras), set())

    def test_the_threshold_clears_the_measured_noise(self):
        # The real headers run 89-209 across the two کلیات volumes; the
        # highest non-header repeat measured anywhere is فہرست at 26.
        self.assertGreater(classify.RUNNING_HEADER_MIN, 26)
        self.assertLess(classify.RUNNING_HEADER_MIN, 89)


if __name__ == "__main__":
    unittest.main()
