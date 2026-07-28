import json
import shutil
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from tools.inpage.emit import (
    _piece,
    book_record_slugs,
    resolve_book_records,
    write_book,
    write_segment,
    write_segments,
)
from tools.inpage.models import Book, Segment
from tools.inpage.promote import promote
from tools.inpage.report import render
from tools.migrate.emit import frontmatter


def stage_book_records(segments, book_slug, book_staging, titles=None):
    """Write pieces + one record per collection, exactly as cmd_segment does.

    Kept in one place so the promote and report tests exercise the same
    staging shape the CLI actually produces for کلیات جلد ۲ — six records,
    one per collection — rather than each inventing its own.
    """
    _, slugs, _ = write_segments(segments, book_slug, book_staging)
    contents = [(s, slug) for s, slug in zip(segments, slugs)
                if s.kind in ("ghazals", "nazms")]
    records, problems = resolve_book_records(segments, book_slug)
    for collection, record_slug in records:
        rows = [(s, slug) for s, slug in contents if s.collection == collection]
        write_book(
            Book(
                title=collection or (titles or {}).get(book_slug, book_slug),
                slug=record_slug,
                collected_in=book_slug if collection else "",
                contents=[s for s, _ in rows],
            ),
            [slug for _, slug in rows],
            book_staging,
        )
    return records, problems


class TestWriteSegment(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_writes_frontmatter_without_a_published_date(self):
        segment = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="الف\nب", order=3)
        path = write_segment(segment, "tajawuz", self.root)
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("published:", text)
        self.assertIn('source_book: "tajawuz"', text)
        self.assertIn("book_order: 3", text)

    def test_slug_matches_the_migrate_slugifier(self):
        segment = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="الف\nب", order=1)
        path = write_segment(segment, "tajawuz", self.root)
        self.assertEqual(path.name, "raat-ak-lehar-ruki-pani-mein.md")

    def test_a_normal_titles_slug_is_unchanged_by_the_cap(self):
        # A title short enough to be unaffected by MAX_SLUG_LENGTH must
        # produce the byte-identical slug it always has.
        segment = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="الف\nب", order=1)
        path = write_segment(segment, "tajawuz", self.root)
        self.assertEqual(path.name, "raat-ak-lehar-ruki-pani-mein.md")

    def test_written_note_survives_into_the_emitted_frontmatter(self):
        # A colophon attached in segment.py must actually reach the file a
        # human reviews, not just live on the Segment in memory.
        note = "۱۷، مئی ۲۰۱۰ئ۔ لاہور"
        segment = Segment(
            kind="ghazals", title="پہلی نظم", body="اول\nدوم", order=1,
            written_note=note,
        )
        piece = _piece(segment, "tajawuz")
        text = frontmatter(piece)
        self.assertIn(f"written_note: {json.dumps(note, ensure_ascii=False)}", text)

    def test_an_over_long_title_produces_a_capped_slug(self):
        # A misdetected paragraph run with no line break produced a "title"
        # ~1400 characters long in the پہلا pilot run; its slug was long
        # enough to raise OSError on write. The slug must be capped at
        # MAX_SLUG_LENGTH (80), truncated at a `-` boundary.
        long_title = "غلام حسین ساجد " * 100
        segment = Segment(kind="ghazals", title=long_title, body="الف\nب", order=1)
        path = write_segment(segment, "tajawuz", self.root)
        slug = path.stem
        self.assertLessEqual(len(slug), 80)
        self.assertNotIn("--", slug)
        self.assertFalse(slug.endswith("-"))


