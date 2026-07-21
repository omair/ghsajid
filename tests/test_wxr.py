import unittest
from pathlib import Path

from tools.migrate.wxr import attachment_urls, parse_posts

EXPORT = Path("data/export.xml")


class TestParsePosts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.posts = parse_posts(EXPORT)
        cls.by_title = {p.title: p for p in cls.posts}

    def test_parses_all_published_posts(self):
        self.assertEqual(len(self.posts), 98)

    def test_excludes_non_post_types(self):
        self.assertNotIn("Privacy Policy", self.by_title)
        self.assertTrue(all(p.post_id > 0 for p in self.posts))

    def test_post_carries_categories_and_date(self):
        p = self.by_title["درس گاہ - 1"]
        self.assertEqual(p.categories, ["درس گاہ"])
        self.assertEqual(p.published, "2020-03-24")
        self.assertIn("گورنمنٹ پرائمری سکول", p.body)

    def test_multi_category_post_keeps_all_categories(self):
        p = self.by_title["کہانی - بانگے وچ ڈنگر"]
        self.assertEqual(sorted(p.categories), sorted(["Punjabi", "Videos", "کہانی"]))


class TestAttachments(unittest.TestCase):
    def test_attachments_are_listed(self):
        urls = attachment_urls(EXPORT)
        self.assertEqual(len(urls), 27)
        self.assertTrue(
            all(u.startswith("https://ghsajid.com/wp-content/uploads/") for u in urls)
        )


if __name__ == "__main__":
    unittest.main()
