import unittest
from unittest import mock

from tools.inpage.models import Paragraph
from tools.inpage.segment import (
    MAX_TITLE_LENGTH, _is_ghazal_shaped, is_matla, pair_shers, run_rhyme,
    segment, split_ghazals,
)


def para(text, geometry):
    return Paragraph(text=text, geometry=geometry, raw=text, codes=[])


FRONT = [para("رنگِ ادب پبلی کیشنز", 81), para("۱۔۲۔", 80)]


def _clean_shers(start: int, count: int) -> list[Paragraph]:
    """`count` distinct, cleanly-pairing shers, numbered from `start`.

    Distinct per-sher text (the running number) keeps `is_matla` from firing
    on any of them: each misra ends "اول"/"دوم", never matching across
    shers, so a run built from these never splits into extra ghazals.
    """
    lines: list[Paragraph] = []
    for i in range(start, start + count):
        lines.append(para(f"پہلا مصرع نمبر {i} یہاں پڑا اول", 73))
        lines.append(para(f"دوسرا مصرع نمبر {i} یہاں پڑا دوم", 1))
    return lines


# A single unpairable line, geometry not 1, with no partner on either side.
HALF_LINE = "تنہا مصرع یہاں کھڑا ہے"

GHAZAL = [
    # The second misra is lengthened from the brief's literal "کا جادو الگ"
    # (11 chars) to clear classify.VERSE_MIN (15) — below that floor, classify()
    # marks the line UNKNOWN rather than VERSE and the whole fixture never
    # reaches segment()'s ghazal-pairing branch. The radif ("الگ") and the
    # matlaa relationship to the first misra are unchanged.
    para("جسم کی خوشبو الگ", 73), para("میرے دل کا جادو الگ", 1),
    para("چاٹ لیتی ہے یہ فکر", 89), para("ہو نہ جائے تو الگ", 1),
]


class TestPairShers(unittest.TestCase):
    def test_pairs_on_the_second_misra_geometry(self):
        run = [para("پہلا", 73), para("دوسرا", 1)]
        self.assertEqual(pair_shers(run), [("پہلا", "دوسرا")])

    def test_pairs_several_shers_in_order(self):
        run = [para("ا", 73), para("ب", 1), para("ج", 89), para("د", 1)]
        self.assertEqual(pair_shers(run), [("ا", "ب"), ("ج", "د")])

    def test_a_trailing_unpaired_line_is_kept_as_a_half_sher(self):
        # Never drop a line: the second element is empty, and the caller flags it.
        run = [para("ا", 73), para("ب", 1), para("ج", 89)]
        self.assertEqual(pair_shers(run), [("ا", "ب"), ("ج", "")])


class TestIsMatla(unittest.TestCase):
    def test_true_when_both_misras_end_with_the_same_word(self):
        self.assertTrue(is_matla("عطر کی خوشبو الگ", "کا جادو الگ"))

    def test_true_on_a_multi_word_radif(self):
        self.assertTrue(is_matla("نئی چادر بچھی ہوئی", "سے بڑھ کر بچھی ہوئی"))

    def test_false_when_only_the_second_misra_rhymes(self):
        self.assertFalse(is_matla("چاٹ لیتی ہے یہ فکر", "ہو نہ جائے تو الگ"))

    def test_ignores_diacritics_and_punctuation(self):
        self.assertTrue(is_matla("عِطر کی خُوشبو الگ", "کا جادو، الگ"))

    def test_false_on_an_empty_second_misra(self):
        self.assertFalse(is_matla("کوئی مصرع", ""))


class TestSplitGhazals(unittest.TestCase):
    def test_starts_a_new_ghazal_at_each_matla(self):
        shers = [
            ("خوشبو الگ", "جادو الگ"),      # matla
            ("یہ فکر", "تو الگ"),
            ("دنیا الگ", "چراغوں کا الگ"),  # matla
        ]
        groups = split_ghazals(shers)
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(groups[0]), 2)

    def test_leading_shers_before_any_matla_are_kept_as_a_group(self):
        shers = [("یہ فکر", "تو الگ"), ("خوشبو الگ", "جادو الگ")]
        groups = split_ghazals(shers)
        self.assertEqual(len(groups), 2)

    def test_no_sher_is_lost(self):
        shers = [("a الگ", "b الگ"), ("c", "d"), ("e ہوئی", "f ہوئی"), ("g", "h")]
        self.assertEqual(sum(len(g) for g in split_ghazals(shers)), len(shers))


