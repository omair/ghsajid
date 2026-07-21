"""Extract provenance links and video references from embed markup.

caarwan.com embeds are not media. They sit on pieces that already carry
their full text and mean "this poem also appeared there" — publication
provenance, which WordPress had no field for.
"""

import html as htmllib
import re

YOUTUBE = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]{11})")
FACEBOOK = re.compile(r"facebook\.com/([\w.-]+)/videos/(\d+)")
EXTERNAL_WP = re.compile(r'"providerNameSlug":"([\w-]+)"')
BLOCKQUOTE = re.compile(r"<blockquote[^>]*>(.*?)</blockquote>", re.S)
TAG = re.compile(r"<[^>]+>")
# Urdu posts write dates as DD-MM-YYYY.
CAPTION_DATE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")

PROVIDER_DOMAIN = {"caarwan": "caarwan.com"}


def extract_published_in(html: str) -> list[str]:
    """Return domains this piece was also published on."""
    out: list[str] = []
    for slug in EXTERNAL_WP.findall(html):
        domain = PROVIDER_DOMAIN.get(slug)
        if domain and domain not in out:
            out.append(domain)
    return out


def _caption(html: str) -> str:
    match = BLOCKQUOTE.search(html)
    if not match:
        return ""
    text = TAG.sub(" ", match.group(1))
    text = htmllib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    # Drop Facebook's own attribution tail.
    return re.sub(r"Posted by .*$", "", text).strip()


def extract_video(html: str) -> dict | None:
    """Return the single video referenced by this post, if any."""
    yt = YOUTUBE.search(html)
    if yt:
        vid = yt.group(1)
        return {
            "source": "youtube",
            "video_id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "description": "",
            "recorded": "",
        }

    fb = FACEBOOK.search(html)
    if fb:
        account, vid = fb.group(1), fb.group(2)
        caption = _caption(html)
        date = ""
        match = CAPTION_DATE.search(caption)
        if match:
            day, month, year = match.groups()
            date = f"{year}-{month}-{day}"
        return {
            "source": "facebook",
            "video_id": vid,
            "url": f"https://www.facebook.com/{account}/videos/{vid}/",
            "description": caption,
            "recorded": date,
        }

    return None
