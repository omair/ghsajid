import glob
import unittest

from tools.inpage.checks import FLOATING_MARK, floating_mark_errors
from tools.inpage.marks import reattach
from tools.inpage.models import Paragraph, Segment


def _texts(*texts: str, corpus: tuple[str, ...] = ()) -> tuple[list[str], list[str]]:
    """Reattach `texts`, with `corpus` as extra paragraphs of the same book.

    The lexicon is the book's own vocabulary, so a test supplies the correctly
    marked spellings it relies on as further paragraphs, and reads back only
    the ones it asked about.
    """
    paragraphs = [Paragraph(text=t, geometry=0) for t in (*texts, *corpus)]
    fixed, unresolved = reattach(paragraphs)
    return [p.text for p in fixed[: len(texts)]], unresolved


class TestShortVowels(unittest.TestCase):
    def test_a_floating_pesh_lands_on_the_first_letter(self):
        self.assertEqual(_texts("بہت  ُچوما ہے")[0], ["بہت چُوما ہے"])

    def test_at_the_start_of_a_paragraph(self):
        self.assertEqual(_texts("ُمحرّم الحرام")[0], ["مُحرّم الحرام"])

    def test_a_known_inner_placement_beats_the_first_letter(self):
        # The book spells it کھِلتی, so that is where its kasra goes — and
        # رنگِ being a known izafat must not pull the mark backwards.
        got, _ = _texts("رنگ ِکھلتی ہے", corpus=("کھِلتی", "رنگِ"))
        self.assertEqual(got, ["رنگ کھِلتی ہے"])

    def test_a_kasra_no_placement_explains_is_the_previous_words_izafat(self):
        got, _ = _texts("قلب ِلشکر میں", corpus=("قلبِ",))
        self.assertEqual(got, ["قلبِ لشکر میں"])

    def test_the_word_final_kasra_is_not_a_candidate(self):
        # لشکرِ is the word's OWN izafat. A kasra typed before the word is
        # never that one, so a known لشکرِ must not capture it.
        got, _ = _texts("قلب ِلشکر میں", corpus=("قلبِ", "لشکرِ"))
        self.assertEqual(got, ["قلبِ لشکر میں"])


class TestShadda(unittest.TestCase):
    def test_goes_where_the_book_spells_it(self):
        got, _ = _texts("سے   ّمحبت ہے", corpus=("محبّت",))
        self.assertEqual(got, ["سے محبّت ہے"])

    def test_ambiguity_is_settled_by_frequency(self):
        got, _ = _texts("کسی ّپتھر", corpus=("پتّھر", "پتّھر", "پتھّر"))
        self.assertEqual(got, ["کسی پتّھر"])

    def test_a_placement_no_spelling_supports_is_dropped_and_reported(self):
        got, unresolved = _texts("کوئی ّزلزلہ")
        self.assertEqual(got, ["کوئی زلزلہ"])
        self.assertEqual(len(unresolved), 1)
        self.assertIn("زلزلہ", unresolved[0])


class TestIsolatedMarks(unittest.TestCase):
    def test_a_kasra_between_spaces_is_an_izafat_on_the_word_before(self):
        self.assertEqual(_texts("اپنا بعد ِ دعا راستہ")[0], ["اپنا بعدِ دعا راستہ"])

    def test_after_punctuation_it_belongs_to_the_word_after(self):
        self.assertEqual(_texts("(  ُ  کتاب)")[0], ["( کُتاب)"])

    def test_a_vowel_survives_the_shadda_it_floated_with(self):
        # The title page's `(  ُ  ّکلیاتِ`: the lone pesh joins the shadda's
        # word. The shadda has no spelling to go on and is dropped; the pesh
        # still lands on the first letter rather than going down with it.
        got, unresolved = _texts("(  ُ  ّکلیاتِ غلام)")
        self.assertEqual(got, ["( کُلیاتِ غلام)"])
        self.assertEqual(len(unresolved), 1)

    def test_a_paragraph_of_only_a_mark_is_dropped(self):
        fixed, unresolved = reattach([Paragraph(text="ُ", geometry=0)])
        self.assertEqual((fixed, len(unresolved)), ([], 1))


class TestSplitWords(unittest.TestCase):
    def test_a_fragment_that_is_no_word_rejoins_its_neighbour(self):
        got, _ = _texts("کی قو ّت ہے", corpus=("قوّت",))
        self.assertEqual(got, ["کی قوّت ہے"])


class TestLeavesEverythingElseAlone(unittest.TestCase):
    def test_a_paragraph_without_a_floating_mark_is_byte_identical(self):
        text = "مَیں نے اِک  خواب   میں دیکھا"
        self.assertEqual(_texts(text)[0], [text])

    def test_raw_and_codes_are_untouched(self):
        # Gate B round-trips `raw` against `codes`; both describe the bytes
        # on disk, which this step does not change.
        paragraph = Paragraph(text="بہت  ُچوما", geometry=65, raw="بہت  ُچوما ", codes=[1, 2])
        fixed, _ = reattach([paragraph])
        self.assertEqual((fixed[0].raw, fixed[0].codes, fixed[0].geometry),
                         ("بہت  ُچوما ", [1, 2], 65))

    def test_the_letters_never_change(self):
        # The invariant the whole step answers to: marks move, letters don't.
        import re

        strip = lambda s: re.sub(r"[ً-ْٰ\s]", "", s)
        texts = ["بہت  ُچوما ہے", "قلب ِلشکر", "سے ّمحبت", "کوئی ّزلزلہ", "بعد ِ دعا"]
        got, _ = _texts(*texts, corpus=("قلبِ", "محبّت"))
        self.assertEqual([strip(t) for t in got], [strip(t) for t in texts])


class TestGate(unittest.TestCase):
    def test_names_a_piece_with_a_mark_on_a_space(self):
        piece = Segment(kind="ghazals", title="غزل", body="بہت  ُچوما", order=1)
        self.assertEqual(floating_mark_errors([piece]),
                         ["ghazals/غزل: 1 floating mark(s) in its body"])

    def test_a_mark_on_its_letter_passes(self):
        piece = Segment(kind="ghazals", title="غزل", body="بہت چُوما", order=1)
        self.assertEqual(floating_mark_errors([piece]), [])


class TestPublishedArchive(unittest.TestCase):
    """No piece published from an InPage book carries a floating mark.

    Scoped to `source_book` pieces: those are the ones `tools/inpage` wrote.
    The WordPress-migrated pieces have their own spacing habit — an izafat
    typed after a space, `صاحب ِ دل` — which is a separate fix in a separate
    tool.
    """

    def test_no_floating_marks_in_inpage_pieces(self):
        offenders = []
        for path in sorted(glob.glob("content/**/*.md", recursive=True)):
            text = open(path, encoding="utf-8").read()
            if "\nsource_book:" not in text:
                continue
            body = text.split("---", 2)[2]
            if FLOATING_MARK.search(body):
                offenders.append(path)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