class TestWriteSegments(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_writes_both_poems_on_slug_collision(self):
        # Different titles that slugify identically once diacritics/whitespace
        # are stripped — same underlying string here, forced for the test.
        first = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="اول", order=1)
        second = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="دوم", order=2)
        paths, slugs, problems = write_segments([first, second], "tajawuz", self.root)

        self.assertEqual(len(paths), 2)
        self.assertEqual(paths[0].name, "raat-ak-lehar-ruki-pani-mein.md")
        self.assertEqual(paths[1].name, "raat-ak-lehar-ruki-pani-mein-2.md")
        self.assertEqual(slugs, ["raat-ak-lehar-ruki-pani-mein", "raat-ak-lehar-ruki-pani-mein-2"])
        self.assertIn("اول", paths[0].read_text(encoding="utf-8"))
        self.assertIn("دوم", paths[1].read_text(encoding="utf-8"))
        self.assertTrue(problems)
        self.assertIn("collision", problems[0])

    def test_no_collision_no_problems(self):
        first = Segment(kind="ghazals", title="پہلی نظم", body="اول", order=1)
        second = Segment(kind="nazms", title="دوسری نظم", body="دوم", order=2)
        paths, slugs, problems = write_segments([first, second], "tajawuz", self.root)
        self.assertEqual(len(paths), 2)
        self.assertEqual(slugs[0], "pahli-nazm")
        self.assertEqual(len(slugs), 2)
        self.assertNotEqual(slugs[0], slugs[1])
        self.assertEqual(problems, [])

    def test_deterministic_on_a_fresh_root(self):
        first = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="اول", order=1)
        second = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="دوم", order=2)

        root_a = Path(tempfile.mkdtemp())
        root_b = Path(tempfile.mkdtemp())
        try:
            names_a = [p.name for p in write_segments([first, second], "tajawuz", root_a)[0]]
            names_b = [p.name for p in write_segments([first, second], "tajawuz", root_b)[0]]
            self.assertEqual(names_a, names_b)
        finally:
            shutil.rmtree(root_a)
            shutil.rmtree(root_b)


class TestWriteBook(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_omits_an_unknown_year(self):
        book = Book(title="تجاوز", slug="tajawuz", publisher="رنگ ادب")
        text = write_book(book, [], self.root).read_text(encoding="utf-8")
        self.assertNotIn("year:", text)

    def test_uses_the_slugs_write_segments_resolved_on_collision(self):
        # write_segments disambiguates a collision to <slug>-2; write_book
        # must record that same resolved slug rather than re-deriving its
        # own (independently unaware of the counter) and listing the base
        # slug twice, which would make one contents row point at the wrong
        # poem and orphan the "-2" file from the book record entirely.
        first = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="اول", order=1)
        second = Segment(kind="ghazals", title="رات اک لہر رُکی پانی میں", body="دوم", order=2)
        staging_root = Path(tempfile.mkdtemp())
        try:
            _, slugs, _ = write_segments([first, second], "tajawuz", staging_root)
            book = Book(title="تجاوز", slug="tajawuz", contents=[first, second])
            text = write_book(book, slugs, self.root).read_text(encoding="utf-8")
        finally:
            shutil.rmtree(staging_root)

        self.assertEqual(slugs, [
            "raat-ak-lehar-ruki-pani-mein",
            "raat-ak-lehar-ruki-pani-mein-2",
        ])
        lines = [line for line in text.splitlines() if "slug:" in line and "  - {" in line]
        self.assertEqual(len(lines), 2)
        self.assertIn('slug: "raat-ak-lehar-ruki-pani-mein"', lines[0])
        self.assertIn('slug: "raat-ak-lehar-ruki-pani-mein-2"', lines[1])
        self.assertNotIn(lines[0], lines[1])


