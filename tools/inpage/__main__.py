"""Run the InPage ingestion: inp/*.INP -> out/staging/ -> content/.

    python -m tools.inpage decode  <book-slug>
    python -m tools.inpage segment <book-slug>
    python -m tools.inpage promote <book-slug>

`segment` writes staging output and a review report. `promote` refuses to run
until that report is approved, and refuses again if the segmentation changed
after approval.
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

from .checks import (
    completeness_errors,
    groundtruth_errors,
    lexicon_report,
    roundtrip_errors,
    verse_errors,
)
from .decode import decode
from .emit import write_book, write_segments
from .groundtruth import corpus_lexicon
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
    segments = segment_paragraphs(paragraphs)

    gate_output = (
        completeness_errors(data)
        + roundtrip_errors(paragraphs)[:20]
        + groundtruth_errors(paragraphs)
        + verse_errors(segments)
    )
    outliers = lexicon_report(paragraphs, corpus_lexicon())
    if outliers:
        gate_output.append("lexicon outliers (review for clustered mis-decodes): "
                           + ", ".join(outliers[:20]))

    out = STAGING / book_slug
    out.mkdir(parents=True, exist_ok=True)
    _, problems = write_segments(segments, book_slug, out)
    gate_output.extend(problems)
    write_book(
        Book(title=TITLES[book_slug], slug=book_slug, contents=segments),
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