class TestRadifAwareMatla(unittest.TestCase):
    """The false-opening cases measured in the pilot books.

    Every fixture here is real text. Each one was a piece boundary the
    self-contained matlaa test invented, and each invented boundary truncated
    a real ghazal and left a 1-2 sher runt behind it: تجاوز over-split to 114
    ghazals against a فہرست of 100, باغِ نشاط to 96 against 85.
    """

    def test_a_first_misra_ending_on_the_bare_radif_is_not_an_opening(self):
        # The ghazal's radif is "ضروری ہے"; this sher's first misra ends
        # "گریزاں ہے". Sharing only the ubiquitous "ہے" is not a rhyme, and
        # reading it as one cut this ghazal into three pieces.
        shers = [
            ("یہ آئنہ ہے تو کیوں عکس سے گریزاں ہے", "یہ باغ ہے تو یہاں خار و خس ضروری ہے"),
            ("جو ہو سکے تو میاں نثر پر توجّہ دو", "اگرچہ شاعری بھی اس برس ضروری ہے"),
            ("بدن کے اپنے تقاضے ہیں، روح کے اپنے", "ورائے عشق ذرا سی ہوس ضروری ہے"),
        ]
        self.assertFalse(is_matla(shers[0][0], shers[0][1], run_rhyme(shers, 0)))

    def test_a_first_misra_ending_on_the_whole_rhyme_is_an_opening(self):
        # Same ghazal, its real matlaa: "مَس ضروری ہے" against "دسترس ضروری ہے".
        shers = [
            ("بدن کی سیر نہ گردن کا مَس ضروری ہے", "مگر وجود پہ کچھ دسترس ضروری ہے"),
            ("یہ آئنہ ہے تو کیوں عکس سے گریزاں ہے", "یہ باغ ہے تو یہاں خار و خس ضروری ہے"),
            ("جو ہو سکے تو میاں نثر پر توجّہ دو", "اگرچہ شاعری بھی اس برس ضروری ہے"),
        ]
        self.assertTrue(is_matla(shers[0][0], shers[0][1], run_rhyme(shers, 0)))

    def test_the_rhyme_is_read_as_characters_not_words(self):
        # The qafia is part of a word: نگ سے across سنگ/ترنگ/انگ. A word-tail
        # comparison sees only "سے" and then accepts "نیند سے" as an opening.
        shers = [
            ("مَیں نے چراغِ خلق کیا اُس کی نیند سے", "اُس نے خرام لے لیا میری ترنگ سے"),
            ("ماتھے پہ اُس کے مُہر لگانے کی دیر تھی", "ظاہر ہوئی شگفتہ دلی انگ انگ سے"),
            ("دیکھا مجھے تو شرم سے خود میں سمٹ گئی", "پَل میں کشادہ ہو گئے کپڑے وہ تنگ سے"),
        ]
        self.assertEqual(run_rhyme(shers, 0), "نگ سے")
        self.assertFalse(is_matla(shers[0][0], shers[0][1], run_rhyme(shers, 0)))

    def test_alif_madda_rhymes_with_alif(self):
        # آیا against سایا/لایا/پایا. Spelled differently, heard the same; not
        # folding it welded two تجاوز ghazals into one 17-sher piece.
        shers = [
            ("جبیں سے ہوتے ہوئے نقشِ پا تک آیا ہوں", "یہ اور بات کہ مَیں دھوپ ہوں نہ سایا ہوں"),
            ("خدا کرے کہ حقیقت کا سامنا کر پائے", "اسے مَیں خواب سے باہر تو کھینچ لایا ہوں"),
            ("تجھے تلاش کروں تو کہاں تلاش کروں", "مَیں اپنے آپ کو مشکل سے ڈھونڈ پایا ہوں"),
        ]
        self.assertTrue(is_matla(shers[0][0], shers[0][1], run_rhyme(shers, 0)))

    def test_a_word_final_he_rhymes_with_alif(self):
        # ہالہ against اجالا/والا/سنبھالا — the same miss in باغِ نشاط.
        shers = [
            ("گھروں میں نور کا ہالہ کہاں سے آتا ہے", "مِری گلی کا اُجالا کہاں سے آتا ہے"),
            ("تمام شہر اگر بند ہے چراغوں پر", "یہ سوم رس کا اُجالا کہاں سے آتا ہے"),
            ("عیاں ہے حالِ دلِ زار کے بتانے سے", "کسی کو دیکھنے والا کہاں سے آتا ہے"),
        ]
        self.assertTrue(is_matla(shers[0][0], shers[0][1], run_rhyme(shers, 0)))


