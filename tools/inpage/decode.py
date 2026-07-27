"""Turn the InPage100 byte stream into paragraphs of Unicode text.

The stream interleaves text with layout records. Text is a run of
(0x04, char_code) pairs; a paragraph ends at 0x0D followed by four
little-endian bytes of geometry. Everything else is a layout record and is
stepped over two bytes at a time, matching the pair alignment of the stream.

Stepping blindly over layout records means the walker also lands on any 0x04
byte that happens to sit at pair alignment *inside* a record — a field id, a
count, half a 32-bit offset — and reads the byte after it as a character.
`_text_codes` throws those away; see its docstring for the measurements that
identify them.

Each paragraph's digit runs are reversed (see `_reverse_digit_runs`), and the
paragraph is dropped entirely if none of its codes maps to a character (a
layout record wrongly admitted as a text run).

Two fields serve two different purposes and must not be conflated:
`Paragraph.raw` holds exactly what `codes` decodes to, with NO normalization
— it exists solely so gate B (`checks.roundtrip_errors`) can re-encode it and
compare against `codes` byte-for-byte. `Paragraph.text` is NFC-normalized
(InPage writes bearer and combining mark as separate codes; NFC folds them
into the single precomposed character, e.g. آ) and then stripped — it is what
everything else compares and displays. NFC-normalizing `raw` would compose
sequences `codes` cannot re-produce (the composed character has no single
code of its own), making gate B fail on every such paragraph.
"""

import struct
import unicodedata

from .codepage import decode_byte
from .models import Paragraph

TEXT_FONT = 0x04
PARA_MARK = 0x0D
GEOMETRY_WIDTH = 4

# A real text run is two or more (0x04, code) pairs at consecutive 2-byte
# offsets. A lone pair is an accidental 0x04 inside a layout record. Measured
# over all four books: 27530 codes sit in runs of length 1 and only 2.0% of
# them decode to anything, while 1.07M codes sit in runs of length >= 2 and
# 99.8% of them decode — two orders of magnitude apart, with nothing in
# between. The surviving short runs are real content (`کتاب`, `شاعر`,
# `ناشر`, `غزلیں`, `مزامیر`, the `۱۔` `۲۔` of a table of contents), which is
# why the cut is at 2 and not higher.
#
# The cut is not free: 556 of the 27530 isolated codes do decode, and a
# handful are real — the `:` after each colophon label sits alone in its own
# table cell, so `شاعر: …` comes out as `شاعر …`. That is 556 characters in
# 1.07 million against 27 thousand records of pure noise, and an isolated pair
# is indistinguishable from a layout byte by construction. Colons inside
# running prose are unaffected; they sit in the same run as their sentence.
MIN_TEXT_RUN = 2

# InPage's character codes start at 0x20 (the space). Anything below that is a
# stream control byte the walker mistook for a character: 0x0D is the paragraph
# mark and 0x04 the font selector, and the rest (0x00, 0x01, 0x03, 0x08, 0x1E)
# occur only inside the scrambled scratch region at the tail of a file, never in
# a paragraph of readable Urdu.
FIRST_CHAR_CODE = 0x20

DIGITS = set("۰۱۲۳۴۵۶۷۸۹")


def _text_codes(pairs: list[tuple[int, int]]) -> list[int]:
    """Keep only the codes that belong to a genuine text run.

    `pairs` is (byte offset, char code) for every 0x04-led pair the walker saw
    since the last paragraph mark. Drops runs shorter than `MIN_TEXT_RUN` and
    codes below `FIRST_CHAR_CODE`; both are layout bytes, not characters.
    """
    kept: list[int] = []
    run: list[int] = []
    previous: int | None = None
    for offset, code in pairs:
        if previous is not None and offset != previous + 2:
            if len(run) >= MIN_TEXT_RUN:
                kept.extend(run)
            run = []
        run.append(code)
        previous = offset
    if len(run) >= MIN_TEXT_RUN:
        kept.extend(run)
    return [code for code in kept if code >= FIRST_CHAR_CODE]


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
    pairs: list[tuple[int, int]] = []
    index = 0

    def flush(geometry: int) -> None:
        codes = _text_codes(pairs)
        pairs.clear()
        chars = [decode_byte(code) or "" for code in codes]
        if not any(decode_byte(code) is not None for code in codes):
            # Nothing in this run maps to a character at all — a layout
            # record the walker admitted as text, not real content. A
            # paragraph with even one mapped code is real text and is kept
            # below, however sparse.
            return

        _reverse_digit_runs(chars, codes)

        # `raw` is exactly what `codes` decodes to — gate B round-trips
        # against this, so it must stay unnormalized.
        raw = "".join(chars)
        # InPage writes a combining mark after its bearer — alef then madda for
        # آ, gol he then hamza for ۂ. NFC folds those canonical sequences into
        # the single characters the rest of the archive is written in. Only
        # `text` gets this treatment; `raw` must not, or gate B could never
        # round-trip a composed sequence.
        text = unicodedata.normalize("NFC", raw).strip()
        paragraphs.append(Paragraph(
            text=text, geometry=geometry, raw=raw, codes=codes,
        ))

    while index < len(data) - 1:
        lead = data[index]
        if lead == TEXT_FONT:
            pairs.append((index, data[index + 1]))
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
