"""Find piece boundaries inside a decoded book.

A ghazal carries no title in the source; the site titles poems by their matlaa,
so finding the boundary IS finding the title. The paragraph mark's 4-byte
record is geometry — a line position stepping down a page — not a style id, so
a value that drops back toward the top of a page marks a new piece.

This is heuristic by construction. Nothing here writes to content/: the output
goes to staging with a report, and a human resolves every flag.
"""

from .classify import (
    COLOPHON, HEADING, NORMALISED_HEADINGS, PROSE, SECOND_MISRA_GEOMETRY,
    SECTION_HEADINGS, UNKNOWN, VERSE, classify,
)
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


GHAZAL_SHAPE_THRESHOLD = 0.9


def _is_ghazal_shaped(run: list[Paragraph]) -> bool:
    """True when the run alternates (non-1, 1) as a ghazal's misras do.

    Not an exact test: the corpus has 8 exceptions in 1642 transitions, so
    demanding perfection would misfile real ghazals as nazms.
    """
    if len(run) < 2:
        return False
    matches = sum(
        1
        for index, para in enumerate(run)
        if (para.geometry == SECOND_MISRA_GEOMETRY) == (index % 2 == 1)
    )
    return matches / len(run) >= GHAZAL_SHAPE_THRESHOLD


def _ghazal_body(shers: list[tuple[str, str]]) -> str:
    return "\n\n".join(
        "\n".join(line for line in sher if line) for sher in shers
    )


def segment(paragraphs: list[Paragraph]) -> list[Segment]:
    """Assemble classified paragraphs into pieces.

    Heuristic by construction — output goes to staging behind a review report,
    never straight to content/. Nothing is ever dropped: an unpaired line is
    flagged, and a run that fits no pattern still becomes a piece.
    """
    kinds = classify(paragraphs)
    pieces: list[Segment] = []
    section = ""
    title_candidate = ""

    def add(kind: str, title: str, body: str, flags: list[str]) -> Segment:
        if len(title) > MAX_TITLE_LENGTH:
            flags = flags + ["over-long-title"]
        piece = Segment(
            kind=kind,
            title=title,
            body=body,
            order=len(pieces) + 1,
            section=section,
            flags=flags,
        )
        pieces.append(piece)
        return piece

    index = 0
    while index < len(paragraphs):
        kind = kinds[index]
        para = paragraphs[index]

        if kind == HEADING:
            section = NORMALISED_HEADINGS[skeleton(para.text)]
            index += 1
            continue

        if kind == COLOPHON:
            if pieces:
                pieces[-1].written_note = para.text
            index += 1
            continue

        if kind == UNKNOWN:
            title_candidate = para.text
            index += 1
            continue

        if kind == PROSE:
            start = index
            while index < len(paragraphs) and kinds[index] in (PROSE, VERSE):
                index += 1
            body = "\n\n".join(p.text for p in paragraphs[start:index])
            add("reviews", paragraphs[start].text[:MAX_TITLE_LENGTH], body, [])
            title_candidate = ""
            continue

        if kind == VERSE:
            start = index
            while index < len(paragraphs) and kinds[index] == VERSE:
                index += 1
            run = paragraphs[start:index]
            if _is_ghazal_shaped(run):
                for group in split_ghazals(pair_shers(run)):
                    flags = ["half-sher"] if any(not s[1] for s in group) else []
                    add("ghazals", group[0][0], _ghazal_body(group), flags)
            else:
                title = title_candidate or run[0].text
                add("nazms", title, "\n".join(p.text for p in run), [])
            title_candidate = ""
            continue

        index += 1

    return pieces


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