class TestSplitGhazalsOnRealText(unittest.TestCase):
    def test_a_husn_e_matla_stays_inside_its_ghazal(self):
        # تجاوز's قیامت ہے ghazal opens twice — a matlaa and a husn-e-matlaa,
        # both rhyming across both lines. That is one ghazal, and the فہرست
        # counts it once.
        shers = [
            ("فشارِ ذات ہے اور جاگنا قیامت ہے", "اگر یہ عشق نہیں ہے تو کیا مصیبت ہے"),
            ("یہ اور بات مجھے آدمی سے وحشت ہے", "یہ اور بات مجھے آپ سے محبّت ہے"),
            ("ترے بغیر مِری روشنی ادھوری ہے", "ترے مدار میں رہنا مِری ضرورت ہے"),
            ("ہمیں یقین نہیں اپنی بے گناہی پر", "ہمارے دامنِ دل میں فقط ندامت ہے"),
        ]
        self.assertEqual(len(split_ghazals(shers)), 1)

    def test_a_maqta_closes_the_ghazal_even_when_the_next_rhymes_alike(self):
        # باغِ نشاط: a "-امِ وصال" ghazal followed by a "-ال" ghazal. The
        # rhymes look compatible, so only the takhallus in the sher before
        # shows that the first ghazal has already closed.
        shers = [
            ("مَیں اُتر آئوں گا تجاوز پر", "اور بچھائے گا وہ بھی دامِ وصال"),
            ("آپ ہیں کس قدر خفا ساجدؔ", "کیجیے کچھ تو احترامِ وصال"),
            ("رُوپ کی دھوپ، آئنے کا جمال", "وضع کرتے ہیں اُس کے خدّ و خال"),
            ("اپنی تذلیل کا سبب ہوں مَیں", "ہو رہا ہے مجھے ذرا سا ملال"),
            ("وصل کی رات کے تعیّن کو", "مَیں ہی دیتا ہوں اگلے روز پہ ٹال"),
        ]
        groups = split_ghazals(shers)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[1][0][0], "رُوپ کی دھوپ، آئنے کا جمال")

    def test_no_sher_is_lost_on_real_text(self):
        shers = [
            ("فشارِ ذات ہے اور جاگنا قیامت ہے", "اگر یہ عشق نہیں ہے تو کیا مصیبت ہے"),
            ("یہ اور بات مجھے آدمی سے وحشت ہے", "یہ اور بات مجھے آپ سے محبّت ہے"),
            ("رُوپ کی دھوپ، آئنے کا جمال", "وضع کرتے ہیں اُس کے خدّ و خال"),
        ]
        self.assertEqual(sum(len(g) for g in split_ghazals(shers)), len(shers))


