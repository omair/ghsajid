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


def _existing_body(path: Path) -> str:
    return path.read_text(encoding="utf-8").split("---", 2)[2]


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
        target = content / source.parent.name / source.name
        if target.exists():
            if skeleton(_existing_body(target)) != skeleton(_existing_body(source)):
                problems.append(
                    f"text differs from the archive: {target.relative_to(content)} "
                    f"— book and site disagree, decide by hand"
                )
            else:
                problems.append(f"already in the archive, skipped: {target.relative_to(content)}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        written.append(target)

    books_staging = book_staging.parent / "books"
    if books_staging.exists():
        for source in books_staging.glob("*.yaml"):
            target = content / "books" / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            written.append(target)

    return written, problems
