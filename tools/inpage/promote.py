"""Move approved staging output into content/.

This is the only module that writes to content/. It refuses to act on an
unapproved or stale report, and it never overwrites a piece that is already
in the archive — an existing poem keeps its slug, URL, date and published_in,
and any textual difference is reported for a human to judge.
"""

import json
import shutil
from pathlib import Path

from .checks import UNPUBLISHABLE
from .emit import resolve_book_records, resolve_slugs
from .groundtruth import skeleton
from .models import Segment
from .report import is_approved


# The content collections a staged piece may be promoted into. `reviews` is
# here deliberately: a book's critical foreword is real criticism of the
# poet's work, it has its own collection and /tabsira route, and the design
# always intended to capture it. Omitting it silently skipped both books'
# essays on the first real promote. This set guards against a stray directory
# under staging, not against `reviews`.
#
# It is deliberately NOT the same set as `models.VERSE_KINDS`: that one is
# "kinds whose bodies are verse", used for counting poems against the فہرست
# and for what may appear in a book record's contents. A review is
# promotable but is neither a poem nor a contents row.
KNOWN_KINDS = {"ghazals", "nazms", "reviews"}


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

    # The staging directory and the book slug go in too: the approval binds to
    # the BYTES this function is about to copy, not merely to the boundaries
    # segments.json records. Editing an approved staged .md — or the book
    # record, which no hash covered at all — voids the approval.
    if not is_approved(report_text, segments, book_staging, book_slug):
        return [], [
            f"{report_path} is not approved, or the segmentation or a staged "
            f"file changed after approval"
        ]

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
        # Three things a piece can be that are not a poem and not criticism,
        # each detected by its own check and each confirmed by hand against
        # the printed book before being refused here:
        #
        #   the volume's own first-line فہرست, read as three essays
        #   an essay's byline, orphaned into a one-line "poem"
        #   end-of-stream scratch, read as a poem and as an essay
        #
        # All three stay in staging, flagged and named in the report. What
        # they may not do is reach the site.
        refused = [flag for flag in UNPUBLISHABLE if flag in segment.flags]
        if refused:
            problems.append(
                f"flagged {', '.join(refused)}, not published: order "
                f"{segment.order} ({segment.kind}) {slug!r}"
            )
            continue
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

    # Derived from the segments, never globbed. A directory walk copied
    # whatever yaml happened to sit in staging — a file no approval described
    # and, before the hash covered the record's bytes, one whose title and
    # contents rows could be rewritten after sign-off and still promote. The
    # records this book may publish are the ones `resolve_book_records`
    # names — one per collection for a کلیات volume, one named after the book
    # otherwise — and `is_approved` above has already checked their bytes.
    #
    # This addressed exactly `books/<book_slug>.yaml`, which a
    # multi-collection book never writes, and the copy was guarded with no
    # `else`: کلیات جلد ۲'s 561 poems would have landed in content/ with no
    # /kitab page at all, and not one word said about it.
    records, record_problems = resolve_book_records(segments, book_slug)
    problems.extend(record_problems)
    for _, record_slug in records:
        source = book_staging / "books" / f"{record_slug}.yaml"
        if not source.is_file():
            problems.append(
                f"book record named by segments.json but missing from staging: "
                f"{source}"
            )
            continue
        target = content / "books" / source.name
        if target.exists():
            problems.append(
                f"book record already in the archive, skipped: {target.relative_to(content)}"
            )
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        written.append(target)

    # A yaml nothing described is exactly what the hash cannot see: the digest
    # is derived from the segments, so an extra file in staging/books changes
    # no hash and voids no approval. It is never copied — but staying silent
    # about it hid the fact that something had put it there.
    expected = {f"{record_slug}.yaml" for _, record_slug in records}
    books_dir = book_staging / "books"
    if books_dir.is_dir():
        for stray in sorted(books_dir.iterdir()):
            if stray.name not in expected:
                problems.append(
                    f"unexpected file in staging/books, described by nothing and "
                    f"not promoted: {stray}"
                )

    return written, problems
