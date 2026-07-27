import unittest

from tools.inpage.models import Paragraph
from tools.inpage.segment import is_matla, pair_shers, split_ghazals


def para(text, geometry):
    return Paragraph(text=text, geometry=geometry, raw=text, codes=[])


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


if __name__ == "__main__":
    unittest.main()