class TestPromote(unittest.TestCase):
    def setUp(self):
        self.staging = Path(tempfile.mkdtemp())
        self.content = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.staging)
        shutil.rmtree(self.content)

    def test_refuses_without_an_approved_report(self):
        (self.staging / "tajawuz").mkdir(parents=True)
        (self.staging / "tajawuz" / "report.md").write_text("approved: false\n", encoding="utf-8")
        written, problems = promote("tajawuz", self.staging, self.content)
        self.assertEqual(written, [])
        self.assertTrue(problems)

    def _stage_approved(self, book_slug, segments, book=None):
        """Write segments + an approved, current report into staging.

        The report is rendered LAST and against the staging tree, exactly as
        cmd_segment does: the stamped hash now covers the staged files' bytes,
        so anything written afterwards would void the approval it stamped.
        """
        book_staging = self.staging / book_slug
        _, slugs, _ = write_segments(segments, book_slug, book_staging)
        if book is not None:
            write_book(book, [s for s, seg in zip(slugs, segments)
                              if seg.kind in ("ghazals", "nazms")], book_staging)
        segments_path = book_staging / "segments.json"
        segments_path.write_text(
            json.dumps([asdict(s) for s in segments]), encoding="utf-8"
        )
        self._approve(book_slug, segments, book_staging)
        return book_staging

    def _approve(self, book_slug, segments, book_staging):
        report_text = render(book_slug, segments, [], book_staging).replace(
            "approved: false", "approved: true"
        )
        (book_staging / "report.md").write_text(report_text, encoding="utf-8")

    def test_skips_existing_piece_with_identical_text(self):
        segment = Segment(kind="ghazals", title="پہلی نظم", body="اول\nدوم", order=1)
        self._stage_approved("tajawuz", [segment])

        existing = write_segment(segment, "tajawuz", self.content)
        before = existing.read_bytes()

        written, problems = promote("tajawuz", self.staging, self.content)

        self.assertEqual(written, [])
        self.assertTrue(any("already in the archive, skipped" in p for p in problems))
        self.assertEqual(existing.read_bytes(), before)

    def test_reports_but_does_not_overwrite_differing_text(self):
        staged_segment = Segment(kind="ghazals", title="پہلی نظم", body="اول\nدوم", order=1)
        self._stage_approved("tajawuz", [staged_segment])

        archived_segment = Segment(kind="ghazals", title="پہلی نظم", body="سوم\nچہارم", order=1)
        existing = write_segment(archived_segment, "tajawuz", self.content)
        before = existing.read_bytes()

        written, problems = promote("tajawuz", self.staging, self.content)

        self.assertEqual(written, [])
        self.assertTrue(any("text differs from the archive" in p for p in problems))
        self.assertEqual(existing.read_bytes(), before)

    def test_copies_book_record_when_absent(self):
        segment = Segment(kind="ghazals", title="پہلی نظم", body="اول\nدوم", order=1)
        book = Book(title="تجاوز", slug="tajawuz", contents=[segment])
        self._stage_approved("tajawuz", [segment], book)

        written, problems = promote("tajawuz", self.staging, self.content)

        target = self.content / "books" / "tajawuz.yaml"
        self.assertTrue(target.exists())
        self.assertIn(target, written)
        self.assertFalse(any("book record" in p for p in problems))

    def test_does_not_overwrite_an_existing_book_record(self):
        segment = Segment(kind="ghazals", title="پہلی نظم", body="اول\nدوم", order=1)
        book = Book(title="تجاوز", slug="tajawuz", contents=[segment])
        self._stage_approved("tajawuz", [segment], book)

        target = self.content / "books" / "tajawuz.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('title: "تجاوز"\nyear: 1987\npublisher: "hand entered"\n', encoding="utf-8")
        before = target.read_bytes()

        written, problems = promote("tajawuz", self.staging, self.content)

        self.assertNotIn(target, written)
        self.assertTrue(any("book record" in p and "skipped" in p for p in problems))
        self.assertEqual(target.read_bytes(), before)

    def test_slug_collision_both_poems_reach_staging_and_are_promoted(self):
        first = Segment(kind="ghazals", title="پہلی نظم", body="اول", order=1)
        second = Segment(kind="ghazals", title="پہلی نظم", body="دوم", order=2)
        book_staging = self.staging / "tajawuz"
        _, slugs, staging_problems = write_segments(
            [first, second], "tajawuz", book_staging
        )
        self.assertTrue(any("collision" in p for p in staging_problems))
        # A complete staging tree, as cmd_segment writes it: the book record
        # the segments name is part of what promote must find.
        write_book(
            Book(title="تجاوز", slug="tajawuz", contents=[first, second]),
            slugs,
            book_staging,
        )

        segments_path = book_staging / "segments.json"
        segments_path.write_text(
            json.dumps([asdict(s) for s in (first, second)]), encoding="utf-8"
        )
        self._approve("tajawuz", [first, second], book_staging)

        written, problems = promote("tajawuz", self.staging, self.content)

        names = sorted(p.name for p in written)
        self.assertEqual(
            names, ["pahli-nazm-2.md", "pahli-nazm.md", "tajawuz.yaml"]
        )
        self.assertEqual(problems, [])

    def test_orphaned_staging_file_from_a_prior_run_is_not_promoted(self):
        # Regression for the stale-orphan bug: a book is segmented (2 pieces),
        # then re-segmented after a fix down to 1 piece. The approval gate
        # binds to segments.json, but promote must ALSO refuse to copy
        # whatever .md files are still sitting in staging from the first run
        # — it may only copy what the approved segments.json names.
        first = Segment(kind="ghazals", title="پہلی نظم", body="اول", order=1)
        second = Segment(kind="ghazals", title="دوسری نظم", body="دوم", order=2)
        book_staging = self.staging / "tajawuz"
        write_segments([first, second], "tajawuz", book_staging)  # first run: 2 pieces

        # Re-segment down to just `first` — `second`'s .md is now an orphan.
        segments_path = book_staging / "segments.json"
        segments_path.write_text(
            json.dumps([asdict(first)]), encoding="utf-8"
        )
        self._approve("tajawuz", [first], book_staging)

        written, problems = promote("tajawuz", self.staging, self.content)

        names = sorted(p.name for p in written)
        self.assertEqual(names, ["pahli-nazm.md"])
        self.assertFalse((self.content / "ghazals" / "dosri-nazm.md").exists())
        self.assertFalse(any("dosri" in p for p in problems))

    def test_piece_named_in_segments_json_but_missing_from_disk_is_reported(self):
        segment = Segment(kind="ghazals", title="پہلی نظم", body="اول\nدوم", order=1)
        book_staging = self.staging / "tajawuz"
        book_staging.mkdir(parents=True)
        segments_path = book_staging / "segments.json"
        segments_path.write_text(json.dumps([asdict(segment)]), encoding="utf-8")
        self._approve("tajawuz", [segment], book_staging)
        # Deliberately never wrote pahli-nazm.md into staging.

        written, problems = promote("tajawuz", self.staging, self.content)

        self.assertEqual(written, [])
        self.assertTrue(any("missing" in p and "pahli-nazm" in p for p in problems))


