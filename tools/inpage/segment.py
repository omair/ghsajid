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
    COLOPHON, HEADING, NORMALISED_HEADINGS, PROSE, RUNNING_HEADER,
    SECOND_MISRA_GEOMETRY, SEPARATOR, TOC, UNKNOWN, VERSE, body_start_index,
    classify,
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

# What opens an essay region, and what closes it. Both pilot books fence the
# critic's opening essay between ۰۰۰ separators; a section heading (غزلیں,
# نعت) closes one just as firmly, and so does the body start, since anything
# past it is the poems themselves.
REGION_OPEN_KINDS = (SEPARATOR, TOC, HEADING)
REGION_CLOSE_KINDS = (SEPARATOR, HEADING)

# تجاوز prints the essay's title first and its author second; باغِ نشاط
# prints them the other way round, so position alone cannot tell them apart —
# and taking the first line blind titled باغِ نشاط's essay "ڈاکٹر شاہد اشرف",
# its critic's name.
#
# An academic honorific does distinguish them: a critic is introduced as
# ڈاکٹر or پروفیسر, and a title is not. That is a real convention of Urdu
# literary criticism, not a guess about these two files. When exactly one
# heading line opens with an honorific it is the byline and the other is the
# title; anything else still keeps every line in the body, takes the first as
# the title, and raises the flag for a human, because attributing the wrong
# person to criticism of the poet's work is not a mistake worth risking.
HONORIFICS = ("ڈاکٹر", "پروفیسر", "سیّد", "سید", "پیر", "مولانا")
BYLINE_FLAG = "confirm-review-byline"


def _split_byline(heading_lines: list[str]) -> tuple[str, str, bool]:
    """Return `(title, author, resolved)` for an essay's heading lines."""
    bylines = [
        line for line in heading_lines
        if line.strip().startswith(HONORIFICS)
    ]
    others = [line for line in heading_lines if line not in bylines]
    if len(bylines) == 1 and others:
        return others[0], bylines[0], True
    return (heading_lines[0] if heading_lines else ""), "", False


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


