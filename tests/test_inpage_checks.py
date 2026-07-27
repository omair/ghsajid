import unittest

from tools.inpage import checks
from tools.inpage.checks import conservation_errors, toc_count_errors
from tools.inpage.groundtruth import EXPECTED_LINES_TOTAL, MIN_LINES_MATCHED, MIN_WHOLE_GHAZALS
from tools.inpage.models import Paragraph, Segment


def vpara(text, geometry):
    return Paragraph(text=text, geometry=geometry, raw=text, codes=[])


TOC_AND_GHAZAL = [
    vpara("۱۔۲۔", 80),
    # The second misra is lengthened from the brief's literal "کا جادو الگ"
    # (11 chars) to clear classify.VERSE_MIN (15) — below that floor, classify()
    # marks the line UNKNOWN rather than VERSE, body_start_index never finds
    # its run of 4, and every gate here would silently see zero verse
    # paragraphs. Same fix as tests/test_inpage_segment.py's GHAZAL fixture.
    vpara("جسم کی خوشبو الگ", 73), vpara("میرے دل کا جادو الگ", 1),
    vpara("چاٹ لیتی ہے یہ فکر", 89), vpara("ہو نہ جائے تو الگ", 1),
]


class TestCompleteness(unittest.TestCase):
    def test_reports_unmapped_codes(self):
        # 0xE0 is a real character code the table cannot yet name. A byte below
        # 0x20 would not do here: decode() classifies those as stream control
        # bytes and drops them, so they never reach this gate.
        data = bytes([0x04, 0x81, 0x04, 0xE0])
        errors = checks.completeness_errors(data)
        self.assertEqual(len(errors), 1)
        self.assertIn("0xe0", errors[0])

    def test_silent_when_every_code_is_mapped(self):
        self.assertEqual(checks.completeness_errors(bytes([0x04, 0x81, 0x04, 0x82])), [])


class TestRoundTrip(unittest.TestCase):
    def test_silent_when_text_re_encodes_to_the_same_codes(self):
        para = Paragraph(text="ا", geometry=63, raw="ا", codes=[0x81])
        self.assertEqual(checks.roundtrip_errors([para]), [])

    def test_reports_when_text_does_not_re_encode(self):
        para = Paragraph(text="ب", geometry=63, raw="ب", codes=[0x81])
        self.assertEqual(len(checks.roundtrip_errors([para])), 1)

    def test_surrounding_spaces_do_not_produce_a_false_failure(self):
        # `text` is stripped; `codes` is not. Gate B must compare `raw`.
        para = Paragraph(text="ا", geometry=63, raw=" ا ", codes=[0x20, 0x81, 0x20])
        self.assertEqual(checks.roundtrip_errors([para]), [])


class TestGroundTruth(unittest.TestCase):
    """Amended gate C: a baseline regression gate, not verbatim reproduction.

    The brief's original version flagged every one of the 11 ghazals that
    did not reproduce whole — but the site text and the printed کلیات are
    genuinely different editions, so that reported 10 false alarms. This
    gate instead checks the measured baseline (139/169 lines, >=1 whole
    ghazal) does not regress.
    """

    def test_silent_at_the_committed_baseline(self):
        # Paragraphs built directly from the site text of every known ghazal
        # reproduce all lines verbatim, so this is at least as good as the
        # committed baseline: silent.
        from tools.inpage.groundtruth import KNOWN_GHAZALS, site_text

        paragraphs = [
            Paragraph(text=site_text(slug), geometry=0, raw=site_text(slug))
            for slug in KNOWN_GHAZALS
        ]
        self.assertEqual(checks.groundtruth_errors(paragraphs), [])

    def test_reports_when_nothing_reproduces(self):
        paragraphs = [Paragraph(text="قققق", geometry=0, raw="قققق")]
        errors = checks.groundtruth_errors(paragraphs)
        self.assertGreaterEqual(len(errors), 1)
        joined = " ".join(errors)
        self.assertIn(str(MIN_LINES_MATCHED), joined)
        self.assertIn(str(EXPECTED_LINES_TOTAL), joined)


