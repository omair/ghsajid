import unittest

from tools.inpage import checks
from tools.inpage.checks import conservation_errors, toc_count_errors
from tools.inpage.groundtruth import (
    EXPECTED_LINES_TOTAL, KNOWN_GHAZALS, MIN_LINES_MATCHED,
    MIN_WHOLE_GHAZALS, site_text, skeleton,
)
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


class TestDecodeGarbageFlag(unittest.TestCase):
    """A piece that is not text at all must be flagged, never dropped.

    باغِ نشاط's stream ends in mis-decoded scratch material that became a
    190-character `reviews` piece at order 88. Nothing may be dropped — that
    rule has already caught three separate poem-loss bugs on this pipeline —
    so the piece is kept, flagged, and named in the gate output.
    """

    LEXICON = {"دل", "جان", "شام", "چراغ", "خواب", "آنکھ"}

    def _real(self, order=1):
        # 12 words, all but one in the lexicon: 0.92 — a believable piece.
        body = "دل جان شام چراغ خواب آنکھ\nدل جان شام چراغ خواب قققق"
        return Segment(kind="ghazals", title="اصلی", body=body, order=order)

    def _garbage(self, order=2):
        # 12 words, one in the lexicon: 0.08 — the shape of the real case.
        body = "ٹھڈ ککک ںںں ابلی تاَیِ ئنے\nمعےما کیھا فاوں کری نجج دل"
        return Segment(kind="reviews", title="ں آابلی", body=body, order=order)

    def test_flags_a_piece_almost_none_of_whose_words_are_known(self):
        piece = self._garbage()
        checks.flag_decode_garbage([piece], self.LEXICON)
        self.assertIn(checks.GARBAGE_FLAG, piece.flags)

    def test_does_not_flag_a_real_piece(self):
        piece = self._real()
        checks.flag_decode_garbage([piece], self.LEXICON)
        self.assertEqual(piece.flags, [])

    def test_the_flagged_piece_is_not_dropped_from_the_list(self):
        segments = [self._real(1), self._garbage(2)]
        checks.flag_decode_garbage(segments, self.LEXICON)
        self.assertEqual(len(segments), 2)
        self.assertEqual([s.order for s in segments], [1, 2])

    def test_the_gate_output_names_the_flagged_piece(self):
        messages = checks.flag_decode_garbage(
            [self._real(1), self._garbage(88)], self.LEXICON
        )
        self.assertEqual(len(messages), 1)
        self.assertIn(checks.GARBAGE_FLAG, messages[0])
        self.assertIn("88", messages[0])

    def test_silent_when_every_piece_is_believable(self):
        self.assertEqual(
            checks.flag_decode_garbage([self._real(1), self._real(2)], self.LEXICON),
            [],
        )

    def test_an_empty_body_does_not_divide_by_zero(self):
        piece = Segment(kind="ghazals", title="خالی", body="", order=1)
        self.assertEqual(checks.flag_decode_garbage([piece], self.LEXICON), [])
        self.assertEqual(piece.flags, [])

    def test_a_very_short_piece_is_exempt(self):
        # A two-line قطعہ has too few words for the share to mean anything:
        # at 6 words one unusual word already moves it by 17 points.
        piece = Segment(kind="ghazals", title="قطعہ", body="ٹھڈ ککک ںںں\nابلی تاَیِ ئنے", order=1)
        self.assertLess(
            len(checks.skeleton(piece.body).split()),
            checks.MIN_WORDS_FOR_GARBAGE_CHECK,
        )
        self.assertEqual(checks.flag_decode_garbage([piece], self.LEXICON), [])
        self.assertEqual(piece.flags, [])

    def test_the_threshold_clears_both_measured_extremes(self):
        # Measured on the two books: the weakest real piece (a ghazal) sits at
        # 0.767 and the garbage piece at 0.143. The threshold must have real
        # margin on both sides, not hug either figure.
        self.assertLess(checks.GARBAGE_LEXICON_SHARE, 0.767 / 1.5)
        self.assertGreater(checks.GARBAGE_LEXICON_SHARE, 0.143 * 1.5)

    def test_flagging_twice_does_not_duplicate_the_flag(self):
        piece = self._garbage()
        checks.flag_decode_garbage([piece], self.LEXICON)
        checks.flag_decode_garbage([piece], self.LEXICON)
        self.assertEqual(piece.flags.count(checks.GARBAGE_FLAG), 1)


