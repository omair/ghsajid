import unittest

from tools.migrate.blocks import (
    split_trailing_notes,
    strip_byline,
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


IMAGE = """
<!-- wp:paragraph -->
<p>پہلا پیراگراف</p>
<!-- /wp:paragraph -->

<!-- wp:image {"id":15,"sizeSlug":"large"} -->
<figure class="wp-block-image size-large"><img src="https://ghsajid.com/wp-content/uploads/2020/03/69907262_2502777496427829_9019422242039136256_o-1024x601.jpg" alt="" class="wp-image-15"/></figure>
<!-- /wp:image -->

<!-- wp:paragraph -->
<p>دوسرا پیراگراف</p>
<!-- /wp:paragraph -->
"""

GALLERY = """
<!-- wp:paragraph -->
<p>پیراگراف</p>
<!-- /wp:paragraph -->

<!-- wp:gallery {"ids":[204,205]} -->
<figure class="wp-block-gallery columns-2 is-cropped"><ul class="blocks-gallery-grid">
<li class="blocks-gallery-item"><figure><img src="https://ghsajid.com/wp-content/uploads/2020/05/a.jpg" alt="" data-id="204" class="wp-image-204"/></figure></li>
<li class="blocks-gallery-item"><figure><img src="https://ghsajid.com/wp-content/uploads/2020/05/b.jpg" alt="" data-id="205" class="wp-image-205"/></figure></li>
</ul></figure>
<!-- /wp:gallery -->
"""


class TestImages(unittest.TestCase):
    """Photographs are content: 13 memoir parts are illustrated."""

    def test_image_block_becomes_a_markdown_image(self):
        self.assertIn(
            "![](/media/images/69907262_2502777496427829_9019422242039136256_o.jpg)",
            to_markdown(IMAGE, is_verse=False),
        )

    def test_wordpress_resize_suffix_is_dropped_for_the_original(self):
        self.assertNotIn("1024x601", to_markdown(IMAGE, is_verse=False))

    def test_image_keeps_its_position_between_paragraphs(self):
        self.assertEqual(
            to_markdown(IMAGE, is_verse=False),
            "پہلا پیراگراف\n\n"
            "![](/media/images/69907262_2502777496427829_9019422242039136256_o.jpg)\n\n"
            "دوسرا پیراگراف",
        )

    def test_gallery_becomes_consecutive_images(self):
        self.assertEqual(
            to_markdown(GALLERY, is_verse=False),
            "پیراگراف\n\n"
            "![](/media/images/a.jpg)\n\n"
            "![](/media/images/b.jpg)",
        )

    def test_prose_without_images_is_unchanged(self):
        self.assertEqual(
            to_markdown(PROSE, is_verse=False),
            "پہلا پیراگراف\nدوسری سطر\n\nدوسرا پیراگراف",
        )


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


class TestByline(unittest.TestCase):
    def test_trailing_byline_is_removed(self):
        body, removed = strip_byline("نثر کا پیراگراف\n\nتحریر: غلام حسین ساجد")
        self.assertEqual(body, "نثر کا پیراگراف")
        self.assertEqual(removed, ["تحریر: غلام حسین ساجد"])

    def test_bare_name_byline_is_removed(self):
        body, removed = strip_byline("نثر\n\nغلام حسین ساجد")
        self.assertEqual(body, "نثر")
        self.assertEqual(removed, ["غلام حسین ساجد"])

    def test_a_short_closing_paragraph_is_kept(self):
        body, removed = strip_byline("نثر\n\nاور یہی بات ہے")
        self.assertEqual(body, "نثر\n\nاور یہی بات ہے")
        self.assertEqual(removed, [])


if __name__ == "__main__":
    unittest.main()
