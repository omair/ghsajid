"""Write pieces to markdown, the container to YAML, and the redirect map.

Frontmatter is rendered by hand rather than with PyYAML to keep the package
stdlib-only. Every string value is quoted and embedded quotes are doubled,
which is valid YAML.
"""

import json
from pathlib import Path

from .models import Piece

# Order matters: this is what a human sees at the top of every file.
FIELD_ORDER = [
    "reviewed_book", "reviewed_author", "source", "url", "video_id",
    "recorded", "description", "written_note", "published_in", "part",
    "source_book", "book_order",
]


def _quote(value) -> str:
    """Render a YAML double-quoted scalar.

    YAML double-quoted scalars use JSON string syntax — backslash escapes,
    not the doubled quotes of the single-quoted style — so json.dumps is
    exactly right and handles quotes, backslashes and control characters.
    """
    return json.dumps(str(value), ensure_ascii=False)


def _render(key: str, value) -> str | None:
    if value in ("", None, [], {}):
        return None
    if isinstance(value, list):
        return f"{key}: [" + ", ".join(_quote(v) for v in value) + "]"
    if isinstance(value, int):
        return f"{key}: {value}"
    return f"{key}: {_quote(value)}"


def frontmatter(piece: Piece) -> str:
    """Render YAML frontmatter for a piece."""
    lines = [
        f"title: {_quote(piece.title)}",
        f"slug: {_quote(piece.slug)}",
        f"language: {_quote(piece.language)}",
        f"script: {_quote(piece.script)}",
    ]
    # Book-sourced pieces have no publication date of their own — only the
    # book's year, which is a different fact — and set published=None to say
    # so; that case is omitted. A WordPress-sourced piece with published=""
    # is a different situation (the export had no date in a field that
    # normally has one) and must still render, loudly failing the Astro
    # build rather than silently shipping a dateless piece.
    if piece.published is not None:
        lines.append(f"published: {piece.published}")
    tags = _render("tags", piece.tags)
    if tags:
        lines.append(tags)
    for key in FIELD_ORDER:
        rendered = _render(key, piece.extra.get(key))
        if rendered:
            lines.append(rendered)
    return "\n".join(lines)


def write_piece(piece: Piece, root: Path) -> Path:
    """Write one piece to <root>/<kind>/<slug>.md."""
    path = root / piece.kind / f"{piece.slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = piece.body.strip()
    # newline="\n" so the corpus is byte-identical whichever OS regenerates it;
    # without it Python rewrites every file with CRLF on Windows.
    path.write_text(
        f"---\n{frontmatter(piece)}\n---\n\n{body}\n", encoding="utf-8", newline="\n"
    )
    return path


def write_container(pieces: list[Piece], root: Path) -> Path:
    """Write the dars-gah container, parts in reading order."""
    ordered = sorted(pieces, key=lambda p: p.extra["part"])
    path = root / "containers" / "dars-gah.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        'title: "درس گاہ"',
        'slug: "dars-gah"',
        'description: "ایک خودنوشت"',
        "contents:",
    ]
    lines += [f'  - "{p.slug}"' for p in ordered]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def write_postmap(redirects: dict[int, str], path: Path) -> None:
    """Write {post_id: url} as JSON for the Pages Function."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {str(k): v for k, v in sorted(redirects.items())}
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
