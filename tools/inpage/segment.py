"""Find piece boundaries inside a decoded book.

A ghazal carries no title in the source; the site titles poems by their matlaa,
so finding the boundary IS finding the title. The paragraph mark's 4-byte
record is geometry — a line position stepping down a page — not a style id, so
a value that drops back toward the top of a page marks a new piece.

This is heuristic by construction. Nothing here writes to content/: the output
goes to staging with a report, and a human resolves every flag.
"""

import re

from .classify import (
    COLOPHON, HEADING, NORMALISED_HEADINGS, PROSE, SECOND_MISRA_GEOMETRY,
    UNKNOWN, VERSE, classify,
)
from .groundtruth import skeleton
from .models import Paragraph, Segment

# A real ghazal's matlaa is a line of verse, not a paragraph. When the
# boundary heuristic fails to find a break inside a large prose block (front
# matter, a foreword), the whole block becomes one "title" — one real pilot
# run produced a ~1400-character title that then crashed slugify()'s output
# path. The piece is never dropped for this; it is only flagged so a human
# reviewing the report can see it.
MAX_TITLE_LENGTH = 200

# Rhyme in Urdu is heard, not spelled, so the two orthographic differences that
# never change the sound are folded before any tail is compared. Both were
# measured as real missed matlaa in the pilot: تجاوز's ...اُتر آئی against a
# run rhyming گویائی/پسپائی/شہنائی (آ vs ا), and باغِ نشاط's ...ہالہ کہاں سے
# آتا ہے against اُجالا/والا/سنبھالا (word-final ہ vs ا). Each miss silently
# welded two ghazals into one piece.
RHYME_FOLD = str.maketrans({"آ": "ا", "ۂ": "ہ", "ۃ": "ہ", "ؤ": "و", "ۓ": "ے"})
FINAL_HE = re.compile(r"ہ(?=\s|$)")

# A rhyme is compared as characters, not words: the qafia is a *partial* word
# (نگ سے across سنگ/رنگ/ترنگ, یں تھا across زمیں/مبیں/یقیں), and it is exactly
# the part a word-tail comparison cannot see. Two characters is the floor —
# a bare ہے or سے is not evidence of anything.
MIN_RHYME = 2

# How many shers of the prospective new ghazal establish its rhyme. One sher
# cannot: its own tail carries accidental letters (سنگ سے alone yields
# "سنگ سے", not the qafia). Measured, the piece count is identical at 3, 4 and
# 5 for both pilot books, so this is a plateau rather than a fitted constant.
RHYME_WINDOW = 4

# The poet's takhallus. A sher carrying it is the maqtaa, the closing sher, so
# the ghazal after it is a new ghazal even when it happens to rhyme alike —
# this is what separates باغِ نشاط's ...بنامِ وصال ghazal from the ...خدّ و خال
# ghazal that follows it in the same "-ال" family.
TAKHALLUS = "ساجد"


GHAZAL_SHAPE_THRESHOLD = 0.9


def _is_ghazal_shaped(run: list[Paragraph]) -> bool:
    """True when most of the run pairs cleanly into shers.

    Measured by greedy pairing, NOT by positional parity. Parity — asking
    whether geometry == 1 falls on odd indices — is fragile: one unpairable
    line shifts the parity of everything after it, so conformance collapses to
    ~50% from the first anomaly onward. باغِ نشاط has 8 such lines in 1276 and
    was misfiled as a single nazm; تجاوز has zero, which is the only reason
    parity appeared to work there.

    Greedy pairing resyncs after each anomaly, so the measurement stays local:
    باغِ نشاط scores 634 clean pairs of 642 (98.8%) and تجاوز 817 of 817.
    A nazm, whose lines do not alternate at all, produces mostly half shers
    and falls far below the threshold.
    """
    if len(run) < 2:
        return False
    shers = pair_shers(run)
    clean = sum(1 for _, second in shers if second)
    return clean / len(shers) >= GHAZAL_SHAPE_THRESHOLD


