"""Find piece boundaries inside a decoded book.

A ghazal carries no title in the source; the site titles poems by their matlaa,
so finding the boundary IS finding the title. The paragraph mark's 4-byte
record is geometry — a line position stepping down a page — not a style id, so
a value that drops back toward the top of a page marks a new piece.

This is heuristic by construction. Nothing here writes to content/: the output
goes to staging with a report, and a human resolves every flag.
"""

from .groundtruth import skeleton
from .models import Paragraph, Segment

SECTION_HEADINGS = frozenset({
    "غزلیں", "نعت", "نظمیں", "حمد", "قطعات", "رباعیات",
    "نیند میں چلتے ہوئے", "چہار دریا", "ہست و بود", "اعادہ", "حقیقت", "گل سیمیا",
})

# Headings in the کلیات source can carry diacritics the codepage now maps
# (e.g. گُل سیمیا with a pesh on the گ). SECTION_HEADINGS stays written in
# plain form per the brief; comparisons go through skeleton() instead, so the
# match is diacritic-insensitive without touching the readable constant.
# Precomputed once — not per paragraph — since this set never changes. Maps
# the normalised form back to the plain heading, so a diacritic-bearing
# source heading (گُل سیمیا) still records the section as گل سیمیا, matching
# SECTION_HEADINGS rather than whatever spelling the source happened to use.
_NORMALISED_HEADINGS = {skeleton(heading): heading for heading in SECTION_HEADINGS}

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
        heading = _NORMALISED_HEADINGS.get(skeleton(para.text))
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
