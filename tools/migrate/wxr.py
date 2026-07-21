"""Parse a WordPress WXR 1.2 export into Post records.

Uses xml.etree deliberately rather than defusedxml: this reads exactly one
trusted local file we exported ourselves, offline, and the package is
stdlib-only so it stays runnable without a package manager. Point this at an
untrusted export and switch to defusedxml.ElementTree first.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from .models import Post

NS = {
    "wp": "http://wordpress.org/export/1.2/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}


def _channel(path: Path) -> ET.Element:
    return ET.parse(path).getroot().find("channel")


def parse_posts(path: Path) -> list[Post]:
    """Return every published post, in export order."""
    posts = []
    for item in _channel(path).findall("item"):
        if item.findtext("wp:post_type", namespaces=NS) != "post":
            continue
        if item.findtext("wp:status", namespaces=NS) != "publish":
            continue
        cats = [
            c.text
            for c in item.findall("category")
            if c.get("domain") == "category" and c.text
        ]
        posts.append(
            Post(
                post_id=int(item.findtext("wp:post_id", namespaces=NS)),
                title=(item.findtext("title") or "").strip(),
                body=item.findtext("content:encoded", namespaces=NS) or "",
                categories=cats,
                published=(item.findtext("wp:post_date", namespaces=NS) or "")[:10],
                post_name=item.findtext("wp:post_name", namespaces=NS) or "",
            )
        )
    return posts


def attachment_urls(path: Path) -> list[str]:
    """Return every attachment URL in the export."""
    return [
        item.findtext("wp:attachment_url", namespaces=NS)
        for item in _channel(path).findall("item")
        if item.findtext("wp:post_type", namespaces=NS) == "attachment"
    ]
