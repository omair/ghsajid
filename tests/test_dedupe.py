import unittest

from tools.migrate.dedupe import merge_duplicates, piece_url
from tools.migrate.models import Piece


def piece(kind, slug, pid, **extra):
    return Piece(
        kind=kind, slug=slug, title=slug, language="urdu", script="nastaliq",
        published="2020-01-01", source_post_ids=[pid], extra=extra,
    )


class TestPieceUrl(unittest.TestCase):
    def test_url_uses_singular_kind_segment(self):
        self.assertEqual(piece_url(piece("ghazals", "abc", 1)), "/ghazal/abc")
        self.assertEqual(piece_url(piece("reviews", "abc", 1)), "/tabsira/abc")
        self.assertEqual(piece_url(piece("videos", "abc", 1)), "/video/abc")

    def test_memoir_url_is_owned_by_the_container(self):
        self.assertEqual(piece_url(piece("memoir", "dars-gah-7", 1, part=7)), "/dars-gah/7")


class TestMergeDuplicates(unittest.TestCase):
    def test_identical_slugs_merge_and_redirect_the_loser(self):
        survivors, redirects = merge_duplicates(
            [piece("ghazals", "same", 10), piece("ghazals", "same", 20)]
        )
        self.assertEqual(len(survivors), 1)
        self.assertEqual(survivors[0].source_post_ids, [10, 20])
        self.assertEqual(redirects, {20: "/ghazal/same"})

    def test_one_recording_under_two_titles_stays_two_works(self):
        # An Urdu and a Punjabi piece recited in the same sitting share a
        # video file but are distinct works.
        survivors, redirects = merge_duplicates(
            [
                piece("videos", "urdu-title", 30, video_id="AOl"),
                piece("videos", "punjabi-title", 40, video_id="AOl"),
            ]
        )
        self.assertEqual(len(survivors), 2)
        self.assertEqual(redirects, {})

    def test_distinct_pieces_are_untouched(self):
        survivors, redirects = merge_duplicates(
            [piece("ghazals", "one", 1), piece("ghazals", "two", 2)]
        )
        self.assertEqual(len(survivors), 2)
        self.assertEqual(redirects, {})


if __name__ == "__main__":
    unittest.main()
