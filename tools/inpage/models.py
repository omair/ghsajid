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
    # True only when the book has a section heading inside its body AND this
    # piece comes before it. باغِ نشاط's epigraph couplet is the case: it is
    # a real, correctly segmented poem, but it sits before the first heading
    # and its فہرست never numbered it. Recorded as a position rather than
    # read back off `section`, because `section` can legitimately be cleared
    # (see checks.clear_unverifiable_sections) and the count gate must not
    # move when it is.
    precedes_first_heading: bool = False
    # The named collection this piece belongs to, read from the running page
    # header. Distinct from `section`, which is a form heading (غزلیں, نعت)
    # inside a book: کلیات جلد ۲ gathers six separately-published collections,
    # and a poem belongs to one of them regardless of its form.
    collection: str = ""
    written_note: str = ""        # date and place, verbatim from the source
    # A tribute the poet set under a ghazal — (نذرِ غالب), (نذرِ فراقؔ),
    # (نذرِ دردؔ). Bracketed and short, so it paired as a misra and left the
    # poem ending on a half sher that no missing line could explain.
    dedication: str = ""
    # Only for `reviews`: who wrote the criticism, and which book it prefaces.
    # `reviewed_book` is filled by the CLI, which is what knows a book's title;
    # segmentation only ever sees one book's paragraphs.
    reviewed_author: str = ""
    reviewed_book: str = ""
    flags: list[str] = field(default_factory=list)


@dataclass
class Book:
    """One book record."""

    title: str
    slug: str
    publisher: str = ""
    year: int | None = None
    # Which کلیات volume this collection was read from. Provenance, not
    # authorship: کلیات جلد ۲ gathered نیند میں چلتے ہوئے, it did not publish
    # it, and the collection is the book a reader means.
    collected_in: str = ""
    contents: list[Segment] = field(default_factory=list)
