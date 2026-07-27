"""Write segmented pieces and book records to the staging tree."""

from pathlib import Path

from tools.migrate.emit import frontmatter
from tools.migrate.models import Piece
from tools.migrate.urdu import slugify

from .models import Book, Segment

# A filesystem-safe ceiling on the generated slug. An over-long "title" (a
# misdetected paragraph run with no line break — see segment.MAX_TITLE_LENGTH)
# slugifies into a filename component long enough to raise OSError on write,
# crashing the CLI before any report is produced. Capped well under common
# filename limits (255 bytes), and short enough that ordinary titles never
# come close to it.
MAX_SLUG_LENGTH = 80


def _cap_slug(slug: str) -> str:
    """Truncate `slug` to MAX_SLUG_LENGTH, cutting at a `-` boundary.

    Cutting mid-word would produce an unreadable, possibly misleading
    fragment; cutting at the last `-` at or before the limit keeps every
    remaining word whole. Slugs already at or under the limit are returned
    unchanged, byte-identical to today's output.
    """
    if len(slug) <= MAX_SLUG_LENGTH:
        return slug
    truncated = slug[:MAX_SLUG_LENGTH]
    boundary = truncated.rfind("-")
    if boundary > 0:
        truncated = truncated[:boundary]
    return truncated.strip("-")


def _piece(segment: Segment, book_slug: str) -> Piece:
    # Language is NOT auto-detected. Punjabi in Shahmukhi uses the same letters
    # as Urdu, so any guess would mislabel some of his Punjabi work. Everything
    # defaults to Urdu and is corrected by hand from the review report, which
    # lists every piece.
    return Piece(
        kind=segment.kind,
        slug=_cap_slug(slugify(segment.title)),
        title=segment.title,
        language="urdu",
        script="nastaliq",
        published=None,                    # unknown for book-sourced pieces
        body=segment.body,
        extra={
            "source_book": book_slug,
            "book_order": segment.order,
            "written_note": segment.written_note,
        },
    )


def _write_piece(piece: Piece, root: Path) -> Path:
    directory = root / piece.kind
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{piece.slug}.md"
    body = f"---\n{frontmatter(piece)}\n---\n\n{piece.body}\n"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return path


def write_segment(segment: Segment, book_slug: str, root: Path) -> Path:
    """Write one segment to <root>/<kind>/<slug>.md."""
    piece = _piece(segment, book_slug)
    return _write_piece(piece, root)


def resolve_slugs(segments: list[Segment]) -> tuple[list[str], list[str]]:
    """Resolve the on-disk slug for every segment, in order.

    Two segments whose titles slugify to the same string would otherwise
    overwrite each other in staging, silently dropping a poem before
    `promote` ever sees it. The first keeps its natural slug; later
    collisions are disambiguated to `<slug>-N`, with a problem naming the
    colliding titles so a human can resolve it. Order is taken from the
    input list, so re-running on the same segments is deterministic.

    This is the single source of truth for "what slug does segment i get" —
    `write_segments` uses it to name the files it writes, `write_book` uses
    it to name the same pieces in the book record, and `promote` uses it to
    find those files again in staging. Any of those recomputing the slug
    independently could silently disagree with the others on a collision.
    """
    problems: list[str] = []
    slugs: list[str] = []
    slug_counts: dict[str, int] = {}
    first_title_for_slug: dict[str, str] = {}
    for segment in segments:
        base_slug = _cap_slug(slugify(segment.title))
        count = slug_counts.get(base_slug, 0)
        slug_counts[base_slug] = count + 1
        if count == 0:
            first_title_for_slug[base_slug] = segment.title
            slugs.append(base_slug)
        else:
            slug = f"{base_slug}-{count + 1}"
            problems.append(
                f'slug collision: "{first_title_for_slug[base_slug]}" and '
                f'"{segment.title}" both slugify to "{base_slug}" — wrote the '
                f'second as {slug}.md'
            )
            slugs.append(slug)
    return slugs, problems


def write_segments(
    segments: list[Segment], book_slug: str, root: Path
) -> tuple[list[Path], list[str], list[str]]:
    """Write every segment to <root>/<kind>/<slug>.md.

    Returns (written paths, resolved slugs, problems) — the slugs are
    positional, parallel to `segments`, so a caller (`write_book`, `promote`)
    can pair each segment with the slug it actually got on disk instead of
    re-deriving one independently. See `resolve_slugs`.
    """
    slugs, problems = resolve_slugs(segments)
    written: list[Path] = []
    for segment, slug in zip(segments, slugs):
        piece = _piece(segment, book_slug)
        piece.slug = slug
        written.append(_write_piece(piece, root))
    return written, slugs, problems


def write_book(book: Book, slugs: list[str], root: Path) -> Path:
    """Write one book record to <root>/books/<slug>.yaml.

    `slugs` must be the resolved slugs for `book.contents`, positional and
    in the same order (as returned by `write_segments`) — recomputing them
    here independently would silently disagree with `write_segments` on a
    slug collision, listing one slug twice and orphaning the other from the
    book record.
    """
    directory = root / "books"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{book.slug}.yaml"
    lines = [f'title: "{book.title}"', f'slug: "{book.slug}"']
    if book.publisher:
        lines.append(f'publisher: "{book.publisher}"')
    if book.year is not None:
        lines.append(f"year: {book.year}")
    if book.volume_of:
        lines.append(f'volume_of: "{book.volume_of}"')
    lines.append("contents:")
    for segment, slug in zip(book.contents, slugs):
        section = f' section: "{segment.section}",' if segment.section else ""
        lines.append(
            f'  - {{{section} kind: "{segment.kind}", slug: "{slug}" }}'
        )
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    return path