def _ghazal_body(shers: list[tuple[str, str]]) -> str:
    return "\n\n".join(
        "\n".join(line for line in sher if line) for sher in shers
    )


def segment(paragraphs: list[Paragraph]) -> list[Segment]:
    """Assemble classified paragraphs into pieces.

    Heuristic by construction — output goes to staging behind a review report,
    never straight to content/. Nothing is ever dropped: an unpaired line is
    flagged, and a run that fits no pattern still becomes a piece.
    """
    kinds = classify(paragraphs)
    pieces: list[Segment] = []
    section = ""
    title_candidate = ""
    # A COLOPHON reaching the front of the book, before any piece has been
    # formed, has nothing to attach to yet (see the COLOPHON branch below).
    # Held here rather than dropped, and attached to the first piece add()
    # creates, whatever kind it turns out to be.
    pending_colophon = ""

    def add(kind: str, title: str, body: str, flags: list[str]) -> Segment:
        nonlocal pending_colophon
        if len(title) > MAX_TITLE_LENGTH:
            flags = flags + ["over-long-title"]
        piece = Segment(
            kind=kind,
            title=title,
            body=body,
            order=len(pieces) + 1,
            section=section,
            flags=flags,
        )
        if pending_colophon:
            piece.written_note = pending_colophon
            pending_colophon = ""
        pieces.append(piece)
        return piece

    index = 0
    while index < len(paragraphs):
        kind = kinds[index]
        para = paragraphs[index]

        if kind == HEADING:
            section = NORMALISED_HEADINGS[skeleton(para.text)]
            index += 1
            continue

        if kind == COLOPHON:
            if pieces:
                # A second colophon attaching to the same piece is appended,
                # not overwritten — the same "never drop it" rule as
                # pending_colophon below. No book in the corpus today has
                # adjacent colophons, so this path is covered by a synthetic
                # test rather than a measured one.
                current = pieces[-1].written_note
                pieces[-1].written_note = (
                    f"{current} {para.text}" if current else para.text
                )
            else:
                # Nothing exists yet to attach this to. Never drop it: hold
                # it until add() creates the next piece.
                pending_colophon = para.text
            index += 1
            continue

        if kind == UNKNOWN:
            title_candidate = para.text
            index += 1
            continue

        if kind == PROSE:
            start = index
            while index < len(paragraphs) and kinds[index] in (PROSE, VERSE):
                index += 1
            body = "\n\n".join(p.text for p in paragraphs[start:index])
            add("reviews", paragraphs[start].text[:MAX_TITLE_LENGTH], body, [])
            title_candidate = ""
            continue

        if kind == VERSE:
            start = index
            while index < len(paragraphs) and kinds[index] == VERSE:
                index += 1
            run = paragraphs[start:index]
            if _is_ghazal_shaped(run):
                for group in split_ghazals(pair_shers(run)):
                    flags = ["half-sher"] if any(not s[1] for s in group) else []
                    add("ghazals", group[0][0], _ghazal_body(group), flags)
            else:
                title = title_candidate or run[0].text
                add("nazms", title, "\n".join(p.text for p in run), [])
            title_candidate = ""
            continue

        index += 1

    return pieces


def pair_shers(run: list[Paragraph]) -> list[tuple[str, str]]:
    """Pair a verse run into shers using the recorded second-misra geometry.

    A trailing line with no partner is returned with an empty second misra
    rather than discarded — losing a line of poetry is never acceptable, and
    the caller flags the half sher for review.
    """
    shers: list[tuple[str, str]] = []
    index = 0
    while index < len(run):
        first = run[index]
        if (
            index + 1 < len(run)
            and run[index + 1].geometry == SECOND_MISRA_GEOMETRY
        ):
            shers.append((first.text, run[index + 1].text))
            index += 2
        else:
            shers.append((first.text, ""))
            index += 1
    return shers


def _rhyme_key(text: str) -> str:
    """The form a rhyme is compared in: letters only, sound-folded."""
    return FINAL_HE.sub("ا", skeleton(text).translate(RHYME_FOLD))