class TestSegmentBook(unittest.TestCase):
    def test_front_matter_produces_no_piece(self):
        pieces = segment(FRONT + GHAZAL)
        self.assertEqual([p.kind for p in pieces], ["ghazals"])

    def test_a_ghazal_keeps_all_its_lines(self):
        piece = segment(FRONT + GHAZAL)[0]
        self.assertEqual(len(piece.body.split("\n\n")), 2)

    def test_a_ghazal_is_titled_by_its_matla_first_misra(self):
        self.assertEqual(segment(FRONT + GHAZAL)[0].title, "جسم کی خوشبو الگ")

    def test_two_matlas_make_two_ghazals(self):
        # Lengthened from the brief's literal "دنیا الگ ہے" / "چراغوں کا الگ"
        # for the same VERSE_MIN reason as GHAZAL above, and re-ended on a
        # shared word so the pair actually is a matlaa — the brief's two
        # lines end "ہے" and "الگ" respectively, which is_matla (already
        # merged, tested) does not consider rhyming.
        second = [para("یہ نئی دنیا الگ ہے", 77), para("ہر اک راستہ الگ ہے", 1)]
        self.assertEqual(len(segment(FRONT + GHAZAL + second)), 2)

    def test_a_non_alternating_run_becomes_one_nazm(self):
        nazm = [
            para("مَیں چل رہا تھا", 47), para("سنہرے تانبے کی طشتری پر", 97),
            para("کوئی نہیں تھا یہاں", 53), para("قریب مجھ سے یا دُور", 51),
        ]
        pieces = segment(FRONT + GHAZAL + [para("یاد", 1)] + nazm)
        nazms = [p for p in pieces if p.kind == "nazms"]
        self.assertEqual(len(nazms), 1)
        self.assertEqual(nazms[0].title, "یاد")

    def test_prose_becomes_a_review(self):
        pieces = segment(FRONT + GHAZAL + [para("ا" * 300, 67)])
        self.assertEqual([p.kind for p in pieces if p.kind == "reviews"], ["reviews"])

    def test_a_colophon_becomes_the_written_note(self):
        pieces = segment(FRONT + GHAZAL + [para("۱۷، مئی ۲۰۱۰ئ۔ لاہور", 1)])
        self.assertEqual(pieces[0].written_note, "۱۷، مئی ۲۰۱۰ئ۔ لاہور")

    def test_a_heading_inside_the_body_sets_the_section(self):
        # The heading has to sit after body_start_index to be a real section
        # heading: here the first ghazal establishes the body, so the نعت
        # after it is the book speaking about its own poems.
        second = [para("یہ نئی دنیا الگ ہے", 77), para("ہر اک راستہ الگ ہے", 1)]
        pieces = segment(FRONT + GHAZAL + [para("نعت", 69)] + second)
        self.assertEqual(pieces[1].section, "نعت")

    def test_a_heading_before_the_body_start_does_not_set_the_section(self):
        # A heading in the front matter is the فہرست listing its own section
        # names, not the book reaching a section. تجاوز's only two headings
        # are of exactly this kind (paragraphs 1 and 16, body start 85), and
        # every one of its 101 pieces used to inherit غزلیں from them —
        # correct only by accident.
        pieces = segment(FRONT + [para("نعت", 69)] + GHAZAL)
        self.assertEqual(pieces[0].section, "")

    def test_pieces_before_the_first_body_heading_are_marked(self):
        # باغِ نشاط's epigraph couplet precedes its نعت heading and is not a
        # numbered فہرست entry; the count gate reads this position rather
        # than the section string (see checks.toc_count_errors).
        second = [para("یہ نئی دنیا الگ ہے", 77), para("ہر اک راستہ الگ ہے", 1)]
        pieces = segment(FRONT + GHAZAL + [para("نعت", 69)] + second)
        self.assertEqual(
            [p.precedes_first_heading for p in pieces], [True, False]
        )

    def test_nothing_is_marked_when_the_book_has_no_body_heading(self):
        # تجاوز's shape: headings exist, but only in the front matter.
        pieces = segment(FRONT + [para("نعت", 69)] + GHAZAL)
        self.assertEqual([p.precedes_first_heading for p in pieces], [False])

    def test_a_half_sher_is_flagged_not_dropped(self):
        # Ten clean shers with one interior unpairable line: greedy pairing
        # resyncs right after it, so 10 of 11 shers still pair (0.909),
        # clearing GHAZAL_SHAPE_THRESHOLD -- the whole run stays ghazal-shaped
        # and the odd line is flagged, not dropped. (A run this small with
        # the anomaly under the old positional-parity test would have passed
        # or failed by coincidence of index, not by any real pairing logic --
        # this fixture is sized so the greedy measurement is the thing under
        # test.)
        odd = _clean_shers(0, 5) + [para(HALF_LINE, 77)] + _clean_shers(5, 5)
        piece = segment(FRONT + odd)[0]
        self.assertIn("half-sher", piece.flags)
        self.assertIn(HALF_LINE, piece.body)

    def test_two_colophons_on_the_same_piece_are_both_retained(self):
        # No book in the corpus has adjacent colophons today, so this is
        # synthetic: a second COLOPHON attaching to the same piece must be
        # appended, not silently overwrite the first (the same class of loss
        # closed for a leading colophon by pending_colophon above).
        first_note = "۱۷، مئی ۲۰۱۰ئ۔ لاہور"
        second_note = "۱۸، مئی ۲۰۱۰ئ۔ کراچی"
        pieces = segment(
            FRONT + GHAZAL + [para(first_note, 1), para(second_note, 1)]
        )
        self.assertIn(first_note, pieces[0].written_note)
        self.assertIn(second_note, pieces[0].written_note)

    def test_a_leading_colophon_is_retained_not_dropped(self):
        # A COLOPHON arriving before any piece exists has nothing to attach
        # to yet. Neither pilot book hits this (each one's first colophon
        # follows a piece already formed), so this is synthetic: the note
        # must still reach the eventual piece rather than being discarded.
        note = "۱۷، مئی ۲۰۱۰ئ۔ لاہور"
        pieces = segment(FRONT + [para(note, 1)] + GHAZAL)
        self.assertEqual(pieces[0].written_note, note)

    def test_an_over_long_title_is_flagged(self):
        # No real title from any of segment()'s three call sites can exceed
        # MAX_TITLE_LENGTH today (a `reviews` title is sliced to the cap
        # itself, and a ghazal/nazm title comes from a VERSE paragraph, which
        # classify() caps well under it) -- this guard exists for the day one
        # of those assumptions breaks, e.g. the ~1400-character title one
        # pilot run actually produced. Lowering the cap below an ordinary
        # title's length is what real over-long input would look like from
        # add()'s point of view, without inventing an unreachable fixture.
        with mock.patch("tools.inpage.segment.MAX_TITLE_LENGTH", 5):
            piece = segment(FRONT + GHAZAL)[0]
        self.assertIn("over-long-title", piece.flags)

    def test_pieces_are_numbered_from_one_in_book_order(self):
        second = [para("یہ نئی دنیا الگ ہے", 77), para("ہر اک راستہ الگ ہے", 1)]
        pieces = segment(
            FRONT + GHAZAL + second + [para("ا" * 300, 67)]
        )
        self.assertEqual([p.order for p in pieces], list(range(1, len(pieces) + 1)))


