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
    paras = [_clean(p) for p in PARAGRAPH.findall(html)]
    paras = [p for p in paras if p]
    if not paras:
        return ""

    if is_verse and not any("\n" in p for p in paras):
        # Punjabi shape: every paragraph holds a single line of one stanza.
        return "\n".join(paras)

    return "\n\n".join(paras)
