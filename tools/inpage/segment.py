"""Find piece boundaries inside a decoded book.

A ghazal carries no title in the source; the site titles poems by their matlaa,
so finding the boundary IS finding the title. The paragraph mark's 4-byte
record is geometry — a line position stepping down a page — not a style id, so
a value that drops back toward the top of a page marks a new piece.

This is heuristic by construction. Nothing here writes to content/: the output
goes to staging with a report, and a human resolves every flag.
"""

from .classify import NORMALISED_HEADINGS, SECTION_HEADINGS, SECOND_MISRA_GEOMETRY
from .groundtruth import skeleton
from .models import Paragraph, Segment

# A real ghazal's matlaa is a line of verse, not a paragraph. When the
# boundary heuristic fails to find a break inside a large prose block (front
# matter, a foreword), the whole block becomes one "title" — one real pilot
# run produced a ~1400-character title that then crashed slugify()'s output
# path. The piece is never dropped for this; it is only flagged so a human
# reviewing the report can see it.
MAX_TITLE_LENGTH = 200

# A ghazal's radif can be one word (الگ) or several (بچھی ہوئی). Test longest
# first: a 3-word match is far stronger evidence of a matlaa than a 1-word one.
RADIF_LENGTHS = (3, 2, 1)


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


def pair_shers(run: list[Paragraph]) -> list[tuple[str, str]]:
    """Pair a verse run into shers using the recorded second-misra geometry.

    A trailing line with no partner is returned with an empty second misra
    rather than discarded — losing a line of poetry is never acceptable, and
    the caller flags the half sher for review.
    """
    shers: list[tuple[str, str]] = []
    index = 0
    while index < len(run):
        first = run[index]
        if (
            index + 1 < len(run)
            and run[index + 1].geometry == SECOND_MISRA_GEOMETRY
        ):
            shers.append((first.text, run[index + 1].text))
            index += 2
        else:
            shers.append((first.text, ""))
            index += 1
    return shers


def _tail(text: str, words: int) -> str:
    parts = skeleton(text).split()
    return " ".join(parts[-words:]) if len(parts) >= words else ""


def is_matla(first: str, second: str) -> bool:
    """True when both misras end alike — the opening sher of a ghazal.

    Only the matlaa rhymes across both its lines; every later sher rhymes on
    the second line alone. Compared on the skeleton so a diacritic or comma
    between two printings of the same radif does not break the match.
    """
    if not first or not second:
        return False
    for words in RADIF_LENGTHS:
        head, tail = _tail(first, words), _tail(second, words)
        if head and head == tail:
            return True
    return False


def split_ghazals(
    shers: list[tuple[str, str]],
) -> list[list[tuple[str, str]]]:
    """Group shers into ghazals, starting a new one at each matlaa."""
    groups: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    for first, second in shers:
        if is_matla(first, second) and current:
            groups.append(current)
            current = []
        current.append((first, second))
    if current:
        groups.append(current)
    return groups