class TestSingleLinePieceFlag(unittest.TestCase):
    """Defect 2: کلیات جلد ۲ emits 33 one-line 'nazms' — دیدication, an
    orphaned title, decode garbage — indistinguishable without a human.
    Never dropped, never guessed at: just flagged and named.
    """

    def test_a_one_line_piece_is_flagged(self):
        piece = Segment(
            kind="nazms", title="زُبیر ساجد کے لیے",
            body="زُبیر ساجد کے لیے", order=1,
        )
        checks.flag_single_line_pieces([piece])
        self.assertIn(checks.SINGLE_LINE_FLAG, piece.flags)

    def test_a_two_line_piece_is_not_flagged(self):
        piece = Segment(kind="ghazals", title="t", body="ا\nب", order=1)
        checks.flag_single_line_pieces([piece])
        self.assertEqual(piece.flags, [])

    def test_the_flag_does_not_change_kind_body_or_order(self):
        piece = Segment(kind="nazms", title="t", body="ایک سطر", order=5)
        before = (piece.kind, piece.body, piece.order)
        checks.flag_single_line_pieces([piece])
        self.assertEqual((piece.kind, piece.body, piece.order), before)

    def test_ignores_non_verse_kinds(self):
        piece = Segment(kind="reviews", title="t", body="ایک سطر", order=1)
        checks.flag_single_line_pieces([piece])
        self.assertEqual(piece.flags, [])

    def test_an_empty_body_is_not_flagged(self):
        piece = Segment(kind="ghazals", title="t", body="", order=1)
        checks.flag_single_line_pieces([piece])
        self.assertEqual(piece.flags, [])

    def test_the_gate_output_names_the_flagged_piece(self):
        piece = Segment(
            kind="nazms", title="زُبیر ساجد کے لیے",
            body="زُبیر ساجد کے لیے", order=7,
        )
        messages = checks.flag_single_line_pieces([piece])
        self.assertEqual(len(messages), 1)
        self.assertIn(checks.SINGLE_LINE_FLAG, messages[0])
        self.assertIn("7", messages[0])

    def test_silent_when_no_piece_is_one_line(self):
        piece = Segment(kind="ghazals", title="t", body="ا\nب", order=1)
        self.assertEqual(checks.flag_single_line_pieces([piece]), [])

    def test_flagging_twice_does_not_duplicate_the_flag(self):
        piece = Segment(kind="nazms", title="t", body="ایک سطر", order=1)
        checks.flag_single_line_pieces([piece])
        checks.flag_single_line_pieces([piece])
        self.assertEqual(piece.flags.count(checks.SINGLE_LINE_FLAG), 1)


