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
MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
SOURCE_IMAGE = re.compile(r'<img[^>]*\bsrc="([^"]+)"', re.I)

VERSE_KINDS = {"ghazals", "nazms"}


def normalized(text: str) -> str:
    """Reduce text to comparable content: no markup, tatweel, or whitespace."""
    text = BLOCK_COMMENT.sub("", text)
    text = MARKDOWN_IMAGE.sub(" ", text)
    text = TAG.sub(" ", text)
    text = htmllib.unescape(text).replace("\xa0", " ")
    text = strip_tatweel(text)
    return WHITESPACE.sub("", text)


def media_errors(post: Post, piece: Piece) -> list[str]:
    """Confirm every photograph in the source survived into the piece.

    This gate exists because the fidelity check cannot see it: `normalized`
    strips markup, and an <img> contributes no text characters, so dropping
    every photograph in the corpus leaves the character counts identical.
    That is exactly what happened — 22 photographs across 13 memoir parts
    were silently discarded while all other checks reported success.
    """
    source = SOURCE_IMAGE.findall(strip_embeds(post.body))
    emitted = MARKDOWN_IMAGE.findall(piece.body)
    if len(source) != len(emitted):
        return [
            f"media mismatch in {piece.kind}/{piece.slug}: "
            f"source has {len(source)} image(s), emitted {len(emitted)}"
        ]
    return []


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
