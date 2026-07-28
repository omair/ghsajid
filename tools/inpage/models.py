"""Data carried between InPage ingestion stages."""

from dataclasses import dataclass, field

# The kinds whose bodies are verse. Lives here rather than in checks.py so
# report.py can use it without importing the whole gate module for one
# constant — it is a property of a Segment's kind, not of any single gate.
VERSE_KINDS = {"ghazals", "nazms"}


@dataclass
class Paragraph:
    """One paragraph of decoded text plus the record that terminated it.

    `text` is stripped for display and comparison. `raw` is NOT stripped, and
    gate B must use it: `codes` still holds the leading and trailing space
    codes, so round-tripping against the stripped text would report a failure
    on every indented line in the corpus.
    """

    text: str
    geometry: int          # line position from the paragraph mark, not a style id
    raw: str = ""          # unstripped — the only thing gate B may compare
    codes: list[int] = field(default_factory=list)   # raw codes, for gate B


@dataclass
class Segment:
    """One candidate piece found inside a book."""

    kind: str                       # ghazals | nazms | reviews
    title: str
    body: str
    order: int
    section: str = ""
    written_note: str = ""          # date and place, verbatim from the source
    flags: list[str] = field(default_factory=list)


@dataclass
class Book:
    """One book record."""

    title: str
    slug: str
    publisher: str = ""
    year: int | None = None
    volume_of: str = ""
    contents: list[Segment] = field(default_factory=list)