class TestTocCountGate(unittest.TestCase):
    def test_reports_a_mismatch_with_the_delta(self):
        segments = [Segment(kind="ghazals", title="t", body="b", order=1, section="غزلیں")]
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
            Segment(kind="ghazals", title="t", body="b", order=1, section="غزلیں"),
            Segment(kind="ghazals", title="t", body="b", order=2, section="غزلیں"),
            Segment(kind="reviews", title="t", body="b", order=3, section="غزلیں"),
        ]
        self.assertEqual(toc_count_errors(TOC_AND_GHAZAL, segments), [])

    def test_a_poem_before_the_first_body_heading_is_not_counted(self):
        # باغِ نشاط's epigraph couplet -- the poem the book is named after --
        # sits before the نعت heading and is not a numbered فہرست entry. The
        # gate must count only the two poems that follow that heading,
        # matching the declared count of 2, and stay silent even though a
        # third VERSE_KINDS piece exists in the source. Keyed on position,
        # not on the section string: the section may legitimately be cleared
        # (see checks.clear_unverifiable_sections) and the arithmetic must
        # not move when it is.
        segments = [
            Segment(kind="ghazals", title="epigraph", body="b", order=1,
                    precedes_first_heading=True),
            Segment(kind="ghazals", title="t", body="b", order=2, section="نعت"),
            Segment(kind="ghazals", title="t", body="b", order=3, section="نعت"),
        ]
        self.assertEqual(toc_count_errors(TOC_AND_GHAZAL, segments), [])
        for segment_ in segments:
            segment_.section = ""
        self.assertEqual(toc_count_errors(TOC_AND_GHAZAL, segments), [])

    def test_a_book_with_no_body_heading_counts_all_its_poems(self):
        # تجاوز's shape after the fix: its only headings are in the front
        # matter, so no piece is marked and every poem is counted. Nothing
        # is excluded when there is no body heading to be before.
        segments = [
            Segment(kind="ghazals", title="t", body="b", order=1),
            Segment(kind="ghazals", title="t", body="b", order=2),
        ]
        self.assertEqual(toc_count_errors(TOC_AND_GHAZAL, segments), [])

    def test_still_fails_when_poems_exceed_the_declared_count(self):
        # Over-splitting must still be caught -- excluding the poems before
        # the first body heading must never be able to mask a real surplus.
        segments = [
            Segment(kind="ghazals", title="t", body="b", order=1, section="غزلیں"),
            Segment(kind="ghazals", title="t", body="b", order=2, section="غزلیں"),
            Segment(kind="ghazals", title="t", body="b", order=3, section="غزلیں"),
        ]
        errors = toc_count_errors(TOC_AND_GHAZAL, segments)
        self.assertEqual(len(errors), 1)
        self.assertIn("+1", errors[0])

    def test_still_fails_when_poems_fall_short_of_the_declared_count(self):
        segments = [
            Segment(kind="ghazals", title="t", body="b", order=1, section="غزلیں"),
        ]
        errors = toc_count_errors(TOC_AND_GHAZAL, segments)
        self.assertEqual(len(errors), 1)
        self.assertIn("-1", errors[0])


class TestUnverifiableSection(unittest.TestCase):
    """A heading whose section swallows the book cannot be asserted.

    باغِ نشاط's only two headings are both نعت, and the غزلیں heading the
    book really has never reaches the byte stream — so 85 ghazals were being
    labelled as naat. An empty section is honest; نعت on a ghazal is not.
    """

    def test_a_section_covering_the_whole_book_is_reported_and_cleared(self):
        poems = [
            Segment(kind="ghazals", title="t", body="b", order=i, section="نعت")
            for i in range(1, 11)
        ]
        messages = checks.clear_unverifiable_sections(poems)
        self.assertEqual(len(messages), 1)
        self.assertIn("نعت", messages[0])
        self.assertIn("10", messages[0])
        self.assertEqual({s.section for s in poems}, {""})

    def test_a_section_covering_part_of_a_book_is_left_alone(self):
        poems = [
            Segment(kind="ghazals", title="t", body="b", order=i, section="نعت")
            for i in range(1, 4)
        ] + [
            Segment(kind="ghazals", title="t", body="b", order=i, section="غزلیں")
            for i in range(4, 11)
        ]
        self.assertEqual(checks.clear_unverifiable_sections(poems), [])
        self.assertEqual(
            {s.section for s in poems}, {"نعت", "غزلیں"}
        )

    def test_the_count_gate_is_unmoved_by_the_clearing(self):
        # The reason the gate had to stop keying on the section string: the
        # clearing below empties every section, which a section-based count
        # would read as zero poems against a declared 2.
        segments = [
            Segment(kind="ghazals", title="epigraph", body="b", order=1,
                    precedes_first_heading=True),
            Segment(kind="ghazals", title="t", body="b", order=2, section="نعت"),
            Segment(kind="ghazals", title="t", body="b", order=3, section="نعت"),
        ]
        checks.clear_unverifiable_sections(segments)
        self.assertEqual(toc_count_errors(TOC_AND_GHAZAL, segments), [])

    def test_a_review_carrying_the_same_section_is_cleared_too(self):
        # The share is measured over poems, but the false label is cleared
        # wherever it was written.
        segments = [
            Segment(kind="ghazals", title="t", body="b", order=i, section="نعت")
            for i in range(1, 11)
        ] + [Segment(kind="reviews", title="r", body="r", order=11, section="نعت")]
        checks.clear_unverifiable_sections(segments)
        self.assertEqual({s.section for s in segments}, {""})

    def test_silent_when_no_piece_carries_a_section(self):
        segments = [Segment(kind="ghazals", title="t", body="b", order=1)]
        self.assertEqual(checks.clear_unverifiable_sections(segments), [])


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

    def test_a_line_the_source_prints_twice_may_be_emitted_twice(self):
        # The critic's essay quotes a sher that the book also prints as part
        # of a ghazal — تجاوز's بدن کے اپنے تقاضے ہیں، روح کے اپنے is in both.
        # Now that the essay region keeps its quotations, the line legitimately
        # reaches two pieces because the source holds it twice.
        quoted = "جسم کی خوشبو الگ"
        paragraphs = [vpara(quoted, 70), vpara("ا" * 300, 67)] + TOC_AND_GHAZAL
        segments = [
            Segment(kind="reviews", title="t", order=1,
                    body=f"{quoted}\n\n" + "ا" * 300),
            Segment(
                kind="ghazals", title="t", order=2,
                body="جسم کی خوشبو الگ\nمیرے دل کا جادو الگ\n\nچاٹ لیتی ہے یہ فکر\nہو نہ جائے تو الگ",
            ),
        ]
        self.assertEqual(conservation_errors(paragraphs, segments), [])


