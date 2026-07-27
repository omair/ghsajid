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


def _split_by_run(pairs: list[tuple[int, int]]) -> tuple[list[int], list[int]]:
    """Split pair codes into (kept, excluded) by run length.

    `pairs` is (byte offset, char code) for every 0x04-led pair the walker saw
    since the last paragraph mark. A code is kept if its run has at least
    `MIN_TEXT_RUN` consecutive pairs, excluded otherwise. Shared by
    `_text_codes` (which keeps the survivors) and `excluded_report` (which
    counts what was thrown away), so the two can never disagree about where a
    run boundary falls.
    """
    kept: list[int] = []
    excluded: list[int] = []
    run: list[int] = []
    previous: int | None = None
    for offset, code in pairs:
        if previous is not None and offset != previous + 2:
            (kept if len(run) >= MIN_TEXT_RUN else excluded).extend(run)
            run = []
        run.append(code)
        previous = offset
    (kept if len(run) >= MIN_TEXT_RUN else excluded).extend(run)
    return kept, excluded


def _text_codes(pairs: list[tuple[int, int]]) -> list[int]:
    """Keep only the codes that belong to a genuine text run.

    Drops runs shorter than `MIN_TEXT_RUN` and codes below `FIRST_CHAR_CODE`;
    both are layout bytes, not characters.
    """
    kept, _ = _split_by_run(pairs)
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


def _walk(data: bytes):
    """Yield (geometry, pairs) once per paragraph boundary in `data`.

    A boundary is a 0x0D mark (whose four trailing bytes are the geometry)
    or the end of the stream (geometry 0, for trailing text with no closing
    mark). `pairs` accumulates every 0x04-led pair seen since the previous
    boundary. `decode` and `excluded_report` both walk through this so they
    see exactly the same run boundaries — they must never diverge, or a
    count of what was excluded could describe a different split than the one
    that actually happened.
    """
    pairs: list[tuple[int, int]] = []
    index = 0
    while index < len(data) - 1:
        lead = data[index]
        if lead == TEXT_FONT:
            pairs.append((index, data[index + 1]))
            index += 2
        elif lead == PARA_MARK:
            end = index + 1 + GEOMETRY_WIDTH
            geometry = struct.unpack("<I", data[index + 1:end])[0] if end <= len(data) else 0
            yield geometry, pairs
            pairs = []
            index = end
        else:
            index += 2
    yield 0, pairs


def decode(data: bytes) -> list[Paragraph]:
    """Decode `data` into paragraphs, dropping empty ones."""
    paragraphs: list[Paragraph] = []
    for geometry, pairs in _walk(data):
        codes = _text_codes(pairs)
        chars = [decode_byte(code) or "" for code in codes]
        if not any(decode_byte(code) is not None for code in codes):
            # Nothing in this run maps to a character at all — a layout
            # record the walker admitted as text, not real content. A
            # paragraph with even one mapped code is real text and is kept
            # below, however sparse.
            continue

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

    return [p for p in paragraphs if p.text]


def all_codes(data: bytes) -> list[int]:
    """Every text char code in the stream, in order."""
    return [code for para in decode(data) for code in para.codes]


def excluded_report(data: bytes) -> tuple[int, int]:
    """Count what `decode`'s run-length filter throws away, and how much of
    it was a character.

    Returns `(isolated_pairs_excluded, decoded_to_a_character)`: the total
    number of (0x04, code) pairs dropped for sitting in a run shorter than
    `MIN_TEXT_RUN`, and how many of those codes `decode_byte` maps to a real
    character rather than being unmapped noise. The exclusion itself is
    correct (see `MIN_TEXT_RUN`'s comment) — this exists so a book whose
    layout happens to split genuine text into short runs shows up as a
    growing second number instead of losing text with no signal anywhere.
    """
    isolated = 0
    mapped = 0
    for _, pairs in _walk(data):
        _, excluded = _split_by_run(pairs)
        isolated += len(excluded)
        mapped += sum(1 for code in excluded if decode_byte(code) is not None)
    return isolated, mapped
