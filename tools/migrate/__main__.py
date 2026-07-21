"""Run the full migration: data/export.xml -> content/ + worker/."""

import re
import sys
from pathlib import Path

from .blocks import split_trailing_notes, strip_byline, strip_embeds, to_markdown
from .checks import fidelity_errors, media_errors, verse_errors
from .classify import classify
from .dedupe import merge_duplicates, piece_url
from .embeds import extract_published_in, extract_video
from .emit import write_container, write_piece, write_postmap
from .models import Piece, Post
from .urdu import slugify, strip_tatweel
from .wxr import parse_posts

EXPORT = Path("data/export.xml")
CONTENT = Path("content")
POSTMAP = Path("worker/postmap.json")

VERSE_KINDS = {"ghazals", "nazms"}

# Recordings removed by their uploaders and confirmed unrecoverable on
# 2026-07-21 (yt-dlp: "Video unavailable"). No copy was archived in time, so
# these posts would be pages embedding a dead player. Their old ?p= URLs fall
# through to the home page rather than 301ing to a broken embed.
DEAD_VIDEOS = {
    "XH07MYuzuk4": "دھوپ آنگن میں اترنے سے مجھے خوف آیا",
    "0csAYaeSrU0": "پنجیا",
}
# Part 53's title is punctuated "درس گاہ-  53"; tolerate any spacing.
PART_NUMBER = re.compile(r"(\d+)")
REVIEW_TITLE = re.compile(r"^(?P<book>[^/]+)/(?P<author>[^/]+)$")


def _memoir_part(post: Post) -> int:
    match = PART_NUMBER.search(post.title)
    if not match:
        raise ValueError(f"memoir post {post.post_id} has no part number")
    return int(match.group(1))


# Two review titles do not follow "Book / Author". Confirmed with Omair:
# the first names an author whose books the piece never titles; the second
# spells the name ریاظ in the source, corrected here to the conventional ریاض.
REVIEW_OVERRIDES = {
    "کاشف حسین غائر کی دو کتابیں": {"reviewed_author": "کاشف حسین غائر"},
    'ریاظ احمد کا" شجر ِحیات"': {
        "reviewed_author": "ریاض احمد",
        "reviewed_book": "شجر ِحیات",
    },
}


def _review_fields(title: str) -> dict:
    if title in REVIEW_OVERRIDES:
        return dict(REVIEW_OVERRIDES[title])
    match = REVIEW_TITLE.match(title)
    if not match:
        return {}
    return {
        "reviewed_book": match.group("book").strip(),
        "reviewed_author": match.group("author").strip(),
    }


def build_pieces(
    posts: list[Post],
) -> tuple[list[Piece], dict[int, str], dict[int, str]]:
    """Convert every post to a Piece, then merge duplicates.

    Returns (survivors, redirects, relocated_text). The third value maps a
    post id to text moved out of its body, so the fidelity check can still
    account for every character.
    """
    pieces: list[Piece] = []
    removed: dict[int, str] = {}

    for post in posts:
        kind, language, script, tags = classify(post)
        title = strip_tatweel(post.title).strip()
        extra: dict = {}

        if kind == "videos":
            video = extract_video(post.body)
            if video is None:
                raise ValueError(f"post {post.post_id} classified video, has none")
            if video["video_id"] in DEAD_VIDEOS:
                continue
            extra.update(video)
            slug = slugify(title) or f"video-{post.post_id}"
            body = ""
        else:
            body = to_markdown(strip_embeds(post.body), is_verse=kind in VERSE_KINDS)
            if kind == "ghazals":
                # A ghazal is couplets throughout, so any trailing single line
                # is a colophon or signature, not verse.
                body, colophons, removed_lines = split_trailing_notes(body)
                if colophons:
                    extra["written_note"] = " ".join(colophons)
                removed[post.post_id] = "".join(removed_lines)
            elif kind in ("reviews", "memoir"):
                body, removed_lines = strip_byline(body)
                removed[post.post_id] = "".join(removed_lines)
            published_in = extract_published_in(post.body)
            if published_in:
                extra["published_in"] = published_in
            if kind == "memoir":
                part = _memoir_part(post)
                extra["part"] = part
                slug = f"dars-gah-{part}"
            else:
                if kind == "reviews":
                    extra.update(_review_fields(title))
                slug = slugify(title) or f"{kind}-{post.post_id}"

        pieces.append(
            Piece(
                kind=kind, slug=slug, title=title, language=language,
                script=script, published=post.published, body=body,
                tags=tags, source_post_ids=[post.post_id], extra=extra,
            )
        )

    survivors, redirects = merge_duplicates(pieces)
    return survivors, redirects, removed


def main() -> int:
    posts = parse_posts(EXPORT)
    by_id = {p.post_id: p for p in posts}
    survivors, redirects, removed = build_pieces(posts)

    errors: list[str] = []
    for piece in survivors:
        errors += verse_errors(piece)
        if piece.kind != "videos":
            source_id = piece.source_post_ids[0]
            errors += fidelity_errors(
                by_id[source_id], piece, removed.get(source_id, "")
            )
            errors += media_errors(by_id[source_id], piece)

    if errors:
        print(f"{len(errors)} verification failures — nothing written:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    for piece in survivors:
        write_piece(piece, CONTENT)
    write_container([p for p in survivors if p.kind == "memoir"], CONTENT)

    # Every post redirects, not only the merged ones.
    full_map = {
        pid: piece_url(piece)
        for piece in survivors
        for pid in piece.source_post_ids
    }
    write_postmap(full_map, POSTMAP)

    print(f"wrote {len(survivors)} pieces, {len(full_map)} redirects")

    if redirects:
        print("\nMERGED DUPLICATES — confirm the survivor is the right one:")
        for pid, url in redirects.items():
            print(f"  post {pid} ({by_id[pid].title}) -> {url}")

    unparsed = [
        p.title
        for p in survivors
        if p.kind == "reviews" and not p.extra.get("reviewed_author")
    ]
    if unparsed:
        print("\nREVIEW TITLES NEEDING HAND-ENTRY:")
        for title in unparsed:
            print(f"  {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