class TestEssayRegion(unittest.TestCase):
    """The critic's essay that opens each book, and the verse it quotes.

    Both pilot books open with an essay about the poet, sitting before the
    first ghazal and therefore before `body_start_index`. Every verse line it
    quotes classifies as FRONT_MATTER there, and FRONT_MATTER produced no
    piece — so ~55 lines of the poet's own verse were dropped, and the essay
    itself was shredded into one `reviews` fragment per uninterrupted prose
    run (5 in تجاوز, 10 in باغِ نشاط). The region is now absorbed whole.
    """

    TITLE_LINE = "شاعرانہ مگس کاری کے متنوع سانچے"
    AUTHOR_LINE = "ڈاکٹر سعادت سعید"
    QUOTE_ONE = "شمع خیالِ سبز کی رنگ جما نہیں رہی"
    QUOTE_TWO = "سَر پر کِسی غریب کے ناچار گِر پڑے"
    NOTE = "(۵-مئی ۲۰۲۳ئ)"

    def essay(self):
        """A separator-bounded essay region: headings, prose, quoted verse."""
        return [
            para("۰۰۰", 80),
            para(self.TITLE_LINE, 70),
            para(self.AUTHOR_LINE, 70),
            para("الف" * 60, 67),
            para(self.QUOTE_ONE, 73),
            para("بے" * 60, 67),
            para(self.QUOTE_TWO, 73),
            para(self.NOTE, 1),
            para("۰۰۰", 80),
        ]

    def review(self):
        pieces = segment(FRONT + self.essay() + GHAZAL)
        reviews = [p for p in pieces if p.kind == "reviews"]
        self.assertEqual(len(reviews), 1, "the essay must be one piece")
        return reviews[0]

    def test_an_essay_interrupted_by_verse_is_one_piece_not_several(self):
        pieces = segment(FRONT + self.essay() + GHAZAL)
        self.assertEqual(
            [p.kind for p in pieces], ["reviews", "ghazals"]
        )

    def test_the_quoted_verse_survives_in_source_order(self):
        body = self.review().body
        for quote in (self.QUOTE_ONE, self.QUOTE_TWO):
            self.assertIn(quote, body)
        lines = [line for line in body.split("\n\n") if line.strip()]
        self.assertEqual(
            lines,
            [
                self.TITLE_LINE,
                self.AUTHOR_LINE,
                "الف" * 60,
                self.QUOTE_ONE,
                "بے" * 60,
                self.QUOTE_TWO,
            ],
        )

    def test_a_colophon_inside_the_region_becomes_the_written_note(self):
        self.assertEqual(self.review().written_note, self.NOTE)

    def test_the_byline_is_flagged_and_both_heading_lines_are_kept(self):
        # تجاوز orders the region title-then-author, باغِ نشاط
        # author-then-title, so there is no rule that picks the byline. Both
        # lines stay in the body and a human resolves the flag.
        piece = self.review()
        self.assertIn("confirm-review-byline", piece.flags)
        self.assertEqual(piece.title, self.TITLE_LINE)
        self.assertIn(self.TITLE_LINE, piece.body)
        self.assertIn(self.AUTHOR_LINE, piece.body)

    def test_no_ghazal_line_is_swallowed_by_the_region(self):
        # The region stops at the body start even when no separator closes it.
        essay = [p for p in self.essay() if p.text != "۰۰۰"]
        pieces = segment(FRONT + [para("۰۰۰", 80)] + essay + GHAZAL)
        ghazals = [p for p in pieces if p.kind == "ghazals"]
        self.assertEqual(len(ghazals), 1)
        self.assertIn("جسم کی خوشبو الگ", ghazals[0].body)
        self.assertNotIn("جسم کی خوشبو الگ",
                         [p for p in pieces if p.kind == "reviews"][0].body)

    def test_paragraphs_reaching_no_piece_are_reported_by_kind(self):
        unreached: list[tuple[str, Paragraph]] = []
        segment(FRONT + self.essay() + GHAZAL, None, unreached)
        kinds = {kind for kind, _ in unreached}
        # The title-page front matter and the فہرست line legitimately reach
        # no piece; nothing from inside the essay region may appear here.
        texts = {para_.text for _, para_ in unreached}
        self.assertNotIn(self.QUOTE_ONE, texts)
        self.assertNotIn(self.QUOTE_TWO, texts)
        self.assertNotIn(self.NOTE, texts)
        self.assertIn("front_matter", kinds)


