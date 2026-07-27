"""Turn the InPage100 byte stream into paragraphs of Unicode text.

The stream interleaves text with layout records. Text is a run of
(0x04, char_code) pairs; a paragraph ends at 0x0D followed by four
little-endian bytes of geometry. Everything else is a layout record and is
stepped over two bytes at a time, matching the pair alignment of the stream.
"""

import struct

from .codepage import decode_byte
from .models import Paragraph

TEXT_FONT = 0x04
PARA_MARK = 0x0D
GEOMETRY_WIDTH = 4


def decode(data: bytes) -> list[Paragraph]:
    """Decode `data` into paragraphs, dropping empty ones."""
    paragraphs: list[Paragraph] = []
    chars: list[str] = []
    codes: list[int] = []
    index = 0

    def flush(geometry: int) -> None:
        raw = "".join(chars)
        if raw.strip() or codes:
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
