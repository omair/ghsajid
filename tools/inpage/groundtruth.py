"""Validate the codepage against poems that reached the site independently.

11 of the 21 ghazals in content/ghazals/ also appear in the کلیات volumes.
They were migrated from WordPress — a completely separate path from this
decoder — so they are true ground truth for the byte table.
"""

import re
from pathlib import Path

from .models import Paragraph

GHAZALS = Path("content/ghazals")

# Named explicitly: a renamed or deleted file must fail loudly, not shrink
# the check silently.
KNOWN_GHAZALS: tuple[str, ...] = (
    "agar-farman-roaii-sahab-i-toqir-ka-haq-hai",
    "bian-us-bazm-mein-meri-kahani-ho-rahi-hai",
    "chalne-laga-hai-phir-se-mira-dil-ruka-hoa",
    "dikhe-ghalat-kaha-koi-soche-ghalat-kaha",
    "garadash-i-jam-kahin-garadash-i-mina-sakat",
    "hanas-raha-hai-jo-mari-halat-pah-jane-kaun-hai",
    "ishq-se-aur-kar-dania-se-hazar-karta-hun-mein",
    "jahan-bhar-mein-mare-dil-sa-koi-gahar-ho-nahin-sakta",
    "jahan-mein-dalte-rahte-hain-masioa-ki-tarah",
    "maoraie-saragh-hun-main-bhi",
    "ninad-warasah-hai-mira-khwab-amanat-hai-mari",
)

URDU_LETTERS = "ابپتٹثجچحخدڈذرڑزژسشصضطظعغفقکگلمنںوئیےہھآءۂۓؤۃ"
NOT_LETTER = re.compile(f"[^{URDU_LETTERS}\\s]")
WHITESPACE = re.compile(r"\s+")

# Committed floor, raised deliberately: the site text and the printed کلیات
# are genuinely different editions (site-only provenance blocks, InPage
# typesetting conventions, misras run together, real textual variants), so
# gate C asserts a measured baseline instead of verbatim reproduction. A
# wrong codepage entry breaks hundreds of lines at once and still fails
# hard; editorial variance between editions does not raise a false alarm.
MIN_LINES_MATCHED = 139
# Exact canary, not a floor: if the ground-truth corpus changes size at all,
# that is a deliberate event (a slug added/removed, lines re-split) requiring
# a look, not a silent pass. Do not treat this like MIN_LINES_MATCHED.
EXPECTED_LINES_TOTAL = 169
MIN_WHOLE_GHAZALS = 1


def skeleton(text: str) -> str:
    """Reduce text to letters and single spaces — the tier that must match."""
    return WHITESPACE.sub(" ", NOT_LETTER.sub("", text)).strip()


def site_text(slug: str) -> str:
    """The committed body of a ghazal already on the site."""
    raw = (GHAZALS / f"{slug}.md").read_text(encoding="utf-8")
    return raw.split("---", 2)[2]


def find_in(paragraphs: list[Paragraph], want: str) -> str | None:
    """Return the matching decoded run, or None if the skeleton is absent."""
    haystack = skeleton(" ".join(p.text for p in paragraphs))
    return want if want and want in haystack else None


def line_match_report(paragraphs: list[Paragraph], slugs: tuple[str, ...] = KNOWN_GHAZALS) -> dict[str, list[bool]]:
    """Per-line match results for each known ghazal, in ground-truth order.

    Splits each ghazal's committed body into its non-blank lines and checks
    each one's skeleton against the decoded corpus independently, so gate C
    can report line-level and whole-ghazal counts instead of an all-or-nothing
    verdict per slug.
    """
    haystack = skeleton(" ".join(p.text for p in paragraphs))
    report = {}
    for slug in slugs:
        lines = [line for line in site_text(slug).splitlines() if skeleton(line)]
        report[slug] = [skeleton(line) in haystack for line in lines]
    return report


def corpus_lexicon() -> set[str]:
    """Every word already in the archive — the wordlist for gate D.

    Better than a general Urdu dictionary: it is this poet's own vocabulary,
    needs no dependency, and grows as the archive does. A wrong codepage entry
    shows up as a *cluster* of related outliers rather than one odd word.
    """
    words: set[str] = set()
    for path in Path("content").rglob("*.md"):
        body = path.read_text(encoding="utf-8").split("---", 2)[-1]
        words.update(skeleton(body).split())
    return words
