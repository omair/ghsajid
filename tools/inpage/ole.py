"""Read the text stream out of an InPage (.inp) file.

.inp files are OLE2 compound files (Microsoft structured storage, magic
D0CF11E0A1B11AE1) — the same container legacy .doc used. The document text
lives in a stream named InPage100; two fixed 5 MB PPicts streams hold picture
scratch and account for almost all of a file's size.

This module uses `olefile` rather than parsing the container by hand. The book
files are 11-14 MB, which pushes the FAT past the 109 sectors addressable from
the header into DIFAT chaining — correctness risk with no upside. olefile is
pure Python with no transitive dependencies.
"""

from pathlib import Path

import olefile

TEXT_STREAM = "InPage100"


class MissingStreamError(Exception):
    """The file is not a compound file, or carries no InPage text stream."""


def read_text_stream(path: Path) -> bytes:
    """Return the raw bytes of the InPage100 stream in `path`."""
    if not olefile.isOleFile(str(path)):
        raise MissingStreamError(f"{path} is not an OLE2 compound file")
    ole = olefile.OleFileIO(str(path))
    try:
        if not ole.exists(TEXT_STREAM):
            raise MissingStreamError(f"{path} has no {TEXT_STREAM} stream")
        return ole.openstream(TEXT_STREAM).read()
    finally:
        ole.close()
