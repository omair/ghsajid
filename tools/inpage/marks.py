"""Put back the diacritics a typist floated in front of their word.

InPage 1 books carry a mark stored AFTER a space and BEFORE the word it
belongs to — `بہت␣␣ُچوما`, `سے␣␣␣ّمحبت`. The decoder is not at fault: those
are the bytes on disk, set that way so the mark sits visually over the next
word on the printed page. In Unicode a mark belongs to the character before
it, so decoded faithfully it is a mark on a space, and the word loses it.
557 such marks across the four books, 502 of them in کلیات جلد ۲.

Where a floating mark belongs was measured, not guessed, against the book's
own correctly marked spellings:

  * a zabar, zer or pesh goes on the FIRST letter — every case the book's
    vocabulary pins to one letter is the first (چُوما, خُمار, بِکھر),
    unless the book spells the word with the mark further in (کھِلتی).
  * a zer that no placement explains is the PREVIOUS word's izafat, typed on
    the wrong side of the space: `قلب ِلشکر` is قلبِ لشکر. The word-final
    slot is never a candidate — a word's own izafat is typed after it.
  * a shadda goes where the book spells the word with one (محبّت, جنّت),
    the most frequent spelling winning a tie (پتّھر over پتھّر). With no
    spelling to go on it is DROPPED and reported: an unmarked word is
    ordinary Urdu, a shadda on the wrong letter is a misspelling.
  * a mark alone between spaces (`بعد ِ دعا`) is an izafat on the word
    before; after punctuation, where there is no word before, it floats onto
    the word after (`(  ُ  ّکلیاتِ`).
  * a fragment that is no word at all rejoins its neighbour when the two
    together are one the book knows (`قو ّت` is قوّت).

Only `text` changes. `raw` and `codes` describe the bytes on disk, and gate B
round-trips one against the other, so they are left exactly as decoded. The
invariant, tested: letters never change — a mark moves, or it is dropped.
"""

from __future__ import annotations

import collections
import re
import unicodedata
from dataclasses import replace

from .models import Paragraph

MARKS = "ً-ْٰ"
LEADING_MARKS = re.compile(f"^[{MARKS}]+")
ANY_MARK = re.compile(f"[{MARKS}]")
ZER = "ِ"
SHADDA = "ّ"

# Characters that may wrap a word without being part of it. A floating mark
# never belongs on one of these, and lexicon lookups ignore them.
PUNCTUATION = "،۔!؟,.:;\"'()[]«»-–—؛"

MARK_NAMES = {"َ": "zabar", "ِ": "zer", "ُ": "pesh", SHADDA: "shadda"}


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _split_punctuation(word: str) -> tuple[str, str, str]:
    """(leading punctuation, the word itself, trailing punctuation)."""
    core = word.lstrip(PUNCTUATION)
    lead = word[: len(word) - len(core)]
    stripped = core.rstrip(PUNCTUATION)
    return lead, stripped, core[len(stripped):]


def _floats(word: str) -> bool:
    return bool(LEADING_MARKS.match(word))


class _Lexicon:
    """The book's own vocabulary: how often each marked spelling occurs."""

    def __init__(self, paragraphs: list[Paragraph]):
        self.spelled: collections.Counter[str] = collections.Counter()
        self.bare: collections.Counter[str] = collections.Counter()
        for paragraph in paragraphs:
            for word in paragraph.text.split():
                if _floats(word):
                    continue
                core = _nfc(_split_punctuation(word)[1])
                if core:
                    self.spelled[core] += 1
                    self.bare[ANY_MARK.sub("", core)] += 1

    def count(self, spelling: str) -> int:
        return self.spelled[_nfc(spelling)]

    def best(self, word: str, mark: str, slots) -> str | None:
        """The known spelling of `word` with `mark` after one of `slots`."""
        best_count, best_spelling = 0, None
        for k in slots:  # in order, so a tie goes to the earlier letter
            spelling = word[:k] + mark + word[k:]
            if self.count(spelling) > best_count:
                best_count, best_spelling = self.count(spelling), spelling
        return best_spelling


def _vowel_slots(word: str) -> range:
    # Never the word-final slot: a mark there would be the word's own
    # izafat, and a typist sets that after the word, not before it.
    return range(1, max(len(word), 2))


def _shadda_slots(word: str) -> range:
    return range(1, len(word) + 1)


