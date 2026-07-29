import unittest

from tools.inpage.printed_index import (
    ANASIR,
    AYINDA,
    BY_NAME,
    DECLARED_POEMS,
    KITAB_E_SUBH,
    MAUSAM,
    MUAMLA,
    RODAD,
    VOLUME_1,
    YEARS,
    apply_printed_titles,
)


class TestTranscriptionIntegrity(unittest.TestCase):
    """Guards on the transcription itself.

    Nothing here re-derives the numbers — they came off photographs of the
    printed book and cannot be recomputed. These assert the properties a
    correct transcription must have, so a typo introduced later (a
    transposed digit, a duplicated row, a collection dropped) fails rather
    than silently moving a gate.
    """

    def test_six_collections_in_publication_order(self):
        self.assertEqual(
            [c.name for c in VOLUME_1],
            ["موسم", "عناصر", "کتابِ صبح", "آیندہ", "معاملہ", "روداد"],
        )
        years = [c.year for c in VOLUME_1]
        self.assertEqual(years, sorted(years))
        self.assertEqual(years, [1985, 1993, 1998, 2004, 2006, 2010])

    def test_collections_start_in_page_order_and_do_not_overlap(self):
        starts = [c.start_page for c in VOLUME_1]
        self.assertEqual(starts, sorted(starts))
        self.assertEqual(starts, [23, 205, 353, 501, 643, 735])

    def test_every_index_page_is_strictly_increasing(self):
        # A page number that repeats or goes backwards is a transcription
        # slip, and would quietly change the poem count it implies.
        for collection in VOLUME_1:
            pages = collection.devotional_pages + collection.poem_pages
            with self.subTest(collection=collection.name):
                self.assertEqual(list(pages), sorted(set(pages)))

    def test_indexed_poems_fall_inside_the_collection(self):
        bounds = {c.name: c.start_page for c in VOLUME_1}
        ordered = list(VOLUME_1)
        for i, collection in enumerate(ordered):
            pages = collection.devotional_pages + collection.poem_pages
            if not pages:
                continue
            following = (
                ordered[i + 1].start_page if i + 1 < len(ordered) else 10_000
            )
            with self.subTest(collection=collection.name):
                self.assertGreater(min(pages), bounds[collection.name])
                self.assertLess(max(pages), following)

    def test_a_collection_indexes_by_section_or_by_poem_but_not_both(self):
        for collection in VOLUME_1:
            with self.subTest(collection=collection.name):
                self.assertNotEqual(
                    bool(collection.sections),
                    bool(collection.poem_pages),
                    "each collection uses exactly one of the two index styles",
                )

    def test_section_ranges_are_ordered_within_a_collection(self):
        for collection in VOLUME_1:
            pages = [
                p
                for s in collection.sections
                for p in (s.first_page, s.last_page)
                if p is not None
            ]
            with self.subTest(collection=collection.name):
                self.assertEqual(pages, sorted(pages))


class TestDeclaredCounts(unittest.TestCase):
    """The counts the gates will read."""

    def test_mausam_counts_six_hamds_on_top_of_its_ghazals(self):
        # The trap this whole module exists to close: the printed index
        # declares 130 غزلیں, and a gate reading 130 passes while six حمد
        # are missing. موسم has 136 poems.
        self.assertEqual(sum(s.ghazals for s in MAUSAM.sections), 130)
        self.assertEqual(MAUSAM.poems, 136)
        self.assertTrue(all(s.hamd for s in MAUSAM.sections))

    def test_qadim_is_the_only_section_of_thirty(self):
        by_size = {s.name: s.ghazals for s in MAUSAM.sections}
        self.assertEqual(by_size["قدیم"], 30)
        self.assertEqual(
            sorted(n for s, n in by_size.items() if s != "قدیم"), [20] * 5
        )

    def test_anasir_has_five_sections_of_twenty_and_no_hamd(self):
        self.assertEqual(len(ANASIR.sections), 5)
        self.assertEqual(ANASIR.poems, 100)
        self.assertFalse(any(s.hamd for s in ANASIR.sections))

    def test_first_line_indexes_are_a_census(self):
        self.assertEqual(KITAB_E_SUBH.poems, 97)
        self.assertEqual(AYINDA.poems, 104)      # 100 غزلیں + حمد + 2 نعت + سلام
        self.assertEqual(len(AYINDA.poem_pages), 100)
        self.assertEqual(MUAMLA.poems, 15)
        self.assertEqual(RODAD.poems, 124)       # 120 غزلیں + 3 نعت + سلام
        self.assertEqual(len(RODAD.poem_pages), 120)

    def test_volume_total(self):
        self.assertEqual(sum(c.poems for c in VOLUME_1), 576)

    def test_lookups_cover_every_collection(self):
        for collection in VOLUME_1:
            self.assertIs(BY_NAME[collection.name], collection)
            self.assertEqual(YEARS[collection.name], collection.year)
            self.assertEqual(DECLARED_POEMS[collection.name], collection.poems)

    def test_prose_is_not_counted_as_verse(self):
        # معاملہ's دیباچہ and روداد's آرا / تعارف are criticism and
        # apparatus; counting them would inflate every gate by a few.
        self.assertEqual(MUAMLA.poems, len(MUAMLA.poem_pages))
        self.assertEqual(len(RODAD.prose), 3)