class TestIsGhazalShaped(unittest.TestCase):
    """Direct coverage of the greedy-pairing measurement itself."""

    def test_one_interior_unpairable_line_still_counts_as_ghazal_shaped(self):
        # The exact case positional parity got wrong: one anomaly in the
        # middle. Greedy pairing resyncs immediately after it, so this run
        # (10 of 11 shers clean, 0.909) stays above GHAZAL_SHAPE_THRESHOLD --
        # under the old parity test, everything past this line would have
        # had its expected geometry flipped, and the whole run could tip
        # into "not ghazal" depending on how much run follows.
        run = _clean_shers(0, 5) + [para(HALF_LINE, 77)] + _clean_shers(5, 5)
        self.assertTrue(_is_ghazal_shaped(run))

    def test_a_genuinely_non_alternating_run_is_not_ghazal_shaped(self):
        # Free verse: no line carries the second-misra geometry at all, so
        # every "sher" greedy pairing produces is a half sher -- 0% clean,
        # far below the threshold. This must not become a ghazal.
        nazm = [
            para("مَیں چل رہا تھا", 47), para("سنہرے تانبے کی طشتری پر", 97),
            para("کوئی نہیں تھا یہاں", 53), para("قریب مجھ سے یا دُور", 51),
        ]
        self.assertFalse(_is_ghazal_shaped(nazm))


if __name__ == "__main__":
    unittest.main()
