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
        f"origin: {_quote(piece.origin)}",
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


def _frontmatter_fields(path: Path) -> dict[str, str] | None:
    """Parse a piece file's frontmatter into a flat {key: raw_value} map.

    Returns None unless the file actually opens with a `---` fence: a naive
    split on `---` would otherwise treat body text that merely contains the
    sequence (a stanza rule, say) as frontmatter. Values are returned raw,
    quotes and all; callers strip what they need.
    """
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    # parts[0] is the text before the first `---`; anything non-blank there
    # means the file does not open with a frontmatter fence.
    if len(parts) < 3 or parts[0].strip():
        return None
    fields: dict[str, str] = {}
    for line in parts[1].splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def existing_origin(path: Path) -> str | None:
    """Return the `origin` value in a file's frontmatter, or None.

    None means the file is absent, does not open with frontmatter fences, or
    names no `origin` — anything the generator is free to write. A returned
    "human" is the one value that makes a file off-limits to regeneration.
    """
    fields = _frontmatter_fields(path)
    if fields is None:
        return None
    origin = fields.get("origin")
    return origin.strip().strip('"') if origin is not None else None


def _human_memoir_chapters(root: Path) -> list[tuple[int, str]]:
    """Find (part, slug) for every human-authored memoir chapter on disk.

    A person can add a memoir chapter the WordPress export never had; it is
    stamped origin: "human" and `write_piece` already refuses to overwrite it.
    The container must include it too, or the درس گاہ index would silently drop
    the chapter every time it is regenerated from the export's survivors.
    """
    chapters: list[tuple[int, str]] = []
    memoir_dir = root / "memoir"
    if not memoir_dir.is_dir():
        return chapters
    for path in sorted(memoir_dir.glob("*.md")):
        fields = _frontmatter_fields(path)
        if not fields or fields.get("origin", "").strip('"') != "human":
            continue
        part = fields.get("part")
        if part is None:
            continue
        try:
            chapters.append((int(part), path.stem))
        except ValueError:
            continue
    return chapters


def write_piece(piece: Piece, root: Path) -> Path | None:
    """Write one piece to <root>/<kind>/<slug>.md.

    Returns the path written, or None if a human-authored file already sits
    there: a person's own work is never overwritten by regeneration. The
    caller reports the skip; staying silent about it would hide that the
    generator declined to touch a file it normally owns.
    """
    path = root / piece.kind / f"{piece.slug}.md"
    if existing_origin(path) == "human":
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    body = piece.body.strip()
    # newline="\n" so the corpus is byte-identical whichever OS regenerates it;
    # without it Python rewrites every file with CRLF on Windows.
    path.write_text(
        f"---\n{frontmatter(piece)}\n---\n\n{body}\n", encoding="utf-8", newline="\n"
    )
    return path


def write_container(pieces: list[Piece], root: Path) -> Path:
    """Write the dars-gah container, parts in reading order.

    Built from the passed (tool-authored) pieces plus any human-authored
    memoir chapters already on disk, so regeneration never drops a chapter a
    person added by hand. A slug in both keeps its passed part.
    """
    part_by_slug: dict[str, int] = {p.slug: p.extra["part"] for p in pieces}
    for part, slug in _human_memoir_chapters(root):
        part_by_slug.setdefault(slug, part)
    ordered = sorted(part_by_slug.items(), key=lambda item: item[1])
    path = root / "containers" / "dars-gah.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        'title: "درس گاہ"',
        'slug: "dars-gah"',
        'description: "ایک خودنوشت"',
        "contents:",
    ]
    lines += [f'  - "{slug}"' for slug, _ in ordered]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def write_postmap(redirects: dict[int, str], path: Path) -> None:
    """Write {post_id: url} as JSON for the Pages Function."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {str(k): v for k, v in sorted(redirects.items())}
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
