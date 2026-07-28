"""The human review report — the gate segmentation must pass.

Segmentation is heuristic, so a person reads this before anything reaches
content/. The approval line is bound to a hash of the segmentation it
describes, so re-running the segmenter invalidates a previous sign-off
instead of silently inheriting it.
"""

import hashlib
import re
from pathlib import Path

from .emit import resolve_slugs
from .models import VERSE_KINDS, Segment

APPROVAL_HEADING = "## Approval"
APPROVED_LINE = re.compile(r"^approved:\s*(true|false)\s*$", re.M)
HASH_LINE = re.compile(r"^segmentation:\s*([0-9a-f]{16})\s*$", re.M)


def _sanitise(text: str) -> str:
    """Collapse embedded newlines so a value cannot forge a new report line."""
    return text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")


ABSENT = "absent"


def _staged_digests(
    staging: Path, book_slug: str, segments: list[Segment]
) -> list[str]:
    """`<relative path>\x1f<sha256 of its bytes>` for everything promote copies.

    Derived from `segments` (via the same `resolve_slugs` the writer and
    `promote` use), never from what happens to be on disk — a directory walk
    would let a file nobody described join the digest, and `promote` refuses
    to copy such a file anyway. A named file that is not there digests as
    `absent`, which is a different value from any content, so staging a piece
    after approval invalidates the approval exactly as editing one does.
    """
    slugs, _ = resolve_slugs(segments)
    relative = [
        f"{segment.kind}/{slug}.md" for segment, slug in zip(segments, slugs)
    ]
    if book_slug:
        relative.append(f"books/{book_slug}.yaml")
    lines = []
    for name in relative:
        path = staging / name
        digest = (
            hashlib.sha256(path.read_bytes()).hexdigest()
            if path.is_file()
            else ABSENT
        )
        lines.append(f"{name}\x1f{digest}")
    return lines


def segmentation_hash(
    segments: list[Segment],
    staging: Path | None,
    book_slug: str,
) -> str:
    """A stable digest of the boundaries this report describes.

    With `staging`, the digest also covers the bytes of every staged file
    `promote` would copy — each piece's .md and the book record named by
    `book_slug`. This is the whole point of the binding: the report describes
    a segmentation, but `promote` copies FILES, and hashing only segments.json
    left the gap where an approved staged file could be edited afterwards and
    promoted with the approval still reading as valid. Digesting the files
    rather than re-rendering them from the segments keeps `emit` the single
    writer of a piece's bytes, and catches an edit to any part of the file —
    frontmatter included — not just to the body a re-render would reproduce.

    `staging` may be None to get the boundary digest alone, but it has NO
    DEFAULT: a caller must say so deliberately. A default would let a future
    caller weaken the binding by omission and never notice — the same shape as
    the bug where `is_approved` took the FIRST regex match in the document and
    a crafted title could forge an approval above the real one.
    """
    lines = [f"{s.order}\x1f{s.kind}\x1f{s.title}\x1f{s.body}" for s in segments]
    if staging is not None:
        lines.extend(_staged_digests(staging, book_slug, segments))
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]


def render(
    book_slug: str,
    segments: list[Segment],
    gate_output: list[str],
    staging: Path | None,
) -> str:
    """Render the review report for one book.

    `staging` must be the book's staging directory, already written, so the
    stamped hash covers the staged bytes as well as the boundaries. See
    `segmentation_hash`.
    """
    flagged = [s for s in segments if s.flags]
    lines = [
        f"# Review report — {book_slug}",
        "",
        f"{len(segments)} pieces detected, {len(flagged)} flagged.",
        "",
        "## Gate output",
        "",
    ]
    lines.extend(f"- {_sanitise(line)}" for line in gate_output or ["all gates clean"])
    lines.extend(["", "## Pieces", ""])
    for s in segments:
        units = len([b for b in s.body.split("\n\n") if b.strip()])
        # Print the kind, and count prose in paragraphs rather than shers.
        # The line used to show only [section] — the last heading seen — so a
        # reviews piece displayed as [غزلیں] and a 3358-character essay read
        # as "2 sher". A reviewer could not tell prose from a ghazal.
        measure = f"{units} sher" if s.kind in VERSE_KINDS else f"{units} para"
        flags = f"  ** {', '.join(s.flags)}" if s.flags else ""
        section = f"[{_sanitise(s.section)}] " if s.section else ""
        title = _sanitise(s.title)[:50]
        lines.append(
            f"{s.order:4d}. {s.kind:<8s} {section}{title}  ({measure}){flags}"
        )
    lines.extend([
        "",
        "## Approval",
        "",
        "Once the boundaries above are correct, change the `approved:` line",
        "below to read exactly `approved: true` — that literal string, nothing",
        "else, is the only value this gate accepts.",
        "Re-running segmentation voids this approval, and so does editing any",
        "staged file — the hash covers the bytes promote will copy. If you",
        "hand-correct a staged file after approval, run",
        "`python -m tools.inpage restamp <book-slug>` to re-baseline the hash",
        "against your correction, then re-approve.",
        "",
        f"segmentation: {segmentation_hash(segments, staging, book_slug)}",
        "approved: false",
        "",
    ])
    return "\n".join(lines)