class TestSegmentationGroundTruth(unittest.TestCase):
    """Gate 1 — each of the 11 known ghazals must be exactly one piece.

    The pieces here are built from the committed site text itself, so the
    fixture is the same ground truth the gate reads in production rather than
    a paraphrase of it.
    """

    def _pieces(self):
        return [
            Segment(kind="ghazals", title=slug, body=site_text(slug), order=i)
            for i, slug in enumerate(KNOWN_GHAZALS, start=1)
        ]

    def test_silent_when_every_ghazal_is_exactly_one_piece(self):
        self.assertEqual(
            checks.segmentation_groundtruth_errors(self._pieces()), []
        )

    def test_reports_a_ghazal_no_piece_holds(self):
        errors = checks.segmentation_groundtruth_errors(
            [Segment(kind="ghazals", title="x", body="ا" * 40, order=1)]
        )
        self.assertEqual(len(errors), len(KNOWN_GHAZALS))
        self.assertIn(KNOWN_GHAZALS[0], errors[0])
        self.assertIn("0", errors[0])

    def test_reports_a_ghazal_split_across_two_pieces(self):
        # The failure a running page header causes: the opening survives in
        # one piece and the rest lands in the next.
        pieces = self._pieces()
        victim = pieces[0]
        lines = [ln for ln in victim.body.splitlines() if skeleton(ln)]
        half = len(lines) // 2
        victim.body = "\n".join(lines[:half])
        pieces.append(
            Segment(kind="ghazals", title="tail", order=99,
                    body="\n".join(lines[half:]))
        )
        errors = checks.segmentation_groundtruth_errors(pieces)
        self.assertEqual(len(errors), 1)
        self.assertIn(KNOWN_GHAZALS[0], errors[0])
        self.assertIn("2", errors[0])

    def test_reports_a_ghazal_fused_behind_another(self):
        # Fusion, which a bare holder count cannot see: both ghazals are in
        # one piece, so each has exactly one holder. The second ghazal fails
        # to open its piece, which is what the "opens with it" check catches.
        # The first ghazal now also runs materially past its own last line
        # (the second ghazal's text is appended after it), which the extent
        # bound added below catches independently -- welding two whole
        # ghazals together trips BOTH checks, one per slug.
        pieces = self._pieces()
        first, second = pieces[0], pieces[1]
        first.body = f"{first.body}\n{second.body}"
        pieces.remove(second)
        errors = checks.segmentation_groundtruth_errors(pieces)
        self.assertEqual(len(errors), 2)
        joined = " ".join(errors)
        self.assertIn(KNOWN_GHAZALS[0], joined)
        self.assertIn(KNOWN_GHAZALS[1], joined)
        self.assertIn("welded onto its end", joined)
        self.assertIn("fused behind another", joined)

    def test_reports_a_ghazal_fused_with_the_piece_after_it(self):
        # The complement Finding 1 closes: the known ghazal LEADS and an
        # unknown piece is welded onto its END. Both land in one piece (the
        # holder count stays 1) and the known ghazal still opens the piece
        # (the "opens with it" check stays silent too) -- before this fix,
        # mutating a holder this way was silent for all 11. Only a bound on
        # the holder's own extent catches it.
        pieces = self._pieces()
        victim = pieces[0]
        # Well past HOLDER_LINE_COUNT_TOLERANCE (5) and past the measured
        # spread (-3 to +2), so this cannot be edition variance.
        welded_on = "\n".join(f"قققق ثثثث {n}" for n in range(20))
        victim.body = f"{victim.body}\n{welded_on}"
        errors = checks.segmentation_groundtruth_errors(pieces)
        self.assertEqual(len(errors), 1)
        self.assertIn(KNOWN_GHAZALS[0], errors[0])
        self.assertIn("welded onto its end", errors[0])

    def test_the_extent_bound_tolerates_the_measured_edition_variance(self):
        # A holder legitimately running a little longer than the site copy
        # (see HOLDER_LINE_COUNT_TOLERANCE's measured -3..+2 spread) must not
        # be flagged. +2 is the largest measured surplus; the bound must
        # clear it with room.
        pieces = self._pieces()
        victim = pieces[0]
        extra = "\n".join(f"قققق ثثثث {n}" for n in range(2))
        victim.body = f"{victim.body}\n{extra}"
        self.assertEqual(checks.segmentation_groundtruth_errors(pieces), [])

    def test_the_volume_map_covers_every_known_ghazal_exactly_once(self):
        # The per-book wiring narrows the gate to one volume's share. If that
        # map ever drifts from KNOWN_GHAZALS, a ghazal silently stops being
        # gated anywhere — the failure this whole gate exists to prevent.
        listed = [
            slug for slugs in checks.KULLIYAT_VOLUMES.values() for slug in slugs
        ]
        self.assertEqual(sorted(listed), sorted(KNOWN_GHAZALS))
        self.assertEqual(len(listed), len(set(listed)))

    def test_prefix_matching_rejects_a_coincidental_substring_match(self):
        # Every line of this ghazal ends in the same radif, "کا حق ہے".
        # Bidirectional substring matching (opening in line OR line in
        # opening) would accept a holder whose real opening line was
        # unrelated garbage that merely CONTAINED that radif somewhere,
        # since the radif is a substring of every real line even though it
        # is never a PREFIX of one. Prefix matching correctly rejects it.
        pieces = self._pieces()
        victim = pieces[0]
        _, rest = victim.body.split("\n", 1)
        victim.body = f"کا حق ہے\n{rest}"
        errors = checks.segmentation_groundtruth_errors(pieces)
        self.assertEqual(len(errors), 1)
        self.assertIn(KNOWN_GHAZALS[0], errors[0])
        self.assertIn("fused behind another", errors[0])

    def test_a_prose_piece_quoting_a_ghazal_is_not_a_second_holder(self):
        # The فہرست and the critic's essay both reproduce lines of these
        # ghazals. Counting them would report a false split on every run.
        pieces = self._pieces()
        pieces.append(
            Segment(kind="reviews", title="essay", order=98,
                    body=site_text(KNOWN_GHAZALS[0]))
        )
        self.assertEqual(checks.segmentation_groundtruth_errors(pieces), [])


