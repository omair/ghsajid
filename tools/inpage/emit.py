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


def write_segment(segment: Segment, book_slug: str, root: Path) -> Path:
    """Write one segment to <root>/<kind>/<slug>.md."""
    piece = _piece(segment, book_slug)
    directory = root / piece.kind
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{piece.slug}.md"
    body = f"---\n{frontmatter(piece)}\n---\n\n{piece.body}\n"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return path


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
