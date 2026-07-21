"""Merge duplicated posts and record redirects from the discarded ones."""

from .models import Piece

URL_SEGMENT = {
    "ghazals": "ghazal",
    "nazms": "nazm",
    "reviews": "tabsira",
    "videos": "video",
}


def piece_url(piece: Piece) -> str:
    """Public URL for a piece."""
    if piece.kind == "memoir":
        # A container holding a complete ordered work owns its URL space.
        return f"/dars-gah/{piece.extra['part']}"
    return f"/{URL_SEGMENT[piece.kind]}/{piece.slug}"


def _identity(piece: Piece):
    """What makes two pieces the same work.

    Deliberately keyed on title, not on video id: one recording can hold two
    distinct works (an Urdu and a Punjabi piece recited in the same sitting),
    and merging on the shared video would erase one of them.
    """
    return (piece.kind, piece.slug)


def merge_duplicates(pieces: list[Piece]) -> tuple[list[Piece], dict[int, str]]:
    """Keep the first piece of each identity; redirect the rest to it."""
    survivors: dict[tuple, Piece] = {}
    redirects: dict[int, str] = {}

    for piece in pieces:
        key = _identity(piece)
        if key not in survivors:
            survivors[key] = piece
            continue
        winner = survivors[key]
        for pid in piece.source_post_ids:
            redirects[pid] = piece_url(winner)
            winner.source_post_ids.append(pid)

    return list(survivors.values()), redirects
