import unittest

from tools.migrate.classify import classify
from tools.migrate.models import Post


def post(cats):
    return Post(1, "t", "", cats, "2020-01-01", "s")


class TestClassify(unittest.TestCase):
    def test_ghazal_is_urdu_nastaliq(self):
        self.assertEqual(classify(post(["غزل"])), ("ghazals", "urdu", "nastaliq", []))

    def test_memoir_maps_from_dars_gah(self):
        kind, lang, script, _ = classify(post(["درس گاہ"]))
        self.assertEqual((kind, lang, script), ("memoir", "urdu", "nastaliq"))

    def test_review_maps_from_tabsire(self):
        self.assertEqual(classify(post(["تبصرے"]))[0], "reviews")

    def test_punjabi_poem_is_a_nazm_with_punjabi_language(self):
        self.assertEqual(
            classify(post(["Punjabi"])), ("nazms", "punjabi", "shahmukhi", [])
        )

    def test_video_wins_over_genre_and_language(self):
        kind, lang, _, tags = classify(post(["Punjabi", "Videos", "کہانی"]))
        self.assertEqual(kind, "videos")
        self.assertEqual(lang, "punjabi")
        self.assertEqual(tags, ["کہانی"])

    def test_video_alone_defaults_to_urdu(self):
        self.assertEqual(classify(post(["Videos"])), ("videos", "urdu", "nastaliq", []))


if __name__ == "__main__":
    unittest.main()
