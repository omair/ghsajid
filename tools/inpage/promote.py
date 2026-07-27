"""Move approved staging output into content/.

This is the only module that writes to content/. It refuses to act on an
unapproved or stale report, and it never overwrites a piece that is already
in the archive — an existing poem keeps its slug, URL, date and published_in,
and any textual difference is reported for a human to judge.
"""

import json
import shutil
from pathlib import Path

from .emit import resolve_slugs
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

    # Drive the copy loop from segments.json — the thing the approval gate
    # actually bound its hash to — never from whatever files happen to sit
    # in staging. A book re-segmented after a first pass (2 pieces staged,
    # then re-run down to 1) leaves the first run's orphan .md file on disk;
    # rglob would promote it even though no approved report ever described
    # it. Only a piece this segmentation names may be copied, and only if it
    # is actually present — its absence is a problem, not a silent skip.
    slugs, _ = resolve_slugs(segments)

    written: list[Path] = []
    problems: list[str] = []
    for segment, slug in zip(segments, slugs):
        if segment.kind not in KNOWN_KINDS:
            problems.append(
                f"unexpected kind {segment.kind!r} for piece {slug!r}, skipped "
                f"(expected one of {sorted(KNOWN_KINDS)})"
            )
            continue
        source = book_staging / segment.kind / f"{slug}.md"
        if not source.exists():
            problems.append(
                f"named in segments.json but missing from staging: {source}"
            )
            continue
        target = content / segment.kind / f"{slug}.md"
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
