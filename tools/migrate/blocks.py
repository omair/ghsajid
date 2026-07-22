"""Convert Gutenberg block HTML to markdown, preserving verse structure."""

import html as htmllib
import re

from .urdu import strip_tatweel

# Any block whose content is a third-party embed rather than the author's text.
EMBED_BLOCK = re.compile(
    r"<!-- wp:(?:core-embed/[\w-]+|embed|html).*?-->"
    r".*?"
    r"<!-- /wp:(?:core-embed/[\w-]+|embed|html) -->",
    re.S,
)
BLOCK_COMMENT = re.compile(r"<!--.*?-->", re.S)
PARAGRAPH = re.compile(r"<p[^>]*>(.*?)</p>", re.S)
BR = re.compile(r"<br\s*/?>", re.I)
TAG = re.compile(r"<[^>]+>")

# A body is a sequence of paragraphs and photographs. Matching both in one
# pass is what keeps them in document order — 13 memoir parts place a photo
# against the paragraph that describes it, so position carries meaning.
# `wp:image` and `wp:gallery` differ only in wrapping, and both bottom out in
# <img src>, so matching the img directly handles each without special-casing.
NODE = re.compile(r'<p[^>]*>(.*?)</p>|<img[^>]*\bsrc="([^"]+)"[^>]*>', re.S | re.I)

# WordPress serves a downscaled copy ("…_o-1024x601.jpg") while the original
# sits beside it. The archive keeps the original.
WP_RESIZE = re.compile(r"-\d+x\d+(?=\.[A-Za-z0-9]+$)")
# When the same filename is uploaded twice, WordPress appends "-1", "-2" … to
# the second. Some posts reference that re-upload ("…_o-1.jpg") while only the
# original ("…_o.jpg") was archived. They are the same photograph — every image
# in this corpus is a Facebook export named "<ids>_o.jpg" / "…_n.jpg", so a
# trailing "-<n>" before the extension is always a re-upload counter, never
# part of the name — so drop it and resolve to the archived original.
WP_REUPLOAD = re.compile(r"-\d+(?=\.[A-Za-z0-9]+$)")
MEDIA_ROOT = "/media/images/"


def image_path(src: str) -> str:
    """Map a WordPress upload URL to its local original."""
    name = src.rsplit("/", 1)[-1]
    name = WP_RESIZE.sub("", name)
    name = WP_REUPLOAD.sub("", name)
    return f"{MEDIA_ROOT}{name}"


def strip_embeds(html: str) -> str:
    """Remove embed containers and the third-party text inside them.

    Must run before any measurement or extraction of the author's own text:
    Facebook embeds carry a caption written by someone else, and a naive
    "does this post have content?" check would file it as poetry.
    """
    return EMBED_BLOCK.sub("", html)


def _clean(fragment: str) -> str:
    text = BR.sub("\n", fragment)
    text = TAG.sub("", text)
    text = htmllib.unescape(text).replace("\xa0", " ")
    text = strip_tatweel(text)
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


AUTHOR_NAME = "غلام حسین ساجد"
SEPARATOR = re.compile(r"^[-–—_=۔\s]{3,}$")
# "تحریر: غلام حسین ساجد" or the bare name, as a standalone closing line.
BYLINE = re.compile(rf"^(?:تحریر\s*[:؛]?\s*)?{AUTHOR_NAME}$")


def strip_byline(markdown: str) -> tuple[str, list[str]]:
    """Remove a trailing byline from prose.

    Every review closes by naming its author, which is redundant on his own
    site. Only exact byline matches are removed, so a genuine short closing
    paragraph is never mistaken for one.
    """
    paragraphs = [p for p in markdown.split("\n\n") if p.strip()]
    removed: list[str] = []
    while paragraphs and BYLINE.match(paragraphs[-1].strip()):
        removed.append(paragraphs.pop().strip())
    removed.reverse()
    return "\n\n".join(paragraphs), removed


def split_trailing_notes(markdown: str) -> tuple[str, list[str], list[str]]:
    """Separate a ghazal's verse from trailing non-verse lines.

    Some ghazals end with a colophon (date and place of composition), a
    separator rule, or the poet's signature. WordPress rendered these as
    ordinary paragraphs, so they arrive looking like a one-line sher.

    Returns (verse, colophons, removed). `removed` holds every stripped line
    in document order — including the colophons — so the fidelity check can
    reassemble the original text exactly.
    """
    stanzas = [s for s in markdown.split("\n\n") if s.strip()]
    colophons: list[str] = []
    removed: list[str] = []

    while stanzas and "\n" not in stanzas[-1]:
        line = stanzas[-1].strip()
        if not (SEPARATOR.match(line) or line == AUTHOR_NAME):
            colophons.append(line)
        removed.append(line)
        stanzas.pop()

    colophons.reverse()
    removed.reverse()
    return "\n\n".join(stanzas), colophons, removed


def to_markdown(html: str, *, is_verse: bool) -> str:
    """Convert block HTML to markdown under the project's verse convention.

    Newline = new misra, blank line = new sher.
    """
    html = BLOCK_COMMENT.sub("", html)
    nodes: list[str] = []
    for match in NODE.finditer(html):
        paragraph, src = match.group(1), match.group(2)
        if paragraph is not None:
            text = _clean(paragraph)
            if text:
                nodes.append(text)
        else:
            nodes.append(f"![]({image_path(src)})")
    if not nodes:
        return ""

    if is_verse and not any("\n" in n for n in nodes):
        # Punjabi shape: every paragraph holds a single line of one stanza.
        return "\n".join(nodes)

    return "\n\n".join(nodes)
