"""Run the InPage ingestion: inp/*.INP -> out/staging/ -> content/.

    python -m tools.inpage decode  <book-slug>
    python -m tools.inpage segment <book-slug>
    python -m tools.inpage promote <book-slug>

`segment` writes staging output and a review report. `promote` refuses to run
until that report is approved, and refuses again if the segmentation changed
after approval.
"""

import collections
import json
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

from .checks import (
    VERSE_KINDS,
    clear_unverifiable_sections,
    completeness_errors,
    conservation_errors,
    lexicon_report,
    roundtrip_errors,
    toc_count_errors,
    verse_errors,
)
from .decode import decode, excluded_report
from .emit import write_book, write_segments
from .groundtruth import (
    EXPECTED_LINES_TOTAL,
    MIN_LINES_MATCHED,
    MIN_WHOLE_GHAZALS,
    corpus_lexicon,
)
from .models import Book
from .ole import read_text_stream
from .promote import promote
from .report import render
from .segment import segment as segment_paragraphs

SOURCES = {
    "tajawuz": Path("inp/TAJAWUZ.INP"),
    "bagh-e-nishat-ki-taraf": Path("inp/BAGH E NISHAT KI TARAF.INP"),
    "kulliyat-jild-1": Path("inp/MAZAMEER (1).INP"),
    "kulliyat-jild-2": Path("inp/MAZAMEER (2).INP"),
}
STAGING = Path("out/staging")
CONTENT = Path("content")

TITLES = {
    "tajawuz": "تجاوز",
    "bagh-e-nishat-ki-taraf": "باغ نشاط کی طرف",
    "kulliyat-jild-1": "مزامیر ۔ کلیات، جلد اول",
    "kulliyat-jild-2": "مزامیر ۔ کلیات، جلد دوم",
}


def _load(book_slug: str):
    source = SOURCES.get(book_slug)
    if source is None:
        sys.exit(f"unknown book: {book_slug}. known: {', '.join(sorted(SOURCES))}")
    if not source.exists():
        sys.exit(f"missing source file: {source}")
    return read_text_stream(source)


def book_contents_and_slugs(
    segments: list, slugs: list[str]
) -> tuple[list, list[str]]:
    """Filter (segments, their resolved slugs) down to Book.contents rows.

    Book.contents feeds src/content.config.ts's books schema, which only
    allows kind: ghazals | nazms — a `reviews` row would fail validation (or,
    if the schema were ever loosened, trip resolveBook's dead-reference
    throw, since `promote` deliberately skips reviews pieces). Reviews are
    still written to staging by `write_segments` and still listed in the
    report; they are simply not book-contents rows. `segments` and `slugs`
    are filtered together, in lockstep, so the pairing (segment, its
    resolved slug) stays positional and in book order.
    """
    contents: list = []
    resolved: list[str] = []
    for segment, slug in zip(segments, slugs, strict=True):
        if segment.kind in VERSE_KINDS:
            contents.append(segment)
            resolved.append(slug)
    return contents, resolved


def cmd_decode(book_slug: str) -> None:
    data = _load(book_slug)
    paragraphs = decode(data)
    print(f"{len(paragraphs)} paragraphs")
    for error in completeness_errors(data):
        print(f"  GATE A: {error}")
    for error in roundtrip_errors(paragraphs)[:10]:
        print(f"  GATE B: {error}")


