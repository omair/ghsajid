import unittest
from unittest import mock

from tools.inpage.models import Paragraph, Segment
from tools.inpage.segment import (
    KULLIYAT_JILD_1_COLLECTIONS, MAX_TITLE_LENGTH, _is_ghazal_shaped,
    _position_collection,
    attribute_gathered_collections, collection_boundary_dedication, is_matla,
    merge_orphan_shers, pair_shers, run_rhyme, segment, split_ghazals,
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


class TestMergeOrphanShers(unittest.TestCase):
    def test_two_adjacent_half_shers_become_one_sher(self):
        shers = [("ا", "ب"), ("ج", ""), ("د", "")]
        self.assertEqual(merge_orphan_shers(shers), [("ا", "ب"), ("ج", "د")])

    def test_a_lone_half_sher_stays_a_half_sher(self):
        shers = [("ا", "ب"), ("ج", ""), ("د", "ہ")]
        self.assertEqual(merge_orphan_shers(shers), [("ا", "ب"), ("ج", ""), ("د", "ہ")])

    def test_a_trailing_lone_half_sher_stays_a_half_sher(self):
        shers = [("ا", "ب"), ("ج", "")]
        self.assertEqual(merge_orphan_shers(shers), [("ا", "ب"), ("ج", "")])

    def test_three_in_a_row_pair_the_first_two_and_leave_the_third(self):
        # Greedy, left to right — the same rule `pair_shers` itself follows.
        # The odd line out is kept and stays flagged rather than being welded
        # onto a couplet it does not belong to.
        shers = [("ا", ""), ("ب", ""), ("ج", "")]
        self.assertEqual(merge_orphan_shers(shers), [("ا", "ب"), ("ج", "")])

    def test_no_line_is_ever_lost(self):
        for shers in (
            [("ا", "ب"), ("ج", ""), ("د", "")],
            [("ا", "ب"), ("ج", ""), ("د", "ہ")],
            [("ا", ""), ("ب", ""), ("ج", "")],
            [("ا", ""), ("ب", ""), ("ج", ""), ("د", "")],
        ):
            before = [line for sher in shers for line in sher if line]
            after = [line for sher in merge_orphan_shers(shers) for line in sher if line]
            self.assertEqual(before, after)

    def test_a_ghazal_of_clean_shers_is_untouched(self):
        shers = [("ا", "ب"), ("ج", "د")]
        self.assertEqual(merge_orphan_shers(shers), shers)

    def test_the_merged_sher_is_flagged_no_longer_but_the_lone_one_is(self):
        # The half-sher flag is raised on any sher with an empty second misra,
        # so merging clears it for the pair and leaves it for the orphan.
        merged = merge_orphan_shers([("ا", ""), ("ب", ""), ("ج", "")])
        self.assertEqual([bool(second) for _, second in merged], [True, False])


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

    NAZM = [
        para("مَیں چل رہا تھا", 47), para("سنہرے تانبے کی طشتری پر", 97),
        para("کوئی نہیں تھا یہاں", 53), para("قریب مجھ سے یا دُور", 51),
    ]

    def test_a_non_alternating_run_becomes_one_nazm(self):
        # The title sits after the previous poem's colophon, which is where
        # کلیات جلد ۲ actually prints one: paragraph 783 is
        # ‘‘۱۹، مئی ۲۰۱۰ئ۔ لاہور’’, 784 is the title نیلو فر, and 785 opens
        # the نظم. A colophon is not VERSE, so the title touches verse on one
        # side only — the position classify.py deliberately leaves UNKNOWN
        # (see _bridge_lines_enclosed_by_verse) precisely so it can still be read as
        # a title here.
        pieces = segment(
            FRONT + GHAZAL
            + [para("۱۷، مئی ۲۰۱۰ئ۔ لاہور", 1), para("یاد", 1)] + self.NAZM
        )
        nazms = [p for p in pieces if p.kind == "nazms"]
        self.assertEqual(len(nazms), 1)
        self.assertEqual(nazms[0].title, "یاد")

    def test_a_short_line_enclosed_by_verse_joins_the_poem(self):
        # The cost of that rule, stated rather than left to be discovered: a
        # title printed with verse on BOTH sides is indistinguishable from a
        # line of free verse — کلیات جلد ۲ prints سٹَیٹَس کُو (11 chars, ¶802)
        # and دِیمک (5, ¶846) exactly like it prints سُکڑ کر (7, ¶883), which
        # is a line of the نظم around it. classify() reads the enclosed
        # position as verse, so the run is not broken here and the two poems
        # become one piece carrying the title as a line. Nothing is lost —
        # conservation holds and the text still reaches a reviewer — but the
        # boundary is not found, and this locks which way the trade was made.
        pieces = segment(FRONT + GHAZAL + [para("یاد", 1)] + self.NAZM)
        self.assertEqual(len(pieces), 1)
        self.assertIn("یاد", pieces[0].body.split("\n"))

    def test_prose_becomes_a_review(self):
        pieces = segment(FRONT + GHAZAL + [para("ا" * 300, 67)])
        self.assertEqual([p.kind for p in pieces if p.kind == "reviews"], ["reviews"])

    def test_a_colophon_becomes_the_written_note(self):
        pieces = segment(FRONT + GHAZAL + [para("۱۷، مئی ۲۰۱۰ئ۔ لاہور", 1)])
        self.assertEqual(pieces[0].written_note, "۱۷، مئی ۲۰۱۰ئ۔ لاہور")

    def test_a_digit_stripped_colophon_closes_the_nazm_and_dates_it(self):
        # The consequence the four-digit rule was costing: a colophon whose
        # digits InPage stripped classified as VERSE, so it neither ended the
        # نظم it follows nor became its written_note — the next poem ran
        # straight on into it. جلد ۲'s largest نظم piece was 365 lines of
        # welded-together poems for exactly this reason.
        second = [
            para("دُھند میں لپٹا ہوا", 47), para("وہ ایک شہر تھا کہیں", 97),
        ]
        # The leading colophon is the one whose digits survived; it is there
        # only so یاد touches verse on one side and can be read as a title,
        # exactly as in test_a_non_alternating_run_becomes_one_nazm above.
        pieces = segment(
            FRONT + GHAZAL
            + [para("۱۷، مئی ۲۰۱۰ئ۔ لاہور", 1), para("یاد", 1)] + self.NAZM
            + [para("دسمبر ئ۔ لاہور", 1), para("خواب", 1)] + second
        )
        nazms = [p for p in pieces if p.kind == "nazms"]
        self.assertEqual([p.title for p in nazms], ["یاد", "خواب"])
        self.assertEqual(nazms[0].written_note, "دسمبر ئ۔ لاہور")
        self.assertNotIn("دسمبر ئ۔ لاہور", nazms[0].body.split("\n"))

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

    def essay(self, author_line=None):
        """A separator-bounded essay region: headings, prose, quoted verse."""
        return [
            para("۰۰۰", 80),
            para(self.TITLE_LINE, 70),
            para(author_line or self.AUTHOR_LINE, 70),
            para("الف" * 60, 67),
            para(self.QUOTE_ONE, 73),
            para("بے" * 60, 67),
            para(self.QUOTE_TWO, 73),
            para(self.NOTE, 1),
            para("۰۰۰", 80),
        ]

    def review(self, author_line=None):
        pieces = segment(FRONT + self.essay(author_line) + GHAZAL)
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

    def test_the_byline_is_resolved_and_both_heading_lines_are_kept(self):
        # تجاوز orders the region title-then-author and باغِ نشاط
        # author-then-title, so position cannot pick the byline — but the
        # honorific can. Both lines still stay in the body either way.
        piece = self.review()
        self.assertEqual(piece.title, self.TITLE_LINE)
        self.assertEqual(piece.reviewed_author, self.AUTHOR_LINE)
        self.assertNotIn("confirm-review-byline", piece.flags)
        self.assertIn(self.TITLE_LINE, piece.body)
        self.assertIn(self.AUTHOR_LINE, piece.body)

    def test_an_unresolvable_byline_is_still_flagged(self):
        # No honorific: the pipeline must not guess which line is the critic.
        piece = self.review(author_line="سعادت سعید")
        self.assertIn("confirm-review-byline", piece.flags)
        self.assertEqual(piece.reviewed_author, "")

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


from tools.inpage.segment import _split_byline


class TestSplitByline(unittest.TestCase):
    """تجاوز prints title then author; باغِ نشاط prints author then title.

    Taking the first line blind titled باغِ نشاط's essay 'ڈاکٹر شاہد اشرف' —
    its critic's name. An academic honorific tells them apart; anything it
    cannot resolve is flagged rather than guessed.
    """

    def test_author_second_as_in_tajawuz(self):
        title, author, resolved = _split_byline(
            ["شاعرانہ مگس کاری کے متنوع سانچے", "ڈاکٹر سعادت سعید"]
        )
        self.assertEqual(title, "شاعرانہ مگس کاری کے متنوع سانچے")
        self.assertEqual(author, "ڈاکٹر سعادت سعید")
        self.assertTrue(resolved)

    def test_author_first_as_in_bagh_e_nishat(self):
        title, author, resolved = _split_byline(
            ["ڈاکٹر شاہد اشرف", "روح کی ڈھولک پہ شاداں، غلام حسین ساجد"]
        )
        self.assertEqual(title, "روح کی ڈھولک پہ شاداں، غلام حسین ساجد")
        self.assertEqual(author, "ڈاکٹر شاہد اشرف")
        self.assertTrue(resolved)

    def test_unresolved_when_no_honorific(self):
        title, author, resolved = _split_byline(["پہلا عنوان", "دوسرا عنوان"])
        self.assertEqual(title, "پہلا عنوان")
        self.assertEqual(author, "")
        self.assertFalse(resolved)

    def test_unresolved_when_two_honorifics(self):
        _, author, resolved = _split_byline(["ڈاکٹر الف", "پروفیسر ب"])
        self.assertEqual(author, "")
        self.assertFalse(resolved)

    def test_unresolved_when_the_honorific_is_the_only_line(self):
        title, author, resolved = _split_byline(["ڈاکٹر سعادت سعید"])
        self.assertEqual(title, "ڈاکٹر سعادت سعید")
        self.assertEqual(author, "")
        self.assertFalse(resolved)


class TestRunningHeadersInAssembly(unittest.TestCase):
    HEADER = "نیند میں چلتے ہوئے"

    def _with_header_mid_ghazal(self):
        """One ghazal of four shers, interrupted by a page header."""
        from tools.inpage.classify import RUNNING_HEADER_MIN
        shers = _clean_shers(1, 4)
        # A header often enough to be running, placed inside the run.
        elsewhere = [para(self.HEADER, 60)] * RUNNING_HEADER_MIN
        return FRONT + GHAZAL + shers[:4] + [para(self.HEADER, 60)] + shers[4:] + elsewhere

    def test_a_page_header_ends_the_run_it_interrupts(self):
        # This used to assert the opposite, on the reasoning that 972 running
        # headers in کلیات vol 2 would cut a ghazal at every page turn. That
        # count is of the whole book and is almost entirely the back-of-book
        # فہرست, where every index line prints its collection's name.
        # Measured where it matters — a header sitting BETWEEN two verse
        # paragraphs — there are six such sites in the whole corpus (four in
        # جلد ۱, two in جلد ۲) and every one is a collection's title page,
        # exactly where a piece must end. Reading through them welded موسم's
        # last ghazal onto عناصر's title page and جادو onto نیند میں چلتے
        # ہوئے's title poem.
        pieces = [p for p in segment(self._with_header_mid_ghazal())
                  if p.kind == "ghazals"]
        before = [p for p in pieces if "نمبر 2" in p.body]
        after = [p for p in pieces if "نمبر 3" in p.body]
        self.assertTrue(before, "sher 2 reached no ghazal piece")
        self.assertTrue(after, "sher 3 reached no ghazal piece")
        self.assertIsNot(
            before[0], after[0], "the header did not end the run"
        )

    def test_no_piece_holds_text_from_both_sides_of_a_header(self):
        # The structural form of the "last header wins" guard: کلیات جلد ۲'s
        # bug was a piece whose own lines straddled a header inheriting the
        # LAST header seen rather than the one in force where its lines sit.
        # A piece can no longer straddle a header at all — a verse run ends
        # at one and an essay region is closed by one — so no piece can be
        # stamped with a name its own earlier lines never saw.
        pieces = segment(self._with_header_mid_ghazal())
        for piece in pieces:
            with self.subTest(order=piece.order):
                self.assertFalse(
                    "نمبر 2" in piece.body and "نمبر 3" in piece.body
                )

    def test_the_piece_after_the_header_takes_its_name(self):
        pieces = [p for p in segment(self._with_header_mid_ghazal())
                  if p.kind == "ghazals"]
        after = [p for p in pieces if "نمبر 3" in p.body]
        self.assertEqual(after[0].collection, self.HEADER)

    def test_a_real_section_heading_still_breaks_the_run(self):
        pieces = segment(FRONT + GHAZAL + [para("نعت", 60)] + _clean_shers(1, 2))
        sections = [p.section for p in pieces if p.kind == "ghazals"]
        self.assertIn("نعت", sections)

    def test_collection_is_empty_before_any_page_header(self):
        pieces = segment(FRONT + GHAZAL)
        self.assertEqual(pieces[0].collection, "")

    # Four distinct first/second-misra phrasings, real-ghazal-shaped: each
    # sher's own two misras share only the trailing rhyme word appended by
    # `_rhymed_shers`, and the four shers of one poem share nothing else
    # with each other either -- exactly like real poetry, where only the
    # qafia+radif recurs across shers. A shared filler phrase here (as
    # opposed to only the final word) would make `run_rhyme`'s multi-sher
    # look-ahead measure that whole filler as the "rhyme", which then fails
    # to match against a differently-worded first misra and never opens.
    _FIRST_PHRASES = ["جسم کی خوشبو", "اک روشنی دیکھی", "کوئی صدا آئی", "دل میں اک لہر"]
    _SECOND_PHRASES = ["میرے دل کا جادو", "پھر دور تلک آئی", "جو ساتھ رہی گئی", "چپکے سے اتر"]

    def _rhymed_shers(self, rhyme_word: str, count: int) -> list[Paragraph]:
        """`count` shers of a real ghazal, all rhyming on `rhyme_word`.

        `run_rhyme`'s look-ahead window is 4, so each poem needs at least 4
        shers of its own to establish its rhyme without the window leaking
        into the next poem's different rhyme and diluting the split.
        """
        lines: list[Paragraph] = []
        for i in range(count):
            lines.append(para(f"{self._FIRST_PHRASES[i]} {rhyme_word}", 73))
            lines.append(para(f"{self._SECOND_PHRASES[i]} {rhyme_word}", 1))
        return lines

    def test_a_verse_run_spanning_two_headers_splits_collection_at_the_second(self):
        # کلیات جلد ۲'s exact shape: one collection's poems run straight into
        # the next's with nothing between them but a page header, so the
        # whole span is one VERSE run. The poems before HEADER2 must take
        # HEADER1 and the poems after it must take HEADER2 -- not whichever
        # header was last seen when the run finally gets split into pieces.
        from tools.inpage.classify import RUNNING_HEADER_MIN
        HEADER1 = self.HEADER          # "نیند میں چلتے ہوئے"
        HEADER2 = "چہار دریا"
        # Three rhymes sharing no suffix with one another (شمس/قمر/نجم end
        # in س/ر/م respectively), so a real split_ghazals boundary forms at
        # each transition rather than a husn-e-matla merge.
        seed_poem = self._rhymed_shers("شمس", 4)
        poem_a = self._rhymed_shers("قمر", 4)
        poem_b = self._rhymed_shers("نجم", 4)
        trailer = (
            [para(HEADER1, 60)] * RUNNING_HEADER_MIN
            + [para(HEADER2, 60)] * RUNNING_HEADER_MIN
        )
        paragraphs = (
            FRONT + seed_poem
            + [para(HEADER1, 60)] + poem_a
            + [para(HEADER2, 60)] + poem_b
            + trailer
        )
        pieces = [p for p in segment(paragraphs) if p.kind == "ghazals"]
        self.assertEqual(len(pieces), 3, "the three rhymes must split into three poems")
        before = next(p for p in pieces if "قمر" in p.body)
        after = next(p for p in pieces if "نجم" in p.body)
        self.assertEqual(before.collection, HEADER1)
        self.assertEqual(after.collection, HEADER2)


class TestPositionAttributedCollection(unittest.TestCase):
    """کلیات جلد ۲'s Defect 1: 82 opening poems precede the volume's first
    running header by 900 paragraphs and so carried collection == "".

    A piece whose own last line still sits before the very first running
    header in the whole book has no earlier collection to belong to, so it
    takes that header's name. A piece that STRADDLES the header (its own
    run continues past it, as when split_ghazals fails to separate two
    collections' poems — see TestRunningHeadersInAssembly) must not be
    relabeled this way: that is exactly the "last header wins" bug this
    fix must not reintroduce.
    """

    HEADER = "نیند میں چلتے ہوئے"

    def _book_with_a_leading_ghazal_before_the_only_header(self):
        from tools.inpage.classify import RUNNING_HEADER_MIN
        second = [para("یہ نئی دنیا الگ ہے", 77), para("ہر اک راستہ الگ ہے", 1)]
        # RUNNING_HEADER_MIN+1 occurrences: running_headers() only counts a
        # text as page furniture past a strict majority, not at the count.
        headers = [para(self.HEADER, 60)] * (RUNNING_HEADER_MIN + 1)
        return FRONT + GHAZAL + headers + second

    def test_a_piece_entirely_before_the_first_header_takes_its_name(self):
        pieces = segment(self._book_with_a_leading_ghazal_before_the_only_header())
        self.assertEqual(pieces[0].collection, self.HEADER)

    def test_a_book_with_no_running_headers_leaves_collections_empty(self):
        # تجاوز and باغِ نشاط's shape: no line repeats often enough to be a
        # header, so nothing is attributed and every collection stays "".
        pieces = segment(FRONT + GHAZAL)
        self.assertEqual([p.collection for p in pieces], [""])

    def test_the_attribution_is_reported_through_the_out_param(self):
        attributed: list = []
        pieces = segment(
            self._book_with_a_leading_ghazal_before_the_only_header(),
            None, None, attributed,
        )
        self.assertEqual(attributed, [pieces[0]])

    def test_a_piece_straddling_the_first_header_is_not_relabeled(self):
        # The rule itself, exercised directly on `_position_collection`. It
        # used to be reachable through segment(): a ghazal-shaped run ran
        # across the book's first header and the whole run became one piece
        # whose own first line sat before it. A header now ends the run it
        # interrupts (see TestRunningHeadersInAssembly), so no piece in any
        # book can straddle one any more — the invariant is enforced by
        # structure, and this is what still guards the rule that enforced it.
        natural, attributed = _position_collection(
            "", last_index=12, first_header_index=8,
            first_header_name=self.HEADER,
        )
        self.assertEqual(natural, "")
        self.assertFalse(attributed)

    def test_a_piece_wholly_before_the_first_header_is_backfilled(self):
        natural, attributed = _position_collection(
            "", last_index=4, first_header_index=8,
            first_header_name=self.HEADER,
        )
        self.assertEqual(natural, self.HEADER)
        self.assertTrue(attributed)

    def test_a_piece_with_its_own_name_is_left_alone(self):
        natural, attributed = _position_collection(
            "چہار دریا", last_index=4, first_header_index=8,
            first_header_name=self.HEADER,
        )
        self.assertEqual(natural, "چہار دریا")
        self.assertFalse(attributed)


class TestRunningHeaderClosesEssayRegion(unittest.TestCase):
    """کلیات vol 2's bug: a running header never closed an essay region.

    چہار دریا prints the collection name atop every one of its 89 pages —
    RUNNING_HEADER, not HEADING — and the essay region opened earlier in the
    book kept absorbing everything after it, since nothing closed the region
    until end of book. The whole collection disappeared into one `reviews`
    piece. A new page of a poetry collection is definitively not still the
    foreword.
    """

    HEADER = "چہار دریا"
    SECOND_GHAZAL = [
        para("یہ نئی دنیا الگ ہے", 77), para("ہر اک راستہ الگ ہے", 1),
    ]

    def test_a_running_header_closes_an_essay_region(self):
        from tools.inpage.classify import RUNNING_HEADER_MIN
        # GHAZAL establishes the body immediately; everything below is
        # already in_body, exactly as چہار دریا's pages are (they follow
        # earlier collections, not the book's own front matter).
        region = (
            [para("۰۰۰", 80), para("ا" * 150, 67), para(self.HEADER, 60)]
            + self.SECOND_GHAZAL
        )
        # Enough further occurrences for running_headers() to count this
        # text as a running header rather than a one-off section heading.
        extra_headers = [para(self.HEADER, 60)] * RUNNING_HEADER_MIN
        pieces = segment(FRONT + GHAZAL + region + extra_headers)
        ghazals = [p for p in pieces if p.kind == "ghazals"]
        reviews = [p for p in pieces if p.kind == "reviews"]
        review_text = "".join(p.body for p in reviews)
        self.assertEqual(
            len(ghazals), 2,
            "the verse after the running header must become its own poem",
        )
        self.assertNotIn("یہ نئی دنیا الگ ہے", review_text)

    def test_a_running_header_does_not_open_an_essay_region(self):
        from tools.inpage.classify import RUNNING_HEADER_MIN
        # Verse, a running header, more verse -- no prose anywhere, so this
        # must never produce a `reviews` piece. Confirms RUNNING_HEADER stays
        # out of REGION_OPEN_KINDS even though it now closes a region.
        extra_headers = [para(self.HEADER, 60)] * RUNNING_HEADER_MIN
        pieces = segment(
            FRONT + GHAZAL + [para(self.HEADER, 60)] + self.SECOND_GHAZAL
            + extra_headers
        )
        self.assertEqual(
            [p.kind for p in pieces if p.kind == "reviews"], []
        )


# --- کلیات جلد ۱'s gathered collections ------------------------------------

IMPRINT_LINE = "(جون ئ،اورینٹ پبلشرز،لاہور)"
DEDICATION_LINE = "شمس الرحمن فاروقی کے نام"

# A table of the shape tools.inpage.segment.KULLIYAT_JILD_1_COLLECTIONS has,
# built here so these tests exercise the mechanism rather than the real
# volume's contents (which tests/test_inpage_pilot.py gates against the file).
FAKE_TABLE = {DEDICATION_LINE: ("معاملہ", "test fixture")}


def _boundary_block(order: int, title: str, body: str) -> Segment:
    return Segment(kind="nazms", title=title, body=body, order=order)


class TestCollectionBoundaryDetection(unittest.TestCase):
    """A collection's title page is recognised by what it PRINTS.

    Not by its kind: in کلیات جلد ۱ the six blocks segment as `reviews`,
    `nazms` and `ghazals` — whatever their shape suggests — so the kind
    carries no information at all.
    """

    def test_an_imprint_and_a_dedication_together_are_a_boundary(self):
        block = _boundary_block(
            1, "معاملہ", f"{IMPRINT_LINE}\n{DEDICATION_LINE}"
        )
        self.assertEqual(
            collection_boundary_dedication(block), DEDICATION_LINE
        )

    def test_the_imprint_may_be_the_pieces_title(self):
        # کلیات جلد ۱ order 332: the piece boundary fell such that the imprint
        # became the title and only the dedication stayed in the body.
        block = _boundary_block(
            1, "ئ،قوسین،لاہور)", "اپنی بیٹی سنبل نسیم کے لیے!"
        )
        self.assertEqual(
            collection_boundary_dedication(block), "اپنی بیٹی سنبل نسیم کے لیے!"
        )

    def test_a_dedication_alone_is_not_a_boundary(self):
        # A ghazal whose radif is کے لیے ends every second misra on it.
        # کلیات جلد ۱ has 20 such ghazals; taking a dedication alone as
        # evidence would cut the volume into 26 "collections".
        ghazal = Segment(
            kind="ghazals",
            title="تارِ گریہ میں گلِ اشک پرونے کے لیے",
            body=(
                "تارِ گریہ میں گلِ اشک پرونے کے لیے\n"
                "کیوں پریشاں ہو کسی اور کی ہونے کے لیے"
            ),
            order=1,
        )
        self.assertEqual(collection_boundary_dedication(ghazal), "")

    def test_an_imprint_alone_is_not_a_boundary(self):
        block = _boundary_block(1, "کوئی کتاب", IMPRINT_LINE)
        self.assertEqual(collection_boundary_dedication(block), "")


class TestAttributeGatheredCollections(unittest.TestCase):
    """Every poem takes the collection whose title page last preceded it."""

    def _volume(self):
        return [
            Segment(kind="ghazals", title="پہلے", body="پہلے", order=1),
            _boundary_block(2, "معاملہ", f"{IMPRINT_LINE}\n{DEDICATION_LINE}"),
            Segment(kind="ghazals", title="بعد", body="بعد", order=3),
            Segment(kind="reviews", title="تنقید", body="تنقید", order=4),
        ]

    def test_pieces_after_the_block_take_its_name(self):
        segments = self._volume()
        attribute_gathered_collections(segments, FAKE_TABLE)
        self.assertEqual(
            [s.collection for s in segments], ["", "", "معاملہ", "معاملہ"]
        )

    def test_the_block_itself_belongs_to_no_collection(self):
        # It is an imprint and a dedication, not a poem of the book it opens.
        # Left unattributed it stays out of every book record's contents,
        # which is exactly where a title page does not belong.
        segments = self._volume()
        attribute_gathered_collections(segments, FAKE_TABLE)
        self.assertEqual(segments[1].collection, "")

    def test_the_boundaries_are_reported_in_order(self):
        segments = self._volume()
        boundaries, problems = attribute_gathered_collections(
            segments, FAKE_TABLE
        )
        self.assertEqual(boundaries, [(2, "معاملہ")])
        self.assertEqual(problems, [])

    def test_an_unattested_dedication_leaves_the_collection_unnamed(self):
        # An unnamed collection is truthful; a guessed name is not.
        segments = self._volume()
        boundaries, problems = attribute_gathered_collections(segments, {})
        self.assertEqual(boundaries, [])
        self.assertEqual(problems, [])

        segments = self._volume()
        boundaries, problems = attribute_gathered_collections(
            segments, {"کسی اور کے نام": ("کوئی اور", "fixture")}
        )
        self.assertEqual(boundaries, [(2, "")])
        self.assertEqual([s.collection for s in segments], ["", "", "", ""])
        self.assertEqual(len(problems), 1)
        self.assertIn("UNATTRIBUTED", problems[0])

    def test_an_empty_table_changes_nothing(self):
        # تجاوز, باغِ نشاط and کلیات جلد ۲ are not keyed into the table, so
        # this path must be a no-op for them.
        segments = self._volume()
        segments[0].collection = "نیند میں چلتے ہوئے"
        boundaries, problems = attribute_gathered_collections(segments, {})
        self.assertEqual((boundaries, problems), ([], []))
        self.assertEqual(segments[0].collection, "نیند میں چلتے ہوئے")

    def test_the_real_table_names_six_collections(self):
        self.assertEqual(
            [name for name, _ in KULLIYAT_JILD_1_COLLECTIONS.values()],
            ["موسم", "عناصر", "کتابِ صبح", "آیندہ", "معاملہ", "روداد"],
        )
        for name, evidence in KULLIYAT_JILD_1_COLLECTIONS.values():
            with self.subTest(name=name):
                self.assertTrue(evidence.strip(), "every name carries evidence")
