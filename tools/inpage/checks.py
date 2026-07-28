"""Gates run before anything is written.

Silent text corruption in someone's poetry is the failure mode that matters,
so the pipeline refuses to write when these fail. Note carefully which gate
catches which failure: completeness and round-trip are both BLIND to a
wrong-but-consistent mapping, where every poem decodes with the right
character count and re-encodes perfectly while being uniformly wrong. Only
the ground-truth gate can see that, and even it only sees regressions
against the committed baseline, not verbatim reproduction of every ghazal
(see `groundtruth_errors`).
"""

import collections
import re

from .classify import VERSE, classify, toc_count
from .codepage import decode_byte, encode_char, unmapped
from .decode import all_codes
from .groundtruth import (
    EXPECTED_LINES_TOTAL,
    KNOWN_GHAZALS,
    MIN_LINES_MATCHED,
    MIN_WHOLE_GHAZALS,
    line_match_report,
)
from .models import VERSE_KINDS, Paragraph, Segment

WORD = re.compile(r"[^\s]+")


def completeness_errors(data: bytes) -> list[str]:
    """Gate A — every char code in the stream must be in the table.

    Blind spot: `all_codes` iterates `decode()`'s output, so a code that
    `decode.py`'s run-length or control-byte filters exclude never reaches
    this gate at all — not reported unmapped, not reported anything. 0xE8
    (an ornamental divider) is the known instance: it appears only as an
    isolated pair, so gate A can never see it. See `decode.excluded_report`
    for the count of what these filters discard.
    """
    missing = unmapped(all_codes(data))
    if not missing:
        return []
    listed = ", ".join(f"{code:#04x}" for code in sorted(missing))
    return [f"unmapped char codes: {listed}"]


def roundtrip_errors(paragraphs: list[Paragraph]) -> list[str]:
    """Gate B — decoded text must re-encode to the codes it came from.

    Compares against `raw`, not `text`: `text` is stripped while `codes` still
    carries the surrounding space codes.
    """
    errors = []
    for index, para in enumerate(paragraphs, start=1):
        expected = [c for c in para.codes if decode_byte(c) is not None]
        actual = [encode_char(ch) for ch in para.raw if encode_char(ch) is not None]
        if expected != actual:
            errors.append(f"paragraph {index} does not round-trip: {para.text[:40]!r}")
    return errors


def groundtruth_errors(paragraphs: list[Paragraph]) -> list[str]:
    """Gate C — the codepage must still meet the committed ground-truth baseline.

    Not verbatim reproduction: the site text and the printed کلیات are
    genuinely different editions (site-only provenance blocks, InPage
    typesetting conventions, misras run together, real textual variants), so
    asserting that all 11 known ghazals reproduce whole would raise false
    alarms on every review. Instead this checks the codepage still
    reproduces at least as many ground-truth lines letter-for-letter, and at
    least as many whole ghazals, as it did when the baseline
    (`tools.inpage.groundtruth.MIN_LINES_MATCHED` /
    `EXPECTED_LINES_TOTAL` / `MIN_WHOLE_GHAZALS`) was measured. A wrong
    codepage entry breaks hundreds of lines at once and still fails this;
    edition variance already present in the baseline does not.
    """
    report = line_match_report(paragraphs, KNOWN_GHAZALS)
    total = sum(len(results) for results in report.values())
    matched = sum(sum(results) for results in report.values())
    whole = sum(1 for results in report.values() if results and all(results))

    errors = []
    if total != EXPECTED_LINES_TOTAL:
        errors.append(
            f"ground truth corpus size changed: {total} lines total, expected {EXPECTED_LINES_TOTAL}"
        )
    if matched < MIN_LINES_MATCHED:
        errors.append(
            f"ground truth regression: only {matched}/{total} lines reproduce "
            f"(baseline: {MIN_LINES_MATCHED}/{EXPECTED_LINES_TOTAL})"
        )
    if whole < MIN_WHOLE_GHAZALS:
        errors.append(
            f"ground truth regression: only {whole} ghazals reproduce whole "
            f"(baseline: {MIN_WHOLE_GHAZALS})"
        )
    return errors