class TestKulliyatIndexBaseline(unittest.TestCase):
    """Gate 2 — the partial index as a floor, explicitly not a census."""

    FRONT = [
        vpara("جسم کی خوشبو الگ سے", 80),
        vpara("چاٹ لیتی ہے یہ فکر و خیال", 80),
    ]
    BODY = [
        vpara("جسم کی خوشبو الگ سے", 73), vpara("میرے دل کا جادو الگ", 1),
        vpara("چاٹ لیتی ہے یہ فکر", 89), vpara("ہو نہ جائے تو الگ", 1),
    ]

    def _fixture(self):
        paragraphs = self.FRONT + self.BODY
        segments = [
            Segment(
                kind="ghazals", title="t", order=1,
                body="جسم کی خوشبو الگ سے\nمیرے دل کا جادو الگ",
            )
        ]
        return paragraphs, segments

    def test_silent_when_the_floor_is_met(self):
        paragraphs, segments = self._fixture()
        self.assertEqual(
            checks.toc_first_line_baseline_errors(paragraphs, segments, 1), []
        )

    def test_reports_when_the_baseline_falls_below_the_floor(self):
        paragraphs, segments = self._fixture()
        errors = checks.toc_first_line_baseline_errors(paragraphs, segments, 2)
        self.assertEqual(len(errors), 1)
        self.assertIn("1", errors[0])
        self.assertIn("2", errors[0])

    def test_the_message_denies_being_a_census(self):
        paragraphs, segments = self._fixture()
        errors = checks.toc_first_line_baseline_errors(paragraphs, segments, 2)
        self.assertIn("census", errors[0])


