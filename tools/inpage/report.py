"""The human review report — the gate segmentation must pass.

Segmentation is heuristic, so a person reads this before anything reaches
content/. The approval line is bound to a hash of the segmentation it
describes, so re-running the segmenter invalidates a previous sign-off
instead of silently inheriting it.
"""

import hashlib
import re

from .models import Segment

APPROVED_LINE = re.compile(r"^approved:\s*(true|false)\s*$", re.M)
HASH_LINE = re.compile(r"^segmentation:\s*([0-9a-f]{16})\s*$", re.M)


def segmentation_hash(segments: list[Segment]) -> str:
    """A stable digest of the boundaries this report describes."""
    payload = "\n".join(f"{s.order}\x1f{s.kind}\x1f{s.title}\x1f{len(s.body)}" for s in segments)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def render(book_slug: str, segments: list[Segment], gate_output: list[str]) -> str:
    """Render the review report for one book."""
    flagged = [s for s in segments if s.flags]
    lines = [
        f"# Review report — {book_slug}",
        "",
        f"{len(segments)} pieces detected, {len(flagged)} flagged.",
        "",
        "## Gate output",
        "",
    ]
    lines.extend(f"- {line}" for line in gate_output or ["all gates clean"])
    lines.extend(["", "## Pieces", ""])
    for s in segments:
        sher = len([b for b in s.body.split("\n\n") if b.strip()])
        flags = f"  ** {', '.join(s.flags)}" if s.flags else ""
        section = f"[{s.section}] " if s.section else ""
        lines.append(f"{s.order:4d}. {section}{s.title[:50]}  ({sher} sher){flags}")
    lines.extend([
        "",
        "## Approval",
        "",
        "Change `approved` to true once the boundaries above are correct.",
        "Re-running segmentation changes the hash and voids this approval.",
        "",
        f"segmentation: {segmentation_hash(segments)}",
        "approved: false",
        "",
    ])
    return "\n".join(lines)


def is_approved(report_text: str, segments: list[Segment]) -> bool:
    """True only if the report says approved AND still describes `segments`."""
    approved = APPROVED_LINE.search(report_text)
    stamped = HASH_LINE.search(report_text)
    if not approved or not stamped:
        return False
    return approved.group(1) == "true" and stamped.group(1) == segmentation_hash(segments)