class TestPrintedTitles(unittest.TestCase):
    """The printed فہرست names the essays; segmentation cannot."""

    class _Piece:
        def __init__(self, kind, collection, title="", flags=None):
            self.kind = kind
            self.collection = collection
            self.title = title
            self.reviewed_author = ""
            self.flags = flags or []

    NONE = frozenset()

    def test_titles_and_authors_come_from_the_index(self):
        pieces = [
            self._Piece("reviews", "عناصر", "(محمدخالد)"),
            self._Piece("reviews", "عناصر", "یہ ویں صدی کی نویں دھائی ہے"),
            self._Piece("ghazals", "عناصر", "کوئی غزل"),
        ]
        problems = apply_printed_titles(pieces, "kulliyat-jild-1", self.NONE)
        # Only عناصر is supplied here, so every other collection reports its
        # prose as unstaged. What matters is that عناصر does not.
        self.assertEqual([p for p in problems if p.startswith("عناصر")], [])
        self.assertEqual(pieces[0].title, "اعتذار")
        self.assertEqual(pieces[0].reviewed_author, "غلام حسین ساجد")
        self.assertEqual(pieces[1].title, "ابتدائیہ")
        self.assertEqual(pieces[1].reviewed_author, "ڈاکٹر مرزا حامد بیگ")
        # a poem is never renamed
        self.assertEqual(pieces[2].title, "کوئی غزل")

    def test_a_disagreement_renames_nothing_and_is_reported(self):
        # One staged where the book prints two. A wrong byline on a critic's
        # essay is worse than none, so neither is touched.
        pieces = [self._Piece("reviews", "عناصر", "کچھ اور")]
        problems = apply_printed_titles(pieces, "kulliyat-jild-1", self.NONE)
        reported = [p for p in problems if p.startswith("عناصر")]
        self.assertEqual(len(reported), 1)
        self.assertIn("اعتذار", reported[0])
        self.assertIn("ابتدائیہ", reported[0])
        self.assertEqual(pieces[0].title, "کچھ اور")
        self.assertEqual(pieces[0].reviewed_author, "")

    def test_an_unpublishable_piece_is_not_the_books_prose(self):
        # The volume's index is staged as a `reviews` piece too; counting it
        # here would shift every essay's title by one.
        pieces = [
            self._Piece("reviews", "عناصر", "فہرست", flags=["first-line-index"]),
            self._Piece("reviews", "عناصر", "(محمدخالد)"),
            self._Piece("reviews", "عناصر", "یہ ویں صدی"),
        ]
        problems = apply_printed_titles(
            pieces, "kulliyat-jild-1", frozenset({"first-line-index"})
        )
        self.assertEqual([p for p in problems if p.startswith("عناصر")], [])
        self.assertEqual(pieces[0].title, "فہرست")
        self.assertEqual(pieces[1].title, "اعتذار")

    def test_another_book_is_untouched(self):
        pieces = [self._Piece("reviews", "", "تجاوز کا دیباچہ")]
        self.assertEqual(apply_printed_titles(pieces, "tajawuz", self.NONE), [])
        self.assertEqual(pieces[0].title, "تجاوز کا دیباچہ")


if __name__ == "__main__":
    unittest.main()
