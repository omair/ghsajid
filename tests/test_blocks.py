import unittest

from tools.migrate.blocks import (
    split_trailing_notes,
    strip_embeds,
    to_markdown,
)

GHAZAL = """
<!-- wp:paragraph {"align":"right"} -->
<p class="has-text-align-right">پہلا مصرع<br>دوسرا مصرع</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph {"align":"right"} -->
<p class="has-text-align-right">تیسرا مصرع<br>چوتھا مصرع</p>
<!-- /wp:paragraph -->
"""

PUNJABI = """
<!-- wp:paragraph --><p>پہلی سطر</p><!-- /wp:paragraph -->
<!-- wp:paragraph --><p>دوجی سطر</p><!-- /wp:paragraph -->
<!-- wp:paragraph --><p>تیجی سطر</p><!-- /wp:paragraph -->
"""

FB = """
<!-- wp:html -->
<div class="fb-video" data-href="https://www.facebook.com/x/videos/1/">
<blockquote class="fb-xfbml-parse-ignore"><p>کیپشن ٹیکسٹ</p>
Posted by <a href="https://www.facebook.com/x">Someone</a> on Wednesday</blockquote></div>
<!-- /wp:html -->
"""

PROSE = """
<!-- wp:paragraph -->
<p>پہلا پیراگراف&nbsp;<br>دوسری سطر</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p>دوسرا پیراگراف</p>
<!-- /wp:paragraph -->
"""


class TestVerse(unittest.TestCase):
    def test_br_becomes_newline_and_blank_line_between_ashaar(self):
        self.assertEqual(
            to_markdown(GHAZAL, is_verse=True),
            "پہلا مصرع\nدوسرا مصرع\n\nتیسرا مصرع\nچوتھا مصرع",
        )

    def test_without_br_each_paragraph_is_one_line(self):
        self.assertEqual(
            to_markdown(PUNJABI, is_verse=True), "پہلی سطر\nدوجی سطر\nتیجی سطر"
        )


class TestProse(unittest.TestCase):
    def test_paragraphs_separated_by_blank_lines(self):
        self.assertEqual(
            to_markdown(PROSE, is_verse=False),
            "پہلا پیراگراف\nدوسری سطر\n\nدوسرا پیراگراف",
        )

    def test_nbsp_is_normalized(self):
        self.assertNotIn("\xa0", to_markdown(PROSE, is_verse=False))


class TestEmbeds(unittest.TestCase):
    def test_strip_embeds_removes_facebook_caption_entirely(self):
        self.assertEqual(strip_embeds(FB).strip(), "")

    def test_body_of_embed_only_post_is_empty(self):
        self.assertEqual(to_markdown(strip_embeds(FB), is_verse=False), "")


class TestTatweel(unittest.TestCase):
    def test_tatweel_is_stripped_from_body(self):
        self.assertEqual(to_markdown("<p>ســبز</p>", is_verse=True), "سبز")



class TestTrailingNotes(unittest.TestCase):
    def test_colophon_is_separated_from_the_verse(self):
        verse, colophons, removed = split_trailing_notes(
            "ایک\nدو\n\nتین\nچار\n\n٢١ مارچ ، بستی کبیر سنپال"
        )
        self.assertEqual(verse, "ایک\nدو\n\nتین\nچار")
        self.assertEqual(colophons, ["٢١ مارچ ، بستی کبیر سنپال"])
        self.assertEqual(removed, ["٢١ مارچ ، بستی کبیر سنپال"])

    def test_separator_and_signature_are_discarded(self):
        verse, colophons, removed = split_trailing_notes(
            "ایک\nدو\n\n-----------\n\nغلام حسین ساجد"
        )
        self.assertEqual(verse, "ایک\nدو")
        self.assertEqual(colophons, [])
        self.assertEqual(removed, ["-----------", "غلام حسین ساجد"])

    def test_verse_without_trailing_notes_is_untouched(self):
        verse, colophons, removed = split_trailing_notes("ایک\nدو\n\nتین\nچار")
        self.assertEqual(verse, "ایک\nدو\n\nتین\nچار")
        self.assertEqual((colophons, removed), ([], []))

if __name__ == "__main__":
    unittest.main()
