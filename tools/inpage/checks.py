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
from .models import Paragraph, Segment

VERSE_KINDS = {"ghazals", "nazms"}
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
    """The piece count must equal what the book's own فہرست declares.

    تجاوز's فہرست is numbered 1-100 and باغِ نشاط's 1-85, so the expected
    count is read from the file rather than judged. This turns "866 pieces
    looks wrong" into arithmetic.
    """
    expected = toc_count(paragraphs)
    if expected is None:
        return ["no فہرست found: the piece-count gate could not run"]
    actual = len(segments)
    if actual != expected:
        return [
            f"piece count {actual} does not match the فہرست's {expected} "
            f"(delta {actual - expected:+d})"
        ]
    return []


def conservation_errors(
    paragraphs: list[Paragraph], segments: list[Segment]
) -> list[str]:
    """Every verse paragraph must land in exactly one piece.

    Lines in equals lines out. This is what makes losing a poem impossible
    rather than merely unlikely.
    """
    expected = sum(1 for kind in classify(paragraphs) if kind == VERSE)
    actual = sum(
        1
        for segment in segments
        for line in segment.body.split("\n")
        if line.strip()
    )
    if actual != expected:
        return [
            f"verse conservation failed: {expected} verse paragraphs in, "
            f"{actual} lines out (delta {actual - expected:+d})"
        ]
    return []


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
