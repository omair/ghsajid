"""Find piece boundaries inside a decoded book.

A ghazal carries no title in the source; the site titles poems by their matlaa,
so finding the boundary IS finding the title. The paragraph mark's 4-byte
record is geometry — a line position stepping down a page — not a style id, so
a value that drops back toward the top of a page marks a new piece.

This is heuristic by construction. Nothing here writes to content/: the output
goes to staging with a report, and a human resolves every flag.
"""

from .classify import NORMALISED_HEADINGS, SECTION_HEADINGS
from .groundtruth import skeleton
from .models import Paragraph, Segment

# A real ghazal's matlaa is a line of verse, not a paragraph. When the
# boundary heuristic fails to find a break inside a large prose block (front
# matter, a foreword), the whole block becomes one "title" — one real pilot
# run produced a ~1400-character title that then crashed slugify()'s output
# path. The piece is never dropped for this; it is only flagged so a human
# reviewing the report can see it.
MAX_TITLE_LENGTH = 200


def _body(lines: list[str]) -> str:
    """Join lines into couplets separated by a blank line."""
    couplets = [
        "\n".join(lines[i:i + 2])
        for i in range(0, len(lines), 2)
    ]
    return "\n\n".join(couplets)


def segment(paragraphs: list[Paragraph]) -> list[Segment]:
    """Split decoded paragraphs into candidate pieces."""
    segments: list[Segment] = []
    section = ""
    lines: list[str] = []
    previous = None

    def flush() -> None:
        if not lines:
            return
        flags = ["odd-line-count"] if len(lines) % 2 else []
        if len(lines[0]) > MAX_TITLE_LENGTH:
            flags.append("over-long-title")
        segments.append(Segment(
            kind="ghazals",
            title=lines[0],
            body=_body(lines),
            order=len(segments) + 1,
            section=section,
            flags=flags,
        ))
        lines.clear()

    for para in paragraphs:
        heading = NORMALISED_HEADINGS.get(skeleton(para.text))
        if heading is not None:
            flush()
            section = heading
            previous = None
            continue
        if previous is not None and para.geometry <= previous:
            flush()
        lines.append(para.text)
        previous = para.geometry

    flush()
    return segments