def restamp_report(
    report_text: str,
    segments: list[Segment],
    staging: Path,
    book_slug: str,
) -> tuple[str, str, str]:
    """Rewrite `report_text`'s `segmentation:` and `approved:` lines in place.

    Used by `restamp` to recover from a legitimate hand-correction to a staged
    piece: that correction rightly voids the old hash, but `segment` would
    destroy the correction by regenerating staging from scratch, and
    `promote` correctly refuses a stale hash. This recomputes the hash over
    the CURRENT staged bytes (never re-segmenting, never touching a staged
    piece) and rewrites only the two lines the approval gate reads.

    Everything else in the report — including any comments a reviewer typed
    in — is preserved byte-for-byte: only the matched `segmentation:` and
    `approved:` spans are replaced, nothing around them.

    `approved:` is forced to `false` regardless of what it said before. A
    correction is a change, and a change must be re-approved — inheriting a
    prior `true` would let a hand-edit slip through unreviewed, defeating the
    whole point of the binding.

    Only the authoritative `## Approval` section is touched (the last such
    heading, and everything after it — the same scope `is_approved` reads),
    so a segment title crafted to contain a fake `segmentation:` or
    `approved:` line earlier in the report cannot be mistaken for the real
    one.

    Returns `(new_report_text, old_hash, new_hash)`. Raises `ValueError` if
    the report has no `## Approval` section, or is missing either line within
    it — same shape of malformed-report guard as `is_approved`.
    """
    heading_at = report_text.rfind(APPROVAL_HEADING)
    if heading_at == -1:
        raise ValueError("report has no ## Approval section to restamp")
    section = report_text[heading_at:]

    stamped_matches = list(HASH_LINE.finditer(section))
    if not stamped_matches:
        raise ValueError("report has no segmentation: line to restamp")
    approved_matches = list(APPROVED_LINE.finditer(section))
    if not approved_matches:
        raise ValueError("report has no approved: line to restamp")

    old_hash = stamped_matches[-1].group(1)
    new_hash = segmentation_hash(segments, staging, book_slug)

    hash_match = stamped_matches[-1]
    new_section = (
        section[: hash_match.start()]
        + f"segmentation: {new_hash}"
        + section[hash_match.end():]
    )

    # Re-find within `new_section`: replacing the hash line above cannot shift
    # the approved line's offset (same-length replacement of a same-shaped
    # line in the common case), but re-matching against the actual current
    # text is correct regardless of length, rather than trusting stale spans.
    approved_matches = list(APPROVED_LINE.finditer(new_section))
    if not approved_matches:
        raise ValueError("report has no approved: line to restamp")
    approved_match = approved_matches[-1]
    new_section = (
        new_section[: approved_match.start()]
        + "approved: false"
        + new_section[approved_match.end():]
    )

    new_text = report_text[:heading_at] + new_section
    return new_text, old_hash, new_hash


def is_approved(
    report_text: str,
    segments: list[Segment],
    staging: Path | None,
    book_slug: str,
) -> bool:
    """True only if the report says approved AND still describes `segments`.

    With `staging`, "still describes" extends to the staged bytes: the piece
    files and the book record must be byte-identical to what was there when
    the report was rendered. `promote` always passes it.

    Only the authoritative `## Approval` section (the last such heading, and
    everything after it) is consulted. Content earlier in the report — e.g. a
    segment title crafted to contain a newline and a spoofed `approved: true`
    line — cannot forge approval, both because it lives outside this section
    and because we take the *last* match within it, not the first.
    """
    heading_at = report_text.rfind(APPROVAL_HEADING)
    if heading_at == -1:
        return False
    section = report_text[heading_at:]

    approved_matches = list(APPROVED_LINE.finditer(section))
    stamped_matches = list(HASH_LINE.finditer(section))
    if not approved_matches or not stamped_matches:
        return False

    approved = approved_matches[-1]
    stamped = stamped_matches[-1]
    expected = segmentation_hash(segments, staging, book_slug)
    return approved.group(1) == "true" and stamped.group(1) == expected
