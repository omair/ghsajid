"""Urdu/Punjabi text normalization and automatic transliteration."""

import re

TATWEEL = "ـ"

# (latin, is_vowel) per Urdu letter.
LETTERS = {
    "آ": ("aa", True), "ا": ("a", True), "ب": ("b", False), "پ": ("p", False),
    "ت": ("t", False), "ٹ": ("t", False), "ث": ("s", False), "ج": ("j", False),
    "چ": ("ch", False), "ح": ("h", False), "خ": ("kh", False), "د": ("d", False),
    "ڈ": ("d", False), "ذ": ("z", False), "ر": ("r", False), "ڑ": ("r", False),
    "ز": ("z", False), "ژ": ("zh", False), "س": ("s", False), "ش": ("sh", False),
    "ص": ("s", False), "ض": ("z", False), "ط": ("t", False), "ظ": ("z", False),
    "ع": ("", False), "غ": ("gh", False), "ف": ("f", False), "ق": ("q", False),
    "ک": ("k", False), "گ": ("g", False), "ل": ("l", False), "م": ("m", False),
    "ن": ("n", False), "ں": ("n", False), "و": ("o", True), "ہ": ("h", False),
    "ۃ": ("h", False), "ھ": ("h", False), "ء": ("", False), "ی": ("i", True),
    "ئ": ("i", True), "ے": ("e", True), "ؤ": ("o", True), "أ": ("a", True),
    "ۂ": ("h", False), "ۓ": ("e", True),
    # short-vowel diacritics carry real information; keep them
    "َ": ("a", True),   # zabar
    "ِ": ("i", True),   # zer
    "ُ": ("u", True),   # pesh
}

# Diacritics that carry no vowel value for slug purposes.
DROP = "ًٌٍؘؙؚّْٰٕٔٓ"

EXCEPTIONS = {
    "میں": "mein", "ہے": "hai", "ہیں": "hain", "ہوں": "hun", "نہیں": "nahin",
    "کے": "ke", "کی": "ki", "کا": "ka", "کو": "ko", "سے": "se", "پر": "par",
    "اور": "aur", "جو": "jo", "ہو": "ho", "بھی": "bhi", "یہ": "ye", "وہ": "wo",
    "تو": "to", "نے": "ne", "کوئی": "koi", "مرا": "mira", "میرا": "mera",
    "میری": "meri", "میرے": "mere", "اُس": "us", "اس": "is", "کہ": "keh",
    "ہر": "har", "جس": "jis", "کبھی": "kabhi", "پھر": "phir", "اک": "ak",
    "نہ": "na", "کیا": "kya", "ایک": "ek", "دو": "do", "کچھ": "kuch",
    # High-frequency content words in this corpus. The generic rule cannot
    # recover unwritten short vowels, so the common ones are named here.
    "کسی": "kisi", "کسے": "kise", "نگاہ": "nigah", "دل": "dil", "عشق": "ishq",
    "خواب": "khwab", "خوابوں": "khwabon", "جہاں": "jahan", "بھر": "bhar",
    "چراغ": "chiragh", "شعور": "shaoor", "سایہ": "saya", "روز": "roz",
    "پل": "pul", "زمیں": "zamin", "زمین": "zamin", "آسمان": "aasman",
    "آسماں": "aasman", "قدم": "qadam", "حالت": "halat", "کون": "kaun",
    "محمد": "muhammad", "احمد": "ahmad", "حسین": "hussain", "سعید": "saeed",
    "کتابیں": "kitaben", "کتاب": "kitab", "شجر": "shajar", "حیات": "hayat",
    "رات": "raat", "پانی": "pani", "لہر": "lehar", "بزم": "bazm",
    "کہانی": "kahani", "غزل": "ghazal", "نظم": "nazm", "درس": "dars",
    "گاہ": "gah", "سبز": "sabz", "باغ": "bagh", "دیوار": "deewar",
}

# Keep the Arabic block (letters, diacritics, Urdu punctuation) and whitespace.
# \w would strip combining marks, which carry the short vowels.
NON_URDU = re.compile(r"[^؀-ۿ\s]")


def strip_tatweel(text: str) -> str:
    """Remove kashida — typographic stretching with no semantic value."""
    return text.replace(TATWEEL, "")


# Word-initially these are glides, not vowels: یاسمیں is "yasmin", not "iasmin".
INITIAL_GLIDE = {"ی": ("y", False), "ئ": ("y", False), "و": ("w", False)}


def _tokens(word: str) -> list[tuple[str, bool]]:
    out: list[tuple[str, bool]] = []
    for ch in word:
        if ch in DROP:
            continue
        if ch in LETTERS:
            if not out and ch in INITIAL_GLIDE:
                out.append(INITIAL_GLIDE[ch])
                continue
            latin, is_vowel = LETTERS[ch]
            if latin:
                out.append((latin, is_vowel))
    return out


def transliterate_word(word: str) -> str:
    """Transliterate one Urdu word to lowercase Latin."""
    word = strip_tatweel(word)
    if word in EXCEPTIONS:
        return EXCEPTIONS[word]

    toks = _tokens(word)
    parts: list[str] = []
    for i, (latin, is_vowel) in enumerate(toks):
        parts.append(latin)
        if is_vowel or i + 1 >= len(toks):
            continue
        if toks[i + 1][1]:          # next token is a vowel — no filler needed
            continue
        # Urdu omits short vowels. A word-initial consonant pair always needs
        # one ("ksi" -> "kasi"); elsewhere insert only where no vowel already
        # resolves the cluster, so "krta" reads "karta", not "karata".
        after = toks[i + 2] if i + 2 < len(toks) else None
        if i == 0 or after is None or not after[1]:
            parts.append("a")
    return "".join(parts)


def slugify(text: str) -> str:
    """Turn an Urdu title into a URL-safe Latin slug."""
    text = strip_tatweel(text)
    text = NON_URDU.sub(" ", text)
    words = [w for w in text.split() if w]
    latin = [transliterate_word(w) for w in words]
    slug = "-".join(p for p in latin if p)
    return re.sub(r"-+", "-", slug).strip("-").lower()