def _describe(mark: str) -> str:
    return "+".join(MARK_NAMES.get(ch, f"U+{ord(ch):04X}") for ch in mark)


def _reattach_text(text: str, lexicon: _Lexicon) -> tuple[str, list[str]]:
    parts = re.split(r"(\s+)", text)
    words, spaces = parts[0::2], parts[1::2]
    if not any(_floats(word) for word in words):
        return text, []

    unresolved: list[str] = []
    i = 0
    while i < len(words):
        word = words[i]
        match = LEADING_MARKS.match(word)
        if not match:
            i += 1
            continue
        mark, rest = match.group(0), word[match.end():]
        previous = words[i - 1] if i > 0 else ""
        p_lead, p_core, p_trail = _split_punctuation(previous)

        if not rest:
            # A mark standing alone between spaces.
            if p_core and mark == ZER:
                words[i - 1] = p_lead + p_core + mark + p_trail
            elif i + 1 < len(words):
                words[i + 1] = mark + words[i + 1]
            elif p_core:
                words[i - 1] = p_lead + p_core + mark + p_trail
            else:
                unresolved.append(f"dropped a lone {_describe(mark)} in {text!r}")
            del words[i]
            del spaces[i - 1 if i > 0 else 0: (i if i > 0 else 1)]
            continue

        lead, core, trail = _split_punctuation(rest)
        if SHADDA in mark and mark != SHADDA:
            # A vowel and a shadda floated together (`ُ  ّکلیاتِ` once the
            # lone pesh joins it) belong on different letters: the vowel on
            # the first, the shadda on the doubled consonant. Place the
            # shadda, then let the vowels float again on their own.
            placed = lexicon.best(core, SHADDA, _shadda_slots(core))
            if placed is None:
                placed = core
                unresolved.append(
                    f"dropped a floating shadda before {core!r}: no spelling "
                    f"in the book places it — in {text!r}"
                )
            words[i] = mark.replace(SHADDA, "") + lead + placed + trail
            continue
        is_shadda = SHADDA in mark
        slots = _shadda_slots(core) if is_shadda else _vowel_slots(core)
        first = core[:1] + mark + core[1:]

        placed = None
        if not is_shadda and lexicon.count(first):
            placed = first
        if placed is None:
            placed = lexicon.best(core, mark, slots)
        if placed is not None:
            words[i] = lead + placed + trail
        else:
            joined = None
            if p_core and not lead and not p_trail and not lexicon.bare[ANY_MARK.sub("", core)]:
                whole = p_core + core
                edge = len(p_core)
                join_slots = range(edge, edge + (len(core) + 1 if is_shadda else len(core)))
                joined = lexicon.best(whole, mark, join_slots)
            if joined is not None:
                words[i - 1] = p_lead + joined + trail
                del words[i]
                del spaces[i - 1]
                continue
            if mark == ZER and p_core and lexicon.count(p_core + ZER):
                words[i - 1] = p_lead + p_core + ZER + p_trail
                words[i] = lead + core + trail
            elif not is_shadda:
                words[i] = lead + first + trail
            else:
                words[i] = lead + core + trail
                unresolved.append(
                    f"dropped a floating {_describe(mark)} before {core!r}: "
                    f"no spelling in the book places it — in {text!r}"
                )
        if i > 0:
            spaces[i - 1] = " "
        i += 1

    if not words:
        return "", unresolved
    rebuilt = words[0] + "".join(s + w for s, w in zip(spaces, words[1:]))
    return _nfc(rebuilt), unresolved


def reattach(paragraphs: list[Paragraph]) -> tuple[list[Paragraph], list[str]]:
    """Return `paragraphs` with floating marks put back, and what was dropped.

    The lexicon is built from the same paragraphs, so a book is corrected by
    its own spelling and never by another book's or by the site's.
    """
    lexicon = _Lexicon(paragraphs)
    fixed: list[Paragraph] = []
    unresolved: list[str] = []
    for paragraph in paragraphs:
        text, dropped = _reattach_text(paragraph.text, lexicon)
        unresolved.extend(dropped)
        # A paragraph that was nothing but a mark is now empty, and `decode`
        # never hands on an empty paragraph; neither does this.
        if text:
            fixed.append(paragraph if text == paragraph.text else replace(paragraph, text=text))
    return fixed, unresolved
