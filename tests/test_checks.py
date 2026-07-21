import unittest

from tools.migrate.checks import fidelity_errors, normalized, verse_errors
from tools.migrate.models import Piece, Post


def post(body):
    return Post(1, "t", body, ["غزل"], "2020-01-01", "s")


def piece(body, kind="ghazals"):
    return Piece(
        kind=kind, slug="s", title="t", language="urdu", script="nastaliq",
        published="2020-01-01", body=body,
    )


class TestNormalized(unittest.TestCase):
    def test_ignores_whitespace_and_tatweel(self):
        self.assertEqual(normalized("ســبز  مرا\n"), normalized("سبز مرا"))


class TestFidelity(unittest.TestCase):
    def test_passes_when_text_survives(self):
        self.assertEqual(
            fidelity_errors(post("<p>پہلا<br>دوسرا</p>"), piece("پہلا\nدوسرا")), []
        )

    def test_fails_when_a_line_is_dropped(self):
        errors = fidelity_errors(post("<p>پہلا<br>دوسرا</p>"), piece("پہلا"))
        self.assertTrue(errors)
        self.assertIn("text mismatch", errors[0])

    def test_ignores_third_party_embed_captions(self):
        src = (
            '<!-- wp:html --><div class="fb-video">'
            "<blockquote><p>کیپشن</p></blockquote></div><!-- /wp:html -->"
        )
        self.assertEqual(fidelity_errors(post(src), piece("")), [])


class TestVerse(unittest.TestCase):
    def test_requires_an_even_number_of_misra_per_sher(self):
        self.assertEqual(verse_errors(piece("ایک\nدو\n\nتین\nچار")), [])

    def test_flags_an_orphan_misra(self):
        errors = verse_errors(piece("ایک\nدو\n\nتین"))
        self.assertTrue(errors)
        self.assertIn("1 misra", errors[0])

    def test_skips_prose_kinds(self):
        self.assertEqual(verse_errors(piece("کوئی بھی نثر", kind="memoir")), [])


if __name__ == "__main__":
    unittest.main()