def segment(
    paragraphs: list[Paragraph],
    dropped_unknowns: list[str] | None = None,
    unreached: list[tuple[str, Paragraph]] | None = None,
) -> list[Segment]:
    """Assemble classified paragraphs into pieces.

    Heuristic by construction — output goes to staging behind a review report,
    never straight to content/. Nothing is ever dropped: an unpaired line is
    flagged, and a run that fits no pattern still becomes a piece.

    `section` is taken only from a HEADING that sits at or after
    `body_start_index`. A heading before it belongs to the فہرست, which
    lists the book's section names before any poem has been reached; reading
    those as sections gave تجاوز a غزلیں label on all 101 pieces that was
    correct only by coincidence. Pieces formed before the first body heading
    are marked `precedes_first_heading` so the count gate can exclude them
    without depending on the section string.

    `UNKNOWN` paragraphs are the one exception worth naming: each is held as
    `title_candidate` on the chance a nazm immediately follows it with no
    title of its own, but a candidate that is overwritten by a later UNKNOWN,
    or that is still pending when a review/ghazal/EOF makes it moot, reaches
    no piece at all — it is not retained anywhere in the return value. This
    is unchanged behaviour, not a new bug: `dropped_unknowns`, if given a
    list, is appended with the text of every such paragraph so a caller (see
    `cmd_segment`) can surface the count instead of it vanishing silently.

    `unreached` is the general form of that same accounting and is what a
    caller should prefer: given a list, it is appended with `(kind,
    paragraph)` for every paragraph whose text reached no piece at all,
    whatever its kind. Some of that is legitimate — the title page, the
    فہرست, the ۰۰۰ separators, a section heading that becomes `section`
    metadata — but a poem's line appearing there is the loss this pipeline
    exists to prevent, and it was invisible until the count was reported.
    """
    if dropped_unknowns is None:
        dropped_unknowns = []
    # Held as (index, text) rather than appended straight to
    # `dropped_unknowns`: an UNKNOWN that looked moot when it was overwritten
    # can still be swept up by an essay region that starts before it, and
    # reporting it as dropped after it reached a piece would be a false
    # alarm. Reconciled against `consumed` at the end.
    pending_drops: list[tuple[int, str]] = []
    kinds = classify(paragraphs)
    body_start = body_start_index(paragraphs)
    pieces: list[Segment] = []
    section = ""
    collection = ""
    # How many pieces had already been formed when the first BODY heading was
    # reached, or None if the book has no body heading at all. Those pieces
    # precede every section the book declares (باغِ نشاط's epigraph couplet
    # is the one real instance), and `precedes_first_heading` is stamped onto
    # them once the whole book has been read — at add() time there is no way
    # to know whether a heading is still coming.
    pieces_before_first_heading: int | None = None
    title_candidate = ""
    title_candidate_index = -1
    # Every paragraph index whose text reached a piece — body, title or
    # written_note. What is left over is reported through `unreached`.
    consumed: set[int] = set()
    # A COLOPHON reaching the front of the book, before any piece has been
    # formed, has nothing to attach to yet (see the COLOPHON branch below).
    # Held here rather than dropped, and attached to the first piece add()
    # creates, whatever kind it turns out to be.
    pending_colophon = ""
    pending_colophon_index = -1
    # The paragraph just after the last structural boundary (۰۰۰, a فہرست
    # line, a section heading), and the end of the last piece formed. An
    # essay region starts at whichever is later: the boundary tells us where
    # the essay's own heading lines begin, and the piece end stops a region
    # from reaching back over verse already emitted.
    boundary = 0
    emitted_end = 0

    def add(kind: str, title: str, body: str, flags: list[str]) -> Segment:
        nonlocal pending_colophon, pending_colophon_index
        if len(title) > MAX_TITLE_LENGTH:
            flags = flags + ["over-long-title"]
        piece = Segment(
            kind=kind,
            title=title,
            body=body,
            order=len(pieces) + 1,
            section=section,
            collection=collection,
            flags=flags,
        )
        if pending_colophon:
            piece.written_note = pending_colophon
            consumed.add(pending_colophon_index)
            pending_colophon = ""
            pending_colophon_index = -1
        pieces.append(piece)
        return piece

    index = 0
    while index < len(paragraphs):
        kind = kinds[index]
        para = paragraphs[index]

        if kind == RUNNING_HEADER:
            # Page furniture: it names the collection and is otherwise
            # invisible. Emphatically no flush — 972 of these in کلیات vol 2
            # would cut a ghazal at every page turn.
            collection = para.text
            index += 1
            continue

        if kind == HEADING:
            # Only a heading inside the body names a section. Before the body
            # start the same words are the فہرست listing its own section
            # names, and taking `section` from there labelled whole books off
            # a table of contents: تجاوز's only two headings are at
            # paragraphs 1 and 16 against a body start of 85, and all 101 of
            # its pieces inherited غزلیں from them. That label happened to be
            # right, but nothing in the evidence said so.
            if index >= body_start:
                section = NORMALISED_HEADINGS[skeleton(para.text)]
                if pieces_before_first_heading is None:
                    pieces_before_first_heading = len(pieces)
            boundary = index + 1
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
                consumed.add(index)
            else:
                # Nothing exists yet to attach this to. Never drop it: hold
                # it until add() creates the next piece.
                pending_colophon = para.text
                pending_colophon_index = index
            index += 1
            continue

        if kind == UNKNOWN:
            # A candidate still pending when a new one arrives never reached
            # a piece — see the docstring's note on dropped_unknowns.
            if title_candidate:
                pending_drops.append((title_candidate_index, title_candidate))
            title_candidate = para.text
            title_candidate_index = index
            index += 1
            continue

        if kind == PROSE:
            start, end = _essay_region(
                kinds, index, boundary, emitted_end, body_start
            )
            # A running header can fall inside a long essay region — the
            # critic's quotations span pages too — and the region is
            # consumed in one jump below, never passing through the
            # RUNNING_HEADER branch. Without this, the header's own
            # collection change is silently skipped, and its text would
            # otherwise leak into the review body as though it were prose.
            for header_index in range(start, end):
                if kinds[header_index] == RUNNING_HEADER:
                    collection = paragraphs[header_index].text
            piece = _add_review(
                add, paragraphs[start:end], kinds[start:end], index, paragraphs
            )
            consumed.update(
                i for i in range(start, end) if kinds[i] != RUNNING_HEADER
            )
            if title_candidate:
                pending_drops.append((title_candidate_index, title_candidate))
            title_candidate = ""
            title_candidate_index = -1
            emitted_end = end
            index = end
            continue

        if kind == VERSE:
            start = index
            while index < len(paragraphs) and kinds[index] in (VERSE, RUNNING_HEADER):
                if kinds[index] == RUNNING_HEADER:
                    collection = paragraphs[index].text
                index += 1
            run = [p for p, k in zip(paragraphs[start:index], kinds[start:index])
                   if k == VERSE]
            if _is_ghazal_shaped(run):
                # A ghazal is titled by its matlaa, never by title_candidate —
                # a pending candidate here is moot and reaches no piece.
                if title_candidate:
                    pending_drops.append(
                        (title_candidate_index, title_candidate)
                    )
                for group in split_ghazals(pair_shers(run)):
                    flags = ["half-sher"] if any(not s[1] for s in group) else []
                    add("ghazals", group[0][0], _ghazal_body(group), flags)
            else:
                title = title_candidate or run[0].text
                if title_candidate:
                    consumed.add(title_candidate_index)
                add("nazms", title, "\n".join(p.text for p in run), [])
            consumed.update(range(start, index))
            title_candidate = ""
            title_candidate_index = -1
            emitted_end = index
            continue

        if kind in (SEPARATOR, TOC):
            boundary = index + 1
        index += 1

    # A candidate still pending at end of book (paragraphs ran out right
    # after the last UNKNOWN) never reached a piece either.
    if title_candidate:
        pending_drops.append((title_candidate_index, title_candidate))

    if pieces_before_first_heading is not None:
        for piece in pieces[:pieces_before_first_heading]:
            piece.precedes_first_heading = True

    dropped_unknowns.extend(
        text for i, text in pending_drops if i not in consumed
    )
    if unreached is not None:
        unreached.extend(
            (kinds[i], para)
            for i, para in enumerate(paragraphs)
            if i not in consumed
        )
    return pieces


