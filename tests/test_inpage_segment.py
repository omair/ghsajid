import unittest

from tools.inpage.models import Paragraph
from tools.inpage.segment import (
    _is_ghazal_shaped, is_matla, pair_shers, segment, split_ghazals,
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

    def test_a_heading_sets_the_section(self):
        pieces = segment(FRONT + [para("نعت", 69)] + GHAZAL)
        self.assertEqual(pieces[0].section, "نعت")

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
