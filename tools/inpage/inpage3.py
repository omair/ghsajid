"""Decode an InPage 3.x document.

InPage 3 abandoned the codepage. Where InPage 1 stored text as
`(font_selector, char_code)` byte pairs against a ~132-entry table, InPage 3
stores plain UTF-16LE — so `codepage.py` has no part to play here, and none
of the mapping work that format needed applies.

Established by known-plaintext: اِعادہ was published on its own AND gathered
into کلیات جلد ۲, so its opening lines were already in the archive. Encoded
under each candidate encoding and searched for in the stream, UTF-16LE hit
on every probe; the codepage's own byte sequences hit on none.

What the format gives up, and what it gives back:

  * There is no geometry. InPage 1 wrote a 4-byte record after every
    paragraph mark, and `geometry == 1` is how `pair_shers` knows a line is a
    second misra. InPage 3's paragraph mark is a bare `\\r` with nothing
    after it.
  * In exchange the structure is explicit, and better. A sher is two lines;
    shers are separated by an EMPTY paragraph; poems are separated by a run
    of empties around an `O` ornament. InPage 1 gave none of that — poem
    boundaries there have to be inferred from rhyme.

So this module reads the explicit structure and synthesises the geometry the
rest of the pipeline expects, which lets `classify`, `segment` and every gate
work unchanged on a book from either format.

Digits survive, which matters more than it sounds. InPage 1 keeps them out of
the text stream, so every page number, date and count in a book's own فہرست
is lost before decoding begins — the reason جلد ۱'s index had to be
photographed. An InPage 3 book carries its فہرست, its publication year and
its ISBN in readable text.
"""

from __future__ import annotations

import olefile

from .models import Paragraph

STREAM = "InPage300"

# The paragraph mark, as in InPage 1 — the one thing the two formats share.
PARAGRAPH = "\r"

# What `pair_shers` reads as a second misra. Synthesised here from the blank
# line InPage 3 uses instead, so a book from either format pairs identically.
SECOND_MISRA = 1
FIRST_MISRA = 63

# The ornament InPage 3 sets between poems. Mapped to the ۰۰۰ separator the
# classifier already knows rather than introducing a second spelling of the
# same idea — both mean "a piece ends here".
ORNAMENT = "O"
SEPARATOR_TEXT = "۰۰۰"

# A code unit that can plausibly belong to running text: the Arabic block and
# its presentation forms, ASCII, and the paragraph mark. Used to find where
# the text lives, because the stream interleaves it with formatting records
# and an offset table.
def _is_text(unit: int) -> bool:
    return (
        0x0600 <= unit <= 0x06FF     # Arabic, which Urdu is written in
        or 0xFB50 <= unit <= 0xFEFF  # Arabic presentation forms
        or unit in (0x0D, 0x09)      # paragraph mark, tab
        or 0x20 <= unit <= 0x7E      # ASCII: digits, ISBN, publisher's Latin
    )


# How texty a window must be before it counts as running text. The formatting
# records are dominated by 0x00 and structural bytes and score near zero; the
# text regions of اِعادہ score 0.9+. Measured, not tuned: there is nothing
# between 0.1 and 0.85 in that book.
TEXT_DENSITY = 0.5

# Code units per window. Small enough to find the edges of a text region
# closely, large enough that a stanza break does not read as its end.
WINDOW = 256

# How many consecutive non-text code units end the walk outward from a hot
# window's edge. Urdu text carries short non-text runs — a tab, a stretch of
# ASCII in the imprint — and stopping at the first would clip the text as
# badly as the window did.
EDGE_GAP = 8


def text_region(data: bytes) -> tuple[int, int]:
    """Byte bounds of the document's text, as `(start, end)`.

    The stream is an offset table, then formatting records, then text, then
    more records. Rather than parse a container format that is not
    documented, the text is found by what it looks like — a long run of code
    units that are Arabic, ASCII or a paragraph mark.
    """
    units = len(data) // 2
    hot: list[int] = []
    for start in range(0, units, WINDOW):
        window = range(start, min(start + WINDOW, units))
        texty = sum(
            1 for i in window
            if _is_text(data[2 * i] | (data[2 * i + 1] << 8))
        )
        if texty / max(1, len(window)) >= TEXT_DENSITY:
            hot.append(start)
    if not hot:
        return 0, 0

    # A window is a blunt edge: the first and last land mid-sentence, which
    # cost اِعادہ its opening epigraph and the closing lines of its last
    # ghazal. Walk outward from them one code unit at a time and stop only at
    # a real run of non-text, so the bounds sit where the text actually ends.
    def edge(start: int, step: int) -> int:
        at, gap = start, 0
        while 0 <= at < units and gap < EDGE_GAP:
            unit = data[2 * at] | (data[2 * at + 1] << 8)
            gap = 0 if _is_text(unit) else gap + 1
            at += step
        return at - step * gap

    return max(0, edge(hot[0], -1) + 1) * 2, min(
        edge(hot[-1] + WINDOW - 1, 1) * 2, len(data)
    )


def read_text(path) -> str:
    """The document's text, decoded."""
    ole = olefile.OleFileIO(path)
    try:
        if not ole.exists(STREAM):
            raise MissingInPage3Stream(f"{path} has no {STREAM} stream")
        data = ole.openstream(STREAM).read()
    finally:
        ole.close()
    start, end = text_region(data)
    return data[start:end].decode("utf-16-le", "replace")


class MissingInPage3Stream(Exception):
    """Raised when the file is not an InPage 3 document."""


def decode(data_or_text) -> list[Paragraph]:
    """Paragraphs from an InPage 3 stream, with geometry synthesised.

    A blank paragraph is InPage 3's sher boundary. It is consumed rather than
    emitted: the pair either side of it is what the rest of the pipeline
    calls a sher, and it reads that from `geometry`, not from blank lines.

    The `O` ornament becomes the ۰۰۰ separator the classifier already
    understands — the same statement in a different hand.
    """
    text = (
        data_or_text
        if isinstance(data_or_text, str)
        else data_or_text.decode("utf-16-le", "replace")
    )
    lines = [line.strip() for line in text.split(PARAGRAPH)]

    paragraphs: list[Paragraph] = []
    # Position within the current sher: the line after a blank opens one.
    opening = True
    for line in lines:
        if not line:
            opening = True
            continue
        if line == ORNAMENT:
            paragraphs.append(
                Paragraph(
                    text=SEPARATOR_TEXT, geometry=0,
                    raw=SEPARATOR_TEXT, codes=[],
                )
            )
            opening = True
            continue
        paragraphs.append(
            Paragraph(
                text=line,
                geometry=FIRST_MISRA if opening else SECOND_MISRA,
                raw=line,
                codes=[],
            )
        )
        opening = not opening
    return paragraphs