def lexicon_report(paragraphs: list[Paragraph], lexicon: set[str]) -> list[str]:
    """Gate D — words absent from the lexicon, most frequent first.

    Reported, never fatal: the lexicon cannot know this poet's vocabulary.
    A cluster of related outliers is the signature of a wrong table entry.
    """
    counts = collections.Counter(
        word for para in paragraphs for word in WORD.findall(para.text)
        if word not in lexicon
    )
    return [f"{word} ({n}x)" for word, n in counts.most_common(50)]


def toc_count_errors(
    paragraphs: list[Paragraph], segments: list[Segment]
) -> list[str]:
    """The POEM count must equal what the book's own فہرست declares.

    تجاوز's فہرست is numbered 1-100 and باغِ نشاط's 1-85, so the expected
    count is read from the file rather than judged. This turns "866 pieces
    looks wrong" into arithmetic.

    Counted against the poems, not every piece. Read in the source, each
    فہرست sits under the heading غزلیں and its numbering ends before the
    critical foreword that follows it — تجاوز's numbers run out at paragraph
    65 and Dr Saadat Saeed's essay starts at 67, signed and dated at 83. That
    essay is what becomes the `reviews` pieces (5 in تجاوز, 10 in
    باغِ نشاط), and it is not a numbered entry in either book. Comparing
    total pieces instead made the gate fail by exactly the review count in
    both books — +5 and +10 — while the poems matched the declared 100 and 85
    exactly. So the basis is the poems; the reviews are carried by the
    conservation gate and the report, not counted here.

    Poems before the first BODY heading are excluded, for the same reason.
    باغِ نشاط's epigraph couplet — باغِ نشاط کی طرف اپنے قدم نہیں بڑھے / جب
    سے ہمارے کھوج میں بادِ صبا نہیں رہی, the couplet the book takes its title
    from — was recovered as a real, correctly segmented poem, but it sits at
    paragraphs 129-130, before the book's first heading at 131, so it is not
    a numbered فہرست entry either. Counting every VERSE_KINDS piece made the
    gate read 86 against a declared 85.

    Excluded by POSITION (`Segment.precedes_first_heading`), not by an empty
    `section` string. The section is the wrong property to key on twice over:
    باغِ نشاط's only headings are both نعت, so its ghazals' section is a
    false label that `clear_unverifiable_sections` erases, and تجاوز now has
    no body heading at all, so every one of its poems carries `section: ""`
    — a section-based count read 0 against a declared 100. Position survives
    both: تجاوز has no body heading, so nothing is excluded and all 100
    poems count; باغِ نشاط excludes the one piece before paragraph 131 and
    counts 85. The epigraph is still emitted as a piece, still written to
    the book record, still promotable, just not counted against a فہرست that
    never numbered it.
    """
    expected = toc_count(paragraphs)
    if expected is None:
        return ["no فہرست found: the piece-count gate could not run"]
    actual = sum(
        1 for segment in segments
        if segment.kind in VERSE_KINDS and not segment.precedes_first_heading
    )
    if actual != expected:
        return [
            f"poem count {actual} does not match the فہرست's {expected} "
            f"(delta {actual - expected:+d})"
        ]
    return []


# The share of a book's poems one section may cover before the label stops
# being evidence of anything. باغِ نشاط is the measured case: its only two
# headings are both نعت (paragraphs 131 and 144), the غزلیں heading the book
# really prints never reaches the byte stream at all — InPage keeps some
# headings in separate text frames the linear stream does not carry — and so
# 85 ghazals inherited نعت, 85 of 86 poems, 98.8%.
#
# 0.9 is chosen as the point past which the label has stopped describing a
# section and started describing the whole book. What it really means is that
# the source gave us where a section BEGINS and never where it ENDS: there is
# no second heading to close it, so every poem after the first one keeps
# inheriting. That reading holds whether or not the book truly has one
# section, which is why the message says the boundary could not be determined
# rather than claiming the heading is wrong. Below 0.9 a book is genuinely
# divided and each heading is closed by the next, so the sections stand.
IMPLAUSIBLE_SECTION_SHARE = 0.9


