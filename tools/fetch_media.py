"""Download images and archive videos. The only networked step.

Usage:
    python3 tools/fetch_media.py images
    python3 tools/fetch_media.py videos

Images are small and belong in the repo. Videos are insurance against a
third-party account disappearing and stay out of git.
"""

import re
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.migrate.wxr import attachment_urls  # noqa: E402

EXPORT = Path("data/export.xml")
IMAGES = Path("public/media/images")
VIDEOS = Path("media/video")
URL_FIELD = re.compile(r'^url:\s*"([^"]+)"', re.M)

# yt-dlp ships as a self-contained zipapp; prefer a locally fetched copy so
# this works without a package manager.
LOCAL_YTDLP = Path("tools/bin/yt-dlp")


def _ytdlp_cmd() -> list[str]:
    if LOCAL_YTDLP.exists():
        return [sys.executable, str(LOCAL_YTDLP)]
    return ["yt-dlp"]


def fetch_images() -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    for url in attachment_urls(EXPORT):
        # WordPress re-uploads land as "-1.jpg" duplicates of the same image.
        name = re.sub(r"-\d+(\.\w+)$", r"\1", url.rsplit("/", 1)[-1])
        if name in seen:
            print(f"skip duplicate {name}")
            continue
        seen.add(name)
        target = IMAGES / name
        if target.exists():
            print(f"have {name}")
            continue
        print(f"get  {name}")
        urllib.request.urlretrieve(url, target)
    print(f"{len(seen)} distinct images in {IMAGES}")


def fetch_videos() -> None:
    VIDEOS.mkdir(parents=True, exist_ok=True)
    urls = []
    for md in sorted(Path("content/videos").glob("*.md")):
        match = URL_FIELD.search(md.read_text(encoding="utf-8"))
        if match:
            urls.append((md.stem, match.group(1)))

    failed = []
    for stem, url in urls:
        print(f"archiving {stem}: {url}")
        result = subprocess.run(
            # Name by id: Urdu captions become filenames far past the
            # 255-byte limit, and the id is the stable identifier anyway.
            _ytdlp_cmd() + ["-o", str(VIDEOS / "%(id)s.%(ext)s"), url],
            check=False,
        )
        if result.returncode != 0:
            failed.append((stem, url))

    print(f"\n{len(urls) - len(failed)}/{len(urls)} archived into {VIDEOS}")
    if failed:
        # A failure here means that recording is already at risk.
        print("FAILED — these recordings could not be archived:")
        for stem, url in failed:
            print(f"  {stem}: {url}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "images":
        fetch_images()
    elif mode == "videos":
        fetch_videos()
    else:
        print(__doc__)
        raise SystemExit(2)
