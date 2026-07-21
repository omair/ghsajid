import unittest

from tools.migrate.urdu import slugify, strip_tatweel, transliterate_word


class TestStripTatweel(unittest.TestCase):
    def test_removes_kashida(self):
        self.assertEqual(strip_tatweel("کسـی"), "کسی")
        self.assertEqual(strip_tatweel("بـاغِ ســبز"), "باغِ سبز")

    def test_leaves_clean_text_alone(self):
        self.assertEqual(strip_tatweel("غزل"), "غزل")


class TestTransliterate(unittest.TestCase):
    def test_inserts_vowels_into_consonant_clusters(self):
        # Words not in the exception table, so this exercises the rule itself.
        self.assertEqual(transliterate_word("قلم"), "qalam")
        self.assertEqual(transliterate_word("کٹر"), "katar")

    def test_keeps_existing_vowels(self):
        self.assertEqual(transliterate_word("پانی"), "pani")
        self.assertEqual(transliterate_word("رات"), "raat")

    def test_reads_short_vowel_diacritics(self):
        self.assertEqual(transliterate_word("رُکی"), "ruki")

    def test_word_initial_ya_and_wao_are_glides(self):
        self.assertEqual(transliterate_word("یاسمیں"), "yasmin")
        self.assertEqual(transliterate_word("وہاں"), "wahan")

    def test_uses_exception_table_for_function_words(self):
        self.assertEqual(transliterate_word("میں"), "mein")
        self.assertEqual(transliterate_word("ہے"), "hai")
        self.assertEqual(transliterate_word("نہیں"), "nahin")


class TestSlugify(unittest.TestCase):
    def test_joins_words_with_hyphens(self):
        self.assertEqual(
            slugify("رات اک لہر رُکی پانی میں"), "raat-ak-lehar-ruki-pani-mein"
        )

    def test_strips_tatweel_first(self):
        self.assertEqual(slugify("ســبز"), slugify("سبز"))

    def test_drops_punctuation_and_collapses_hyphens(self):
        self.assertEqual(slugify("فیری میڈوز/ آغا"), slugify("فیری میڈوز آغا"))
        self.assertFalse(slugify("، غزل ،").startswith("-"))
        self.assertFalse(slugify("، غزل ،").endswith("-"))


if __name__ == "__main__":
    unittest.main()