def clear_unverifiable_sections(segments: list[Segment]) -> list[str]:
    """Report and erase a section that swallows most of the book.

    Mutates `segments`, which no other check here does, and deliberately:
    the finding and the remedy are the same act. `section` is written
    verbatim into content/books/*.yaml, so leaving it in place would publish
    نعت — the devotional form addressed to the Prophet — as the label on 85
    of this poet's ghazals. An empty section is honest about what the source
    supports; نعت on a ghazal is a fabrication, and the archive is the wrong
    place to keep one.

    The share is measured over poems (VERSE_KINDS) since that is what a
    section divides, but the label is cleared from every piece carrying it,
    reviews included. See IMPLAUSIBLE_SECTION_SHARE for the threshold.
    """
    poems = [s for s in segments if s.kind in VERSE_KINDS]
    if not poems:
        return []
    counts = collections.Counter(s.section for s in poems if s.section)
    messages = []
    for name, count in counts.most_common():
        if count / len(poems) < IMPLAUSIBLE_SECTION_SHARE:
            continue
        messages.append(
            f'section "{name}" covers {count} of {len(poems)} poems: no '
            f"further heading closes it, so its boundary could not be "
            f"determined — headings may be missing from the source. Cleared "
            f"the section on those pieces rather than asserting it."
        )
        for piece in segments:
            if piece.section == name:
                piece.section = ""
    return messages


def conservation_errors(
    paragraphs: list[Paragraph], segments: list[Segment]
) -> list[str]:
    """No verse text is missing or duplicated corpus-wide.

    Checked by matching the lines themselves, not by counting them. A plain
    count of emitted lines cannot express this: it is off by the prose a
    `reviews` piece legitimately carries (+7 lines in تجاوز, +11 in
    باغِ نشاط, all of them the foreword's paragraphs), and it would let a
    line dropped in one place be masked by a line duplicated in another.
    Comparing multisets of the text says what the gate actually proves —
    nothing lost, nothing emitted twice, across the corpus as a whole — and
    stays blind to the prose either way.

    Blind spot: the comparison is a global multiset, not a per-piece one, so
    it cannot see a line *moving* between pieces. A sher relocated from one
    ghazal to another conserves perfectly and this gate stays silent — it
    does not prove each verse paragraph lands in the *same* piece it started
    in, only that it lands in some piece, exactly once, somewhere.

    The duplication half is counted against the SOURCE's own multiset, not
    against one occurrence each. The critic's opening essay quotes the poet,
    and some of what it quotes is printed again as a ghazal later in the same
    book — تجاوز's بدن کے اپنے تقاضے ہیں، روح کے اپنے appears both in Dr
    Saadat Saeed's essay and in the غزل it is quoted from. The source holds
    that line twice, so emitting it twice is conservation, not duplication.
    Emitting it more often than the source prints it still fails.
    """
    kinds = classify(paragraphs)
    expected = collections.Counter(
        para.text.strip()
        for para, kind in zip(paragraphs, kinds)
        if kind == VERSE and para.text.strip()
    )
    in_source = collections.Counter(
        para.text.strip() for para in paragraphs if para.text.strip()
    )
    emitted = collections.Counter(
        line.strip()
        for segment in segments
        for line in segment.body.split("\n")
        if line.strip()
    )
    errors = []
    lost = expected - emitted
    if lost:
        total = sum(lost.values())
        sample = ", ".join(repr(text[:40]) for text in list(lost)[:3])
        errors.append(
            f"verse conservation failed: {total} of {sum(expected.values())} "
            f"verse paragraphs did not reach a piece: {sample}"
        )
    doubled = collections.Counter({
        text: emitted[text] - in_source[text]
        for text in expected
        if emitted[text] > in_source[text]
    })
    if doubled:
        total = sum(doubled.values())
        sample = ", ".join(repr(text[:40]) for text in list(doubled)[:3])
        errors.append(
            f"verse conservation failed: {total} verse paragraph(s) reached "
            f"more than one piece: {sample}"
        )
    return errors


def verse_errors(segments: list[Segment]) -> list[str]:
    """Gate E — every sher kept both of its misra."""
    errors = []
    for segment in segments:
        if segment.kind not in VERSE_KINDS:
            continue
        stanzas = [s for s in segment.body.split("\n\n") if s.strip()]
        for index, stanza in enumerate(stanzas, start=1):
            lines = [ln for ln in stanza.split("\n") if ln.strip()]
            if len(lines) % 2 and len(stanzas) > 1:
                errors.append(
                    f"{segment.kind}/{segment.title[:30]}: sher {index} has {len(lines)} misra"
                )
    return errors
