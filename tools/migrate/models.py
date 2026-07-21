"""Data carried between migration stages."""

from dataclasses import dataclass, field


@dataclass
class Post:
    """One published item straight out of the WordPress export."""

    post_id: int
    title: str
    body: str
    categories: list[str]
    published: str      # ISO date, e.g. "2020-03-24"
    post_name: str      # original (percent-encoded) WordPress slug


@dataclass
class Piece:
    """One output file: frontmatter plus markdown body."""

    kind: str                       # ghazals | nazms | reviews | memoir | videos
    slug: str
    title: str
    language: str                   # urdu | punjabi | english
    script: str                     # nastaliq | shahmukhi | latin
    published: str
    body: str = ""
    tags: list[str] = field(default_factory=list)
    source_post_ids: list[int] = field(default_factory=list)
    extra: dict = field(default_factory=dict)   # kind-specific frontmatter
