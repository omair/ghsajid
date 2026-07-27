"""Move approved staging output into content/.

This is the only module that writes to content/. It refuses to act on an
unapproved or stale report, and it never overwrites a piece that is already
in the archive — an existing poem keeps its slug, URL, date and published_in,
and any textual difference is reported for a human to judge.
"""

import json
import shutil
from pathlib import Path

from .groundtruth import skeleton
from .models import Segment
from .report import is_approved


KNOWN_KINDS = {"ghazals", "nazms"}


class _MalformedFrontmatter(Exception):
    """Raised internally when a file lacks the `---` frontmatter fences."""


def _existing_body(path: Path) -> str:
    parts = path.read_text(encoding="utf-8").split("---", 2)
    if len(parts) < 3:
        raise _MalformedFrontmatter(f"malformed frontmatter, cannot compare: {path}")
    return parts[2]


def promote(book_slug: str, staging: Path, content: Path) -> tuple[list[Path], list[str]]:
    """Copy approved pieces into content/. Returns (written, problems)."""
    book_staging = staging / book_slug
    report_path = book_staging / "report.md"
    if not report_path.exists():
        return [], [f"no report at {report_path}"]

    report_text = report_path.read_text(encoding="utf-8")
    segments_path = book_staging / "segments.json"
    if not segments_path.exists():
        return [], [f"no segments.json at {segments_path}"]

    raw = json.loads(segments_path.read_text(encoding="utf-8"))
    segments = [Segment(**item) for item in raw]

    if not is_approved(report_text, segments):
        return [], [f"{report_path} is not approved, or was re-segmented after approval"]

    written: list[Path] = []
    problems: list[str] = []
    for source in sorted(book_staging.rglob("*.md")):
        if source.name == "report.md":
            continue
        kind = source.parent.name
        if kind not in KNOWN_KINDS:
            problems.append(
                f"unexpected staging directory {kind!r} for {source}, skipped "
                f"(expected one of {sorted(KNOWN_KINDS)})"
            )
            continue
        target = content / kind / source.name
        if target.exists():
            try:
                existing_body = _existing_body(target)
                staged_body = _existing_body(source)
            except _MalformedFrontmatter as exc:
                problems.append(str(exc))
                continue
            if skeleton(existing_body) != skeleton(staged_body):
                problems.append(
                    f"text differs from the archive: {target.relative_to(content)} "
                    "— book and site disagree, decide by hand"
                )
            else:
                problems.append(f"already in the archive, skipped: {target.relative_to(content)}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        written.append(target)

    books_staging = book_staging / "books"
    if books_staging.exists():
        for source in sorted(books_staging.glob("*.yaml")):
            target = content / "books" / source.name
            if target.exists():
                problems.append(
                    f"book record already in the archive, skipped: {target.relative_to(content)}"
                )
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            written.append(target)

    return written, problems