class TestDeclaredCollectionCounts(unittest.TestCase):
    """A collection whose poem count the volume's own فہرست declares.

    کلیات جلد ۱'s فہرست states موسم's six sections as بیس غزلیں five times
    over plus تیس غزلیں (130) and عناصر's five as بیس غزلیں each (100). Those
    are the book declaring its own arithmetic, in the same class as تجاوز's
    numbered فہرست, so they are asserted rather than judged. The volume's
    other four collections declare nothing, and must NOT be asserted against
    a number someone invented for them.
    """

    DECLARED = {"موسم": 3, "عناصر": 2}

    def _poems(self, mausam: int, anasir: int):
        segments = []
        order = 1
        for name, count in (("موسم", mausam), ("عناصر", anasir)):
            for _ in range(count):
                segments.append(Segment(
                    kind="ghazals", title="x", body="x", order=order,
                    collection=name,
                ))
                order += 1
        # A review inside a collection is not one of its poems.
        segments.append(Segment(
            kind="reviews", title="r", body="r", order=order,
            collection="موسم",
        ))
        # An undeclared collection is reported elsewhere, never asserted here.
        segments.append(Segment(
            kind="ghazals", title="y", body="y", order=order + 1,
            collection="روداد",
        ))
        return segments

    def test_silent_when_every_declared_count_is_met(self):
        self.assertEqual(
            checks.declared_collection_count_errors(
                self._poems(3, 2), self.DECLARED
            ),
            [],
        )

    def test_a_short_collection_reports_its_delta(self):
        errors = checks.declared_collection_count_errors(
            self._poems(1, 2), self.DECLARED
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("موسم", errors[0])
        self.assertIn("-2", errors[0])

    def test_a_long_collection_reports_its_delta(self):
        errors = checks.declared_collection_count_errors(
            self._poems(3, 5), self.DECLARED
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("عناصر", errors[0])
        self.assertIn("+3", errors[0])

    def test_a_collection_that_was_never_attributed_is_reported(self):
        segments = [s for s in self._poems(3, 2) if s.collection != "عناصر"]
        errors = checks.declared_collection_count_errors(
            segments, self.DECLARED
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("عناصر", errors[0])
        self.assertIn("-2", errors[0])

    def test_no_declaration_asserts_nothing(self):
        self.assertEqual(
            checks.declared_collection_count_errors(self._poems(1, 1), {}), []
        )

    def test_the_real_declarations_are_the_two_the_fihrist_states(self):
        self.assertEqual(
            checks.DECLARED_COLLECTION_COUNTS,
            {"kulliyat-jild-1": {"موسم": 130, "عناصر": 100}},
        )


if __name__ == "__main__":
    unittest.main()


class TestCountGateSkipsAGathering(unittest.TestCase):
    """A کلیات volume has no whole-book numbering to read.

    جلد ۲'s numeric index yields 124 against 561 poems — it numbers one
    collection's contents, not the volume's — so the gate reported a
    guaranteed `delta +437` on every report, and جلد ۱ reported "could not
    run". A gate a reviewer learns to ignore is worse than no gate.
    `declared_collection_count_errors` is the equivalent for a gathering.
    """

    def paras(self):
        return [vpara("۱۔۲۔", 80),
                vpara("جسم کی خوشبو الگ", 73), vpara("کا جادو الگ ہے", 1),
                vpara("چاٹ لیتی ہے یہ فکر", 89), vpara("ہو نہ جائے تو الگ", 1)]

    def test_a_single_book_is_still_counted(self):
        segs = [Segment(kind="ghazals", title="t", body="b", order=1)]
        errors = toc_count_errors(self.paras(), segs)
        self.assertEqual(len(errors), 1)
        self.assertIn("2", errors[0])

    def test_a_gathering_is_not_counted_against_a_partial_index(self):
        segs = [
            Segment(kind="ghazals", title="t", body="b", order=1,
                    collection="نیند میں چلتے ہوئے"),
        ]
        self.assertEqual(toc_count_errors(self.paras(), segs), [])