def _common_suffix(left: str, right: str) -> str:
    count = 0
    while (
        count < len(left)
        and count < len(right)
        and left[-1 - count] == right[-1 - count]
    ):
        count += 1
    return left[len(left) - count:] if count else ""


def _shared_rhyme(lines: list[str]) -> str:
    if not lines:
        return ""
    rhyme = lines[0]
    for line in lines[1:]:
        rhyme = _common_suffix(rhyme, line)
    return rhyme.lstrip()


def run_rhyme(shers: list[tuple[str, str]], index: int) -> str:
    """The qafia+radif the run starting at `index` shares, or "".

    Read from the SECOND misras — the only lines every sher of a ghazal
    rhymes on — of this sher and the few that follow it. Established forward
    like this, the rhyme belongs to the ghazal being opened rather than to the
    candidate sher alone, which is what stops an ordinary sher whose first
    misra happens to end on a common word (ہے, سے, تھا) from reading as an
    opening.

    At the end of a run there is nothing to look ahead to. There the sher's
    own two misras are used, which is the self-contained test — measured as
    changing no piece count in either pilot book, since it can apply at most
    once per verse run.
    """
    seconds = [
        _rhyme_key(second) for _, second in shers[index:index + RHYME_WINDOW]
        if second
    ]
    if len(seconds) >= 2:
        return _shared_rhyme(seconds)
    first, second = shers[index]
    return _common_suffix(_rhyme_key(first), _rhyme_key(second)).lstrip()


def is_matla(first: str, second: str, rhyme: str | None = None) -> bool:
    """True when the first misra ends in the ghazal's rhyme — a matlaa.

    Only the matlaa rhymes across both its lines; every later sher rhymes on
    the second line alone. `rhyme` is the run's established qafia+radif (see
    `run_rhyme`); passing None falls back to whatever the pair itself shares,
    which is the older self-contained reading.
    """
    if not first or not second:
        return False
    if rhyme is None:
        rhyme = _common_suffix(_rhyme_key(first), _rhyme_key(second)).lstrip()
    if len(rhyme) < MIN_RHYME:
        return False
    return _rhyme_key(first).endswith(rhyme)


def _same_zameen(established: str, opening: str) -> bool:
    """True when two rhymes are the same zameen, one merely stated longer.

    A group of one or two shers has not yet worn its accidental letters away,
    so its rhyme reads longer than the ghazal's real one (a lone سنگ سے before
    ترنگ سے and انگ سے reduce it to نگ سے). Either being a suffix of the other
    means they are the same rhyme seen at two resolutions.
    """
    return bool(established) and bool(opening) and (
        established.endswith(opening) or opening.endswith(established)
    )


def _is_maqta(sher: tuple[str, str]) -> bool:
    return any(TAKHALLUS in _rhyme_key(misra) for misra in sher if misra)


def split_ghazals(
    shers: list[tuple[str, str]],
) -> list[list[tuple[str, str]]]:
    """Group shers into ghazals, starting a new one at each matlaa.

    A matlaa alone is not enough to break the run. Two further readings of
    the same evidence decide whether the break is real:

    * A sher that opens on the rhyme the current ghazal is already in is its
      husn-e-matlaa — a second opening sher, which belongs to the same
      ghazal — not the start of a new one. تجاوز has one
      (وحشت ہے / محبّت ہے inside the قیامت ہے ghazal).
    * Unless the sher before it is the maqtaa, in which case the previous
      ghazal has closed and a like-rhymed opening really is a new poem.
    """
    groups: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    matla_before = False
    for index, (first, second) in enumerate(shers):
        rhyme = run_rhyme(shers, index)
        opens = is_matla(first, second, rhyme)
        if opens and current:
            established = _shared_rhyme(
                [_rhyme_key(s) for _, s in current if s]
            )
            husn = (
                _same_zameen(established, rhyme)
                and (len(current) > 1 or matla_before)
                and not _is_maqta(current[-1])
            )
            if not husn:
                groups.append(current)
                current = []
        current.append((first, second))
        matla_before = opens
    if current:
        groups.append(current)
    return groups
