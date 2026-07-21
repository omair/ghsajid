"""Verification gates run at the end of every migration.

Silent text corruption in someone's poetry is the failure mode that matters,
so the migration refuses to write anything if these fail.
"""

import html as htmllib
import re

from .blocks import strip_embeds
from .models import Piece, Post
from .urdu import strip_tatweel

TAG = re.compile(r"<[^>]+>")
BLOCK_COMMENT = re.compile(r"<!--.*?-->", re.S)
WHITESPACE = re.compile(r"\s+")

VERSE_KINDS = {"ghazals", "nazms"}


def normalized(text: str) -> str:
    """Reduce text to comparable content: no markup, tatweel, or whitespace."""
    text = BLOCK_COMMENT.sub("", text)
    text = TAG.sub(" ", text)
    text = htmllib.unescape(text).replace("\xa0", " ")
    text = strip_tatweel(text)
    return WHITESPACE.sub("", text)


def fidelity_errors(post: Post, piece: Piece, extra_text: str = "") -> list[str]:
    """Confirm the author's words survived the conversion intact.

    `extra_text` carries text moved out of the body into frontmatter (or
    deliberately dropped), so relocating a colophon still has to balance.
    """
    source = normalized(strip_embeds(post.body))
    emitted = normalized(piece.body + extra_text)
    if source != emitted:
        return [
            f"text mismatch in {piece.kind}/{piece.slug}: "
            f"source {len(source)} chars, emitted {len(emitted)} chars"
        ]
    return []


def verse_errors(piece: Piece) -> list[str]:
    """Confirm every sher kept both of its misra."""
    if piece.kind not in VERSE_KINDS:
        return []
    errors = []
    stanzas = [s for s in piece.body.split("\n\n") if s.strip()]
    for index, stanza in enumerate(stanzas, start=1):
        lines = [ln for ln in stanza.split("\n") if ln.strip()]
        if len(lines) % 2 and len(stanzas) > 1:
            errors.append(
                f"{piece.kind}/{piece.slug}: sher {index} has {len(lines)} misra"
            )
    return errors
