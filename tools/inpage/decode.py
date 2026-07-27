"""Turn the InPage100 byte stream into paragraphs of Unicode text.

The stream interleaves text with layout records. Text is a run of
(0x04, char_code) pairs; a paragraph ends at 0x0D followed by four
little-endian bytes of geometry. Everything else is a layout record and is
stepped over two bytes at a time, matching the pair alignment of the stream.

Each paragraph's text is NFC-normalized (InPage writes bearer and combining
mark as separate codes; NFC folds them into the single precomposed
character) and has its digit runs reversed (see `_reverse_digit_runs`), and
is dropped entirely if none of its codes maps to a character (a layout
record wrongly admitted as a text run).
"""

import struct
import unicodedata

from .codepage import decode_byte
from .models import Paragraph

TEXT_FONT = 0x04
PARA_MARK = 0x0D
GEOMETRY_WIDTH = 4

DIGITS = set("۰۱۲۳۴۵۶۷۸۹")


def _reverse_digit_runs(chars: list[str], codes: list[int]) -> None:
    """Reverse each maximal run of digit characters, in place.

    InPage stores digit runs left-to-right inside right-to-left text, so a
    year like 1985 is stored (and, before this fix, decoded) as ۵۸۹۱ — the
    codepage's byte-to-digit mapping is correct, only the assembly order is
    reversed. A single digit is unaffected; non-digit characters keep their
    position.

    `codes` is reversed in lockstep with `chars` so `codes[i]` always still
    decodes to `chars[i]`: gate B re-encodes `raw` from `codes`, and that only
    holds if the two stay aligned after reordering.
    """
    n = len(chars)
    i = 0
    while i < n:
        if chars[i] in DIGITS:
            j = i + 1
            while j < n and chars[j] in DIGITS:
                j += 1
            if j - i > 1:
                chars[i:j] = chars[i:j][::-1]
                codes[i:j] = codes[i:j][::-1]
            i = j
        else:
            i += 1


def decode(data: bytes) -> list[Paragraph]:
    """Decode `data` into paragraphs, dropping empty ones."""
    paragraphs: list[Paragraph] = []
    chars: list[str] = []
    codes: list[int] = []
    index = 0

    def flush(geometry: int) -> None:
        if not any(decode_byte(code) is not None for code in codes):
            # Nothing in this run maps to a character at all — a layout
            # record the walker admitted as text, not real content. A
            # paragraph with even one mapped code is real text and is kept
            # below, however sparse.
            chars.clear()
            codes.clear()
            return

        _reverse_digit_runs(chars, codes)

        # InPage writes a combining mark after its bearer — alef then madda for
        # آ, gol he then hamza for ۂ. NFC folds those canonical sequences into
        # the single characters the rest of the archive is written in.
        raw = unicodedata.normalize("NFC", "".join(chars))
        paragraphs.append(Paragraph(
            text=raw.strip(), geometry=geometry, raw=raw, codes=list(codes),
        ))
        chars.clear()
        codes.clear()

    while index < len(data) - 1:
        lead = data[index]
        if lead == TEXT_FONT:
            code = data[index + 1]
            codes.append(code)
            chars.append(decode_byte(code) or "")
            index += 2
        elif lead == PARA_MARK:
            end = index + 1 + GEOMETRY_WIDTH
            geometry = struct.unpack("<I", data[index + 1:end])[0] if end <= len(data) else 0
            flush(geometry)
            index = end
        else:
            index += 2

    flush(0)
    return [p for p in paragraphs if p.text]


def all_codes(data: bytes) -> list[int]:
    """Every text char code in the stream, in order."""
    return [code for para in decode(data) for code in para.codes]