class TestPromoteIsBoundToTheStagedBytes(unittest.TestCase):
    """The approval must cover the bytes promote copies, not just the boundaries.

    The hash digested segments.json while promote copied the staged .md files,
    so an edit made after sign-off promoted text no report had described. The
    book record was worse: promote found it by globbing the staging directory
    and no hash covered it at all.
    """

    def setUp(self):
        self.staging = Path(tempfile.mkdtemp())
        self.content = Path(tempfile.mkdtemp())
        self.segment = Segment(kind="ghazals", title="پہلی نظم", body="اول\nدوم", order=1)
        self.book_staging = self.staging / "tajawuz"
        _, slugs, _ = write_segments([self.segment], "tajawuz", self.book_staging)
        write_book(
            Book(title="تجاوز", slug="tajawuz", contents=[self.segment]),
            slugs,
            self.book_staging,
        )
        (self.book_staging / "segments.json").write_text(
            json.dumps([asdict(self.segment)]), encoding="utf-8"
        )
        (self.book_staging / "report.md").write_text(
            render("tajawuz", [self.segment], [], self.book_staging).replace(
                "approved: false", "approved: true"
            ),
            encoding="utf-8",
        )
        self.piece = self.book_staging / "ghazals" / "pahli-nazm.md"
        self.record = self.book_staging / "books" / "tajawuz.yaml"

    def tearDown(self):
        shutil.rmtree(self.staging)
        shutil.rmtree(self.content)

    def test_an_untouched_approved_tree_still_promotes(self):
        written, problems = promote("tajawuz", self.staging, self.content)
        self.assertEqual(problems, [])
        self.assertEqual(
            sorted(p.name for p in written), ["pahli-nazm.md", "tajawuz.yaml"]
        )

    def test_editing_a_staged_piece_after_approval_voids_it(self):
        self.piece.write_text(
            self.piece.read_text(encoding="utf-8").replace("دوم", "کچھ اور"),
            encoding="utf-8",
        )
        written, problems = promote("tajawuz", self.staging, self.content)
        self.assertEqual(written, [])
        self.assertTrue(any("not approved" in p for p in problems))
        self.assertFalse((self.content / "ghazals").exists())

    def test_editing_a_staged_piece_frontmatter_after_approval_voids_it(self):
        self.piece.write_text(
            self.piece.read_text(encoding="utf-8").replace(
                'language: "urdu"', 'language: "punjabi"'
            ),
            encoding="utf-8",
        )
        written, problems = promote("tajawuz", self.staging, self.content)
        self.assertEqual(written, [])
        self.assertTrue(any("not approved" in p for p in problems))

    def test_editing_the_staged_book_record_after_approval_voids_it(self):
        self.record.write_text(
            self.record.read_text(encoding="utf-8").replace("تجاوز", "کوئی اور"),
            encoding="utf-8",
        )
        written, problems = promote("tajawuz", self.staging, self.content)
        self.assertEqual(written, [])
        self.assertTrue(any("not approved" in p for p in problems))
        self.assertFalse((self.content / "books").exists())

    def test_adding_a_contents_row_to_the_staged_record_voids_it(self):
        self.record.write_text(
            self.record.read_text(encoding="utf-8")
            + '  - { kind: "ghazals", slug: "smuggled" }\n',
            encoding="utf-8",
        )
        written, problems = promote("tajawuz", self.staging, self.content)
        self.assertEqual(written, [])
        self.assertTrue(any("not approved" in p for p in problems))

    def test_a_stray_yaml_in_staging_is_not_promoted(self):
        # The record paths are derived from the segments, so a yaml dropped
        # into staging/books is neither hashed nor copied — promote used to
        # glob the directory and would have copied this. It is also REPORTED:
        # a record nothing described is exactly what the hash cannot see, so
        # silently ignoring it hid the fact that something put it there.
        stray = self.record.parent / "smuggled.yaml"
        stray.write_text('title: "چوری"\nslug: "smuggled"\ncontents:\n', encoding="utf-8")

        written, problems = promote("tajawuz", self.staging, self.content)

        self.assertEqual(
            sorted(p.name for p in written), ["pahli-nazm.md", "tajawuz.yaml"]
        )
        self.assertFalse((self.content / "books" / "smuggled.yaml").exists())
        self.assertTrue(
            any("smuggled.yaml" in p and "unexpected" in p for p in problems),
            problems,
        )
        # And nothing else went wrong — the stray is the only complaint.
        self.assertEqual(len(problems), 1, problems)


