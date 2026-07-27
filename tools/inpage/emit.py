"""Write segmented pieces and book records to the staging tree."""

from pathlib import Path

from tools.migrate.emit import frontmatter
from tools.migrate.models import Piece
from tools.migrate.urdu import slugify

from .models import Book, Segment


def _piece(segment: Segment, book_slug: str) -> Piece:
    # Language is NOT auto-detected. Punjabi in Shahmukhi uses the same letters
    # as Urdu, so any guess would mislabel some of his Punjabi work. Everything
    # defaults to Urdu and is corrected by hand from the review report, which
    # lists every piece.
    return Piece(
        kind=segment.kind,
        slug=slugify(segment.title),
        title=segment.title,
        language="urdu",
        script="nastaliq",
        published="",                     # unknown for book-sourced pieces
        body=segment.body,
        extra={"source_book": book_slug, "book_order": segment.order},
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


def write_segments(
    segments: list[Segment], book_slug: str, root: Path
) -> tuple[list[Path], list[str]]:
    """Write every segment to <root>/<kind>/<slug>.md.

    Two segments whose titles slugify to the same string would otherwise
    overwrite each other in staging, silently dropping a poem before
    `promote` ever sees it. Both are written here: the first under its
    natural slug, later collisions under a disambiguated `<slug>-N.md`, with
    a problem naming the colliding titles so a human can resolve it. Order
    is taken from the input list, so re-running on a fresh staging
    directory is deterministic.
    """
    written: list[Path] = []
    problems: list[str] = []
    slug_counts: dict[str, int] = {}
    first_title_for_slug: dict[str, str] = {}
    for segment in segments:
        base_slug = slugify(segment.title)
        count = slug_counts.get(base_slug, 0)
        slug_counts[base_slug] = count + 1
        piece = _piece(segment, book_slug)
        if count == 0:
            first_title_for_slug[base_slug] = segment.title
        else:
            piece.slug = f"{base_slug}-{count + 1}"
            problems.append(
                f'slug collision: "{first_title_for_slug[base_slug]}" and '
                f'"{segment.title}" both slugify to "{base_slug}" — wrote the '
                f'second as {piece.slug}.md'
            )
        written.append(_write_piece(piece, root))
    return written, problems


def write_book(book: Book, root: Path) -> Path:
    """Write one book record to <root>/books/<slug>.yaml."""
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
    for segment in book.contents:
        section = f' section: "{segment.section}",' if segment.section else ""
        lines.append(
            f'  - {{{section} kind: "{segment.kind}", slug: "{slugify(segment.title)}" }}'
        )
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    return path
