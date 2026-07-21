"""De-multiplex WordPress's single category axis into kind/language/tags.

WordPress offers one taxonomy, so a post tagged `Punjabi + Videos + کہانی`
mixes language, medium, and genre. This splits that back into three fields.
"""

from .models import Post

# Medium beats genre: a video of a story is a video.
KIND_BY_CATEGORY = {
    "Videos": "videos",
    "درس گاہ": "memoir",
    "غزل": "ghazals",
    "نظم": "nazms",
    "تبصرے": "reviews",
    "Punjabi": "nazms",       # only when no stronger kind is present
}
KIND_PRIORITY = ["videos", "memoir", "ghazals", "nazms", "reviews"]

LANGUAGE_CATEGORY = "Punjabi"
SCRIPT_BY_LANGUAGE = {"urdu": "nastaliq", "punjabi": "shahmukhi"}

# Categories that are neither kind nor language.
NOISE = {"Misc", "Uncategorized"}


def classify(post: Post) -> tuple[str, str, str, list[str]]:
    """Return (kind, language, script, tags) for a post."""
    cats = [c for c in post.categories if c not in NOISE]

    candidates = {KIND_BY_CATEGORY[c] for c in cats if c in KIND_BY_CATEGORY}
    kind = next((k for k in KIND_PRIORITY if k in candidates), "nazms")

    language = "punjabi" if LANGUAGE_CATEGORY in cats else "urdu"
    script = SCRIPT_BY_LANGUAGE[language]

    consumed = {c for c in cats if c in KIND_BY_CATEGORY} | {LANGUAGE_CATEGORY}
    tags = [c for c in cats if c not in consumed]
    return kind, language, script, tags
