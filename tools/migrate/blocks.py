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


def to_markdown(html: str, *, is_verse: bool) -> str:
    """Convert block HTML to markdown under the project's verse convention.

    Newline = new misra, blank line = new sher.
    """
    html = BLOCK_COMMENT.sub("", html)
    paras = [_clean(p) for p in PARAGRAPH.findall(html)]
    paras = [p for p in paras if p]
    if not paras:
        return ""

    if is_verse and not any("\n" in p for p in paras):
        # Punjabi shape: every paragraph holds a single line of one stanza.
        return "\n".join(paras)

    return "\n\n".join(paras)
