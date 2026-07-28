"""The human review report — the gate segmentation must pass.

Segmentation is heuristic, so a person reads this before anything reaches
content/. The approval line is bound to a hash of the segmentation it
describes, so re-running the segmenter invalidates a previous sign-off
instead of silently inheriting it.
"""

import hashlib
import re

from .models import VERSE_KINDS, Segment

APPROVAL_HEADING = "## Approval"
APPROVED_LINE = re.compile(r"^approved:\s*(true|false)\s*$", re.M)
HASH_LINE = re.compile(r"^segmentation:\s*([0-9a-f]{16})\s*$", re.M)


def _sanitise(text: str) -> str:
    """Collapse embedded newlines so a value cannot forge a new report line."""
    return text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")


def segmentation_hash(segments: list[Segment]) -> str:
    """A stable digest of the boundaries this report describes."""
    payload = "\n".join(f"{s.order}\x1f{s.kind}\x1f{s.title}\x1f{s.body}" for s in segments)
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
        "Change `approved` to true once the boundaries above are correct.",
        "Re-running segmentation changes the hash and voids this approval.",
        "",
        f"segmentation: {segmentation_hash(segments)}",
        "approved: false",
        "",
    ])
    return "\n".join(lines)


def is_approved(report_text: str, segments: list[Segment]) -> bool:
    """True only if the report says approved AND still describes `segments`.

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
    return approved.group(1) == "true" and stamped.group(1) == segmentation_hash(segments)
