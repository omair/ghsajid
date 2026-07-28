"""Run the InPage ingestion: inp/*.INP -> out/staging/ -> content/.

    python -m tools.inpage decode  <book-slug>
    python -m tools.inpage segment <book-slug>
    python -m tools.inpage restamp <book-slug>
    python -m tools.inpage promote <book-slug>

`segment` writes staging output and a review report. `promote` refuses to run
until that report is approved, and refuses again if the segmentation changed
after approval. `restamp` re-baselines an approved report against a staged
piece a human hand-corrected after approval: it never re-segments and never
rewrites a staged piece, it only recomputes the hash over the bytes already
on disk and forces the report back to unapproved for re-review.
"""

import collections
import json
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

from .checks import (
    KULLIYAT_VOLUMES,
    TOC_FIRST_LINE_BASELINE,
    VERSE_KINDS,
    clear_unverifiable_sections,
    completeness_errors,
    conservation_errors,
    flag_decode_garbage,
    lexicon_report,
    roundtrip_errors,
    segmentation_groundtruth_errors,
    toc_count_errors,
    toc_first_line_baseline_errors,
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
from .models import Book, Segment
from .ole import read_text_stream
from .promote import promote
from .report import render, restamp_report
from .segment import segment as segment_paragraphs
from tools.migrate.urdu import slugify

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
    "bagh-e-nishat-ki-taraf": "باغِ نشاط کی طرف",
    "kulliyat-jild-1": "مزامیر ۔ کلیات، جلد اول",
    "kulliyat-jild-2": "مزامیر ۔ کلیات، جلد دوم",
}


def _source(book_slug: str) -> Path:
    """Resolve a book slug to its source file, or exit.

    Split out of `_load` so `cmd_promote` can run the same validation without
    re-reading the OLE stream it has no use for. The slug is a path component
    — `STAGING / book_slug` — so an unvalidated one walks out of the staging
    tree: `promote ../../x` read an arbitrary directory as approved staging.
    """
    source = SOURCES.get(book_slug)
    if source is None:
        sys.exit(f"unknown book: {book_slug}. known: {', '.join(sorted(SOURCES))}")
    if not source.exists():
        sys.exit(f"missing source file: {source}")
    return source