def cmd_segment(book_slug: str) -> None:
    data = _load(book_slug)
    paragraphs = decode(data)
    dropped_unknowns: list[str] = []
    unreached: list[tuple[str, object]] = []
    segments = segment_paragraphs(paragraphs, dropped_unknowns, unreached)

    # Gate C (ground truth) is a property of the codepage, not of any one
    # book: the 11 ground-truth ghazals exist only in the کلیات volumes, so
    # running groundtruth_errors() against any other book is a guaranteed
    # false alarm (0/N matched). It is enforced across both کلیات volumes by
    # tests/test_inpage_groundtruth.py instead; the report states that
    # baseline rather than re-running the check per book.
    isolated_pairs, isolated_mapped = excluded_report(data)
    gate_output = (
        completeness_errors(data)
        + roundtrip_errors(paragraphs)[:20]
        + [
            f"ground truth (gate C) is enforced by the test suite across both "
            f"کلیات volumes, not per book: baseline is {MIN_LINES_MATCHED}/"
            f"{EXPECTED_LINES_TOTAL} lines and {MIN_WHOLE_GHAZALS} whole "
            f"ghazal(s) (see tests/test_inpage_groundtruth.py)."
        ]
        + [
            f"{isolated_pairs} isolated pairs excluded as layout records, "
            f"{isolated_mapped} of which decoded to a character"
        ]
        + verse_errors(segments)
        # Runs before anything is written: it erases a section label the
        # source cannot support, and write_book/report both read `section`.
        # The count gate is unaffected by the erasure by construction — it
        # reads position, not the section string.
        + clear_unverifiable_sections(segments)
        + toc_count_errors(paragraphs, segments)
        + conservation_errors(paragraphs, segments)
    )
    if dropped_unknowns:
        # The spec says unknown is flagged and retained, never dropped — but
        # segment() only retains an UNKNOWN paragraph's text when a nazm with
        # no title of its own immediately follows it. Every other UNKNOWN
        # reaches no piece and no flag, which is invisible unless surfaced
        # here: this is the same shape of loss as a real dropped-misra bug,
        # even though every instance measured so far is mis-decode garbage.
        sample = ", ".join(repr(text[:60]) for text in dropped_unknowns[:5])
        gate_output.append(
            f"{len(dropped_unknowns)} unknown paragraph(s) reached no piece "
            f"(first few: {sample})"
        )
    if unreached:
        # The general form of the line above, and the one that would have
        # caught the dropped-foreword bug: an essay's quoted verse sat before
        # the first ghazal, classified front_matter, and reached no piece at
        # all — ~55 lines of the poet's own work, lost with no report of any
        # kind. A nonzero count here is expected (the title page, the فہرست,
        # the ۰۰۰ separators and the section headings all legitimately reach
        # no piece); the point is that the number is stated, so the next
        # regression of this shape shows up as the number moving.
        counts = collections.Counter(kind for kind, _ in unreached)
        breakdown = ", ".join(
            f"{kind} {count}" for kind, count in sorted(counts.items())
        )
        gate_output.append(
            f"{len(unreached)} paragraph(s) reached no piece, by kind: "
            f"{breakdown}"
        )
        sample = ", ".join(
            repr(para.text[:40]) for _, para in unreached[:5]
        )
        gate_output.append(f"  first few unreached: {sample}")
    outliers = lexicon_report(paragraphs, corpus_lexicon())
    if outliers:
        gate_output.append("lexicon outliers (review for clustered mis-decodes): "
                           + ", ".join(outliers[:20]))

    out = STAGING / book_slug
    # Clear this book's staging directory before writing, not just create it:
    # otherwise a piece from a previous run that this run's segmentation no
    # longer produces (renamed, merged, dropped) survives as an orphan file
    # that `promote` could later copy despite never being described by the
    # approved segments.json. Scoped to exactly out/staging/<book_slug>/, so
    # nothing outside this one book's staging is ever touched, and re-running
    # is still safe — the directory is simply rebuilt from scratch each time.
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    _, slugs, problems = write_segments(segments, book_slug, out)
    gate_output.extend(problems)
    book_contents, book_slugs = book_contents_and_slugs(segments, slugs)
    write_book(
        Book(title=TITLES[book_slug], slug=book_slug, contents=book_contents),
        book_slugs,
        out,
    )
    (out / "segments.json").write_text(
        json.dumps([asdict(s) for s in segments], ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    report_path = out / "report.md"
    with open(report_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(book_slug, segments, gate_output))
    print(f"{len(segments)} pieces staged. Review and approve: {report_path}")


def cmd_promote(book_slug: str) -> None:
    written, problems = promote(book_slug, STAGING, CONTENT)
    for problem in problems:
        print(f"  {problem}")
    print(f"{len(written)} files written to content/")
    if problems:
        sys.exit(1)


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    command, book_slug = sys.argv[1], sys.argv[2]
    handlers = {"decode": cmd_decode, "segment": cmd_segment, "promote": cmd_promote}
    handler = handlers.get(command)
    if handler is None:
        sys.exit(__doc__)
    handler(book_slug)


if __name__ == "__main__":
    main()