class TestVerse(unittest.TestCase):
    def test_reports_a_sher_with_one_misra(self):
        segment = Segment(kind="ghazals", title="t", body="ا\nب\n\nج", order=1)
        errors = checks.verse_errors([segment])
        self.assertEqual(len(errors), 1)
        self.assertIn("sher 2", errors[0])

    def test_silent_when_every_sher_has_two_misra(self):
        segment = Segment(kind="ghazals", title="t", body="ا\nب\n\nج\nد", order=1)
        self.assertEqual(checks.verse_errors([segment]), [])

    def test_ignores_non_verse_kinds(self):
        segment = Segment(kind="front_matter", title="t", body="ا\n\nب", order=1)
        self.assertEqual(checks.verse_errors([segment]), [])


class TestLexicon(unittest.TestCase):
    def test_reports_words_absent_from_the_lexicon(self):
        para = Paragraph(text="دل قققق", geometry=63, codes=[])
        report = checks.lexicon_report([para], {"دل"})
        self.assertEqual(len(report), 1)
        self.assertIn("قققق", report[0])


class TestTocCountGate(unittest.TestCase):
    def test_reports_a_mismatch_with_the_delta(self):
        segments = [Segment(kind="ghazals", title="t", body="b", order=1)]
        errors = toc_count_errors(TOC_AND_GHAZAL, segments)
        self.assertEqual(len(errors), 1)
        self.assertIn("2", errors[0])

    def test_reports_when_it_cannot_run(self):
        errors = toc_count_errors([vpara("ا" * 36, 73)], [])
        self.assertEqual(len(errors), 1)
        self.assertIn("no فہرست", errors[0])

    def test_counts_poems_not_the_critical_prose_beside_them(self):
        # Both pilot books print a critic's foreword after the فہرست, and
        # neither book gives it a numbered entry. Counting it would fail the
        # gate by exactly the number of review pieces.
        segments = [
            Segment(kind="ghazals", title="t", body="b", order=1),
            Segment(kind="ghazals", title="t", body="b", order=2),
            Segment(kind="reviews", title="t", body="b", order=3),
        ]
        self.assertEqual(toc_count_errors(TOC_AND_GHAZAL, segments), [])


class TestConservationGate(unittest.TestCase):
    def test_silent_when_every_verse_line_survives(self):
        segments = [Segment(
            kind="ghazals", title="t", order=1,
            body="جسم کی خوشبو الگ\nمیرے دل کا جادو الگ\n\nچاٹ لیتی ہے یہ فکر\nہو نہ جائے تو الگ",
        )]
        self.assertEqual(conservation_errors(TOC_AND_GHAZAL, segments), [])

    def test_reports_a_dropped_line(self):
        segments = [Segment(
            kind="ghazals", title="t", order=1,
            body="جسم کی خوشبو الگ\nمیرے دل کا جادو الگ",
        )]
        errors = conservation_errors(TOC_AND_GHAZAL, segments)
        self.assertEqual(len(errors), 1)
        self.assertIn("4", errors[0])

    def test_prose_carried_by_a_review_is_not_counted_as_a_surplus_line(self):
        # A `reviews` piece legitimately holds the foreword's prose. Counting
        # emitted lines instead of matching them failed by exactly that prose
        # (+7 lines in تجاوز, +11 in باغِ نشاط).
        segments = [
            Segment(
                kind="ghazals", title="t", order=1,
                body="جسم کی خوشبو الگ\nمیرے دل کا جادو الگ\n\nچاٹ لیتی ہے یہ فکر\nہو نہ جائے تو الگ",
            ),
            Segment(kind="reviews", title="t", order=2, body="ا" * 300),
        ]
        self.assertEqual(conservation_errors(TOC_AND_GHAZAL, segments), [])

    def test_reports_a_line_that_reached_two_pieces(self):
        # A count-only gate let a drop in one place hide behind a duplicate
        # in another; "exactly one piece" has to see both.
        piece = Segment(
            kind="ghazals", title="t", order=1,
            body="جسم کی خوشبو الگ\nمیرے دل کا جادو الگ\n\nچاٹ لیتی ہے یہ فکر\nہو نہ جائے تو الگ",
        )
        twice = Segment(kind="ghazals", title="t", order=2, body="جسم کی خوشبو الگ")
        errors = conservation_errors(TOC_AND_GHAZAL, [piece, twice])
        self.assertEqual(len(errors), 1)
        self.assertIn("more than one piece", errors[0])


if __name__ == "__main__":
    unittest.main()
