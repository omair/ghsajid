import unittest

from tools.migrate.embeds import extract_published_in, extract_video

CAARWAN = """
<!-- wp:core-embed/wordpress {"url":"http://caarwan.com/aaj-ki-nazm/x/","providerNameSlug":"caarwan"} -->
<figure><div class="wp-block-embed__wrapper">
http://caarwan.com/aaj-ki-nazm/x/
</div></figure>
<!-- /wp:core-embed/wordpress -->
"""

YT = """
<!-- wp:core-embed/youtube {"url":"https://www.youtube.com/watch?v=2YTT2Arlsus"} -->
<figure><div>https://www.youtube.com/watch?v=2YTT2Arlsus</div></figure>
<!-- /wp:core-embed/youtube -->
"""

FB = """
<div class="fb-video" data-href="https://www.facebook.com/zarqa.naseem.16/videos/1551503588358975/">
<blockquote class="fb-xfbml-parse-ignore"><p>❤ ھے زندگی کا مقصد ❤
12-02-2020 کو علی صدف صاحب کے گھر مشاعرے میں</p>
Posted by <a href="https://www.facebook.com/zarqa.naseem.16">Zarqa Naseem</a> on Wednesday</blockquote></div>
"""


class TestPublishedIn(unittest.TestCase):
    def test_caarwan_embed_becomes_published_in(self):
        self.assertEqual(extract_published_in(CAARWAN), ["caarwan.com"])

    def test_no_embed_yields_no_provenance(self):
        self.assertEqual(extract_published_in("<p>متن</p>"), [])


class TestVideo(unittest.TestCase):
    def test_youtube_video_id_is_extracted(self):
        v = extract_video(YT)
        self.assertEqual(v["source"], "youtube")
        self.assertEqual(v["video_id"], "2YTT2Arlsus")
        self.assertEqual(v["url"], "https://www.youtube.com/watch?v=2YTT2Arlsus")

    def test_short_youtube_urls_are_recognised(self):
        self.assertEqual(
            extract_video("<p>https://youtu.be/abcdefghijk</p>")["video_id"],
            "abcdefghijk",
        )

    def test_facebook_video_is_extracted_with_caption(self):
        v = extract_video(FB)
        self.assertEqual(v["source"], "facebook")
        self.assertEqual(v["video_id"], "1551503588358975")
        self.assertIn("مشاعرے", v["description"])

    def test_facebook_caption_date_becomes_recorded(self):
        self.assertEqual(extract_video(FB)["recorded"], "2020-02-12")

    def test_post_without_video_returns_none(self):
        self.assertIsNone(extract_video("<p>متن</p>"))


if __name__ == "__main__":
    unittest.main()