if __name__ == "__main__":
    unittest.main()


class TestPromoteAcceptsReviews(unittest.TestCase):
    """A book's critical foreword must reach content/reviews/.

    promote's kind guard listed only ghazals and nazms, so the first real
    promote silently skipped both books' essays — real criticism of the poet,
    with its own collection and /tabsira route.
    """

    def test_reviews_is_a_promotable_kind(self):
        from tools.inpage.promote import KNOWN_KINDS

        self.assertIn("reviews", KNOWN_KINDS)

    def test_a_stray_kind_is_still_rejected(self):
        from tools.inpage.promote import KNOWN_KINDS

        self.assertNotIn("front_matter", KNOWN_KINDS)
        self.assertNotIn("toc", KNOWN_KINDS)


class TestBookPerCollection(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_the_record_names_the_volume_it_was_collected_in(self):
        book = Book(
            title="نیند میں چلتے ہوئے",
            slug="nind-mein-chalte-hoe",
            collected_in="kulliyat-jild-2",
        )
        text = write_book(book, [], self.root).read_text(encoding="utf-8")
        self.assertIn('collected_in: "kulliyat-jild-2"', text)

    def test_collected_in_is_omitted_when_absent(self):
        book = Book(title="تجاوز", slug="tajawuz")
        text = write_book(book, [], self.root).read_text(encoding="utf-8")
        self.assertNotIn("collected_in", text)


NIND = "نیند میں چلتے ہوئے"
CHAHAR = "چہار دریا"

MULTI = [
    Segment(kind="ghazals", title="پہلی نظم", body="اول", order=1, collection=NIND),
    Segment(kind="ghazals", title="دوسری نظم", body="دوم", order=2, collection=NIND),
    Segment(kind="nazms", title="تیسری نظم", body="سوم", order=3, collection=CHAHAR),
]


class TestResolveBookRecords(unittest.TestCase):
    """The single source of truth for which records a staging tree has.

    `cmd_segment` writes one record per collection; the approval hash and
    `promote` must derive that same list, from the segments, never from a
    directory walk.
    """

    def test_a_book_with_no_collections_is_its_own_single_record(self):
        segments = [Segment(kind="ghazals", title="a", body="a", order=1)]
        records, problems = resolve_book_records(segments, "tajawuz")
        self.assertEqual(records, [("", "tajawuz")])
        self.assertEqual(problems, [])

    def test_one_record_per_distinct_collection_in_book_order(self):
        records, problems = resolve_book_records(MULTI, "kulliyat-jild-2")
        self.assertEqual([c for c, _ in records], [NIND, CHAHAR])
        self.assertEqual(problems, [])
        self.assertEqual(
            book_record_slugs(MULTI, "kulliyat-jild-2"), [s for _, s in records]
        )

    def test_reviews_do_not_create_a_record(self):
        segments = MULTI + [
            Segment(kind="reviews", title="مضمون", body="ن", order=4,
                    collection="کوئی اور")
        ]
        records, _ = resolve_book_records(segments, "kulliyat-jild-2")
        self.assertEqual([c for c, _ in records], [NIND, CHAHAR])

    def test_the_leading_uncollected_run_gets_no_record(self):
        segments = [
            Segment(kind="ghazals", title="a", body="a", order=1),
            Segment(kind="ghazals", title="b", body="b", order=2, collection=NIND),
        ]
        records, _ = resolve_book_records(segments, "kulliyat-jild-2")
        self.assertEqual([c for c, _ in records], [NIND])

    def test_two_collections_slugifying_alike_are_reported_not_overwritten(self):
        # Synthetic: inert on today's data. Segment titles are disambiguated
        # by `resolve_slugs`; collection names were not, so two that slugify
        # the same silently overwrote each other's yaml — one collection's
        # whole contents list lost, with no report of any kind.
        segments = [
            Segment(kind="ghazals", title="a", body="a", order=1, collection="راہ"),
            Segment(kind="ghazals", title="b", body="b", order=2, collection="راہ!"),
        ]
        records, problems = resolve_book_records(segments, "kulliyat-jild-2")

        slugs = [s for _, s in records]
        self.assertEqual(len(slugs), 2)
        self.assertEqual(len(set(slugs)), 2, "collision must not collapse to one file")
        self.assertTrue(any("collision" in p for p in problems), problems)
        self.assertTrue(any("راہ!" in p for p in problems), problems)

    def test_a_collection_that_slugifies_to_nothing_is_reported(self):
        segments = [
            Segment(kind="ghazals", title="a", body="a", order=1, collection="۔۔۔"),
        ]
        records, problems = resolve_book_records(segments, "kulliyat-jild-2")
        if records:
            self.assertTrue(all(slug for _, slug in records))
        else:
            self.assertTrue(problems)


class TestPromoteCopiesEveryBookRecord(unittest.TestCase):
    """کلیات جلد ۲ has six records; promote copied one path and said nothing.

    The copy was guarded by `if record.is_file():` with no `else`, and the
    path was `books/<book_slug>.yaml` — a file a multi-collection book never
    writes. 561 poems would have landed in content/ with no /kitab page.
    """

    def setUp(self):
        self.staging = Path(tempfile.mkdtemp())
        self.content = Path(tempfile.mkdtemp())
        self.book_staging = self.staging / "kulliyat-jild-2"
        self.records, _ = stage_book_records(
            MULTI, "kulliyat-jild-2", self.book_staging
        )
        (self.book_staging / "segments.json").write_text(
            json.dumps([asdict(s) for s in MULTI]), encoding="utf-8"
        )
        (self.book_staging / "report.md").write_text(
            render("kulliyat-jild-2", MULTI, [], self.book_staging).replace(
                "approved: false", "approved: true"
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self.staging)
        shutil.rmtree(self.content)

    def test_every_record_reaches_content(self):
        written, problems = promote("kulliyat-jild-2", self.staging, self.content)

        self.assertEqual(problems, [])
        expected = sorted(f"{slug}.yaml" for _, slug in self.records)
        self.assertEqual(len(expected), 2)
        self.assertEqual(
            sorted(p.name for p in written if p.suffix == ".yaml"), expected
        )
        for name in expected:
            self.assertTrue((self.content / "books" / name).exists(), name)

    def test_no_record_is_named_after_the_volume_itself(self):
        # The bug in one assertion: the old code addressed exactly this path.
        self.assertFalse(
            (self.book_staging / "books" / "kulliyat-jild-2.yaml").exists()
        )

    def test_a_record_named_by_the_segments_but_missing_is_reported(self):
        missing = self.book_staging / "books" / f"{self.records[0][1]}.yaml"
        missing.unlink()
        # Re-approve against the tree as it now stands, so the refusal under
        # test is the missing record itself and not the stale hash.
        (self.book_staging / "report.md").write_text(
            render("kulliyat-jild-2", MULTI, [], self.book_staging).replace(
                "approved: false", "approved: true"
            ),
            encoding="utf-8",
        )

        written, problems = promote("kulliyat-jild-2", self.staging, self.content)

        self.assertTrue(
            any(missing.name in p and "missing" in p for p in problems), problems
        )
        self.assertNotIn(missing.name, [p.name for p in written])

    def test_an_existing_record_is_never_overwritten(self):
        name = f"{self.records[0][1]}.yaml"
        target = self.content / "books" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('title: "hand entered"\n', encoding="utf-8")
        before = target.read_bytes()

        written, problems = promote("kulliyat-jild-2", self.staging, self.content)

        self.assertEqual(target.read_bytes(), before)
        self.assertNotIn(target, written)
        self.assertTrue(any(name in p and "skipped" in p for p in problems), problems)