def _load(book_slug: str):
    return read_text_stream(_source(book_slug))


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
    # A review's `reviewed_book` is the book it prefaces. Set here rather than
    # in segmentation, which only ever sees one book's paragraphs and has no
    # way to know its title.
    for piece in segments:
        if piece.kind == "reviews":
            piece.reviewed_book = TITLES[book_slug]

    # Gate C (ground truth) is a property of the codepage, not of any one
    # book: the 11 ground-truth ghazals exist only in the کلیات volumes, so
    # running groundtruth_errors() against any other book is a guaranteed
    # false alarm (0/N matched). It is enforced across both کلیات volumes by
    # tests/test_inpage_groundtruth.py instead; the report states that
    # baseline rather than re-running the check per book.
    isolated_pairs, isolated_mapped = excluded_report(data)
    # Read once and shared: the garbage flag and the outlier report below both
    # measure against the archive's own vocabulary, and it walks every file in
    # content/ to build.
    lexicon = corpus_lexicon()
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
        # Also mutates the segments — it adds a flag, which the report prints
        # beside the piece. Nothing is removed: a flagged piece is still
        # staged, still counted by the gates below, still promotable.
        + flag_decode_garbage(segments, lexicon)
        + toc_count_errors(paragraphs, segments)
        + conservation_errors(paragraphs, segments)
        # The کلیات-only gates. Both are wired by slug for the same reason
        # gate C above is not wired per book at all: the 11 ground-truth
        # ghazals exist only in these two volumes, so running the
        # segmentation gate against تجاوز would report 0 of 11 every single
        # run, and a gate that always fails is a gate nobody reads. Each
        # volume is asked only for its own share of the 11 (KULLIYAT_VOLUMES)
        # and against its own measured index floor (TOC_FIRST_LINE_BASELINE).
        + segmentation_groundtruth_errors(
            segments, KULLIYAT_VOLUMES.get(book_slug, ())
        )
        + (
            toc_first_line_baseline_errors(
                paragraphs, segments, TOC_FIRST_LINE_BASELINE[book_slug]
            )
            if book_slug in TOC_FIRST_LINE_BASELINE
            else []
        )
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
    outliers = lexicon_report(paragraphs, lexicon)
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

    # Group pieces and their resolved slugs together, positionally. write_book
    # requires the two lists to correspond index for index.
    pieces_by: dict[str, list[Segment]] = {}
    slugs_by: dict[str, list[str]] = {}
    for piece, slug in zip(book_contents, book_slugs):
        pieces_by.setdefault(piece.collection, []).append(piece)
        slugs_by.setdefault(piece.collection, []).append(slug)

    if list(pieces_by) == [""]:
        # No running headers — تجاوز, باغِ نشاط, کلیات جلد ۱. The book is its
        # own single record.
        write_book(
            Book(title=TITLES[book_slug], slug=book_slug, contents=book_contents),
            book_slugs,
            out,
        )
    else:
        for collection, pieces in pieces_by.items():
            if not collection:
                # Front matter, and anything before the first page header.
                continue
            write_book(
                Book(
                    title=collection,
                    slug=slugify(collection),
                    collected_in=book_slug,
                    contents=pieces,
                ),
                slugs_by[collection],
                out,
            )
    (out / "segments.json").write_text(
        json.dumps([asdict(s) for s in segments], ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    report_path = out / "report.md"
    # Rendered last, and against `out`: the stamped hash covers the bytes of
    # every staged file promote would copy, so it can only be computed once
    # they are all on disk. Anything written into staging after this point
    # voids the approval the reviewer is about to give.
    with open(report_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(book_slug, segments, gate_output, out))
    print(f"{len(segments)} pieces staged. Review and approve: {report_path}")


def cmd_restamp(book_slug: str) -> None:
    """Re-baseline an approved report's hash against hand-corrected staging.

    Never re-segments (that would destroy the correction) and never rewrites
    a staged piece — it only reads what is already on disk, recomputes the
    hash over those bytes, and rewrites the `segmentation:` and `approved:`
    lines of the existing report.md, leaving every other line — including any
    reviewer comments — untouched. `approved:` is always forced back to
    false: a correction is a change, and a change must be re-approved.
    """
    _source(book_slug)   # validate the slug before it is joined onto a path
    book_staging = STAGING / book_slug
    segments_path = book_staging / "segments.json"
    if not segments_path.exists():
        sys.exit(f"no segments.json at {segments_path} — run segment first")
    report_path = book_staging / "report.md"
    if not report_path.exists():
        sys.exit(f"no report at {report_path} — run segment first")

    raw = json.loads(segments_path.read_text(encoding="utf-8"))
    segments = [Segment(**item) for item in raw]
    report_text = report_path.read_text(encoding="utf-8")

    new_text, old_hash, new_hash = restamp_report(
        report_text, segments, book_staging, book_slug
    )
    with open(report_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(new_text)

    changed = "yes" if old_hash != new_hash else "no"
    print(f"segmentation: {old_hash} -> {new_hash} (changed: {changed})")
    print("approved: false — re-review the staged pieces and re-approve before promote.")


def cmd_promote(book_slug: str) -> None:
    _source(book_slug)   # validate the slug before it is joined onto a path
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
    handlers = {
        "decode": cmd_decode,
        "segment": cmd_segment,
        "restamp": cmd_restamp,
        "promote": cmd_promote,
    }
    handler = handlers.get(command)
    if handler is None:
        sys.exit(__doc__)
    handler(book_slug)


if __name__ == "__main__":
    main()