def _essay_region(
    kinds: list[str],
    prose_index: int,
    boundary: int,
    emitted_end: int,
    body_start: int,
) -> tuple[int, int]:
    """The half-open span of paragraphs the essay at `prose_index` occupies.

    Bounded structurally, not by the prose run: the critic quotes the poet
    throughout, and each quotation is verse sitting before the first ghazal,
    where classify() can only call it FRONT_MATTER. Taking the prose run
    alone therefore stopped at the first quotation, dropped it, and started a
    fresh fragment after it — تجاوز's essay became 5 pieces and lost 5 lines,
    باغِ نشاط's became 10 and lost ~50.

    The span runs from the last structural boundary (so the essay's title and
    author lines come with it) to the next one, never past the body start and
    never back over paragraphs already emitted.
    """
    start = max(boundary, emitted_end)
    end = prose_index
    while end < len(kinds) and kinds[end] not in REGION_CLOSE_KINDS:
        end += 1
    if body_start > prose_index:
        end = min(end, body_start)
    return start, end


def _add_review(
    add,
    region: list[Paragraph],
    region_kinds: list[str],
    prose_index: int,
    paragraphs: list[Paragraph],
) -> Segment:
    """Emit one `reviews` piece for a whole essay region, in source order."""
    # A running header inside the region is page furniture, exactly as it
    # is everywhere else — it names the collection (handled by the caller
    # before this runs) and must not become literal essay text.
    body_lines = [
        p.text for p, k in zip(region, region_kinds)
        if k not in (COLOPHON, RUNNING_HEADER)
    ]
    first_prose = next(
        (i for i, k in enumerate(region_kinds) if k == PROSE), 0
    )
    heading_lines = [
        p.text
        for p, k in zip(region[:first_prose], region_kinds[:first_prose])
        if k not in (COLOPHON, RUNNING_HEADER)
    ]
    title, author, resolved = _split_byline(heading_lines)
    if not title:
        title = paragraphs[prose_index].text
    flags = [] if resolved or not heading_lines else [BYLINE_FLAG]
    piece = add("reviews", title[:MAX_TITLE_LENGTH], "\n\n".join(body_lines), flags)
    piece.reviewed_author = author
    for p, k in zip(region, region_kinds):
        if k != COLOPHON:
            continue
        piece.written_note = (
            f"{piece.written_note} {p.text}" if piece.written_note else p.text
        )
    return piece


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
