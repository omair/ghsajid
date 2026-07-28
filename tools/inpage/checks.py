"""Gates run before anything is written.

Silent text corruption in someone's poetry is the failure mode that matters,
so the pipeline refuses to write when these fail. Note carefully which gate
catches which failure: completeness and round-trip are both BLIND to a
wrong-but-consistent mapping, where every poem decodes with the right
character count and re-encodes perfectly while being uniformly wrong. Only
the ground-truth gate can see that, and even it only sees regressions
against the committed baseline, not verbatim reproduction of every ghazal
(see `groundtruth_errors`).
"""

import collections
import re

from .classify import (
    VERSE, _is_verse_length, body_start_index, classify, toc_count,
)
from .codepage import decode_byte, encode_char, unmapped
from .decode import all_codes
from .groundtruth import (
    EXPECTED_LINES_TOTAL,
    KNOWN_GHAZALS,
    MIN_LINES_MATCHED,
    MIN_WHOLE_GHAZALS,
    line_match_report,
    site_text,
    skeleton,
)
from .models import VERSE_KINDS, Paragraph, Segment

WORD = re.compile(r"[^\s]+")


def completeness_errors(data: bytes) -> list[str]:
    """Gate A — every char code in the stream must be in the table.

    Blind spot: `all_codes` iterates `decode()`'s output, so a code that
    `decode.py`'s run-length or control-byte filters exclude never reaches
    this gate at all — not reported unmapped, not reported anything. 0xE8
    (an ornamental divider) is the known instance: it appears only as an
    isolated pair, so gate A can never see it. See `decode.excluded_report`
    for the count of what these filters discard.
    """
    missing = unmapped(all_codes(data))
    if not missing:
        return []
    listed = ", ".join(f"{code:#04x}" for code in sorted(missing))
    return [f"unmapped char codes: {listed}"]


def roundtrip_errors(paragraphs: list[Paragraph]) -> list[str]:
    """Gate B — decoded text must re-encode to the codes it came from.

    Compares against `raw`, not `text`: `text` is stripped while `codes` still
    carries the surrounding space codes.
    """
    errors = []
    for index, para in enumerate(paragraphs, start=1):
        expected = [c for c in para.codes if decode_byte(c) is not None]
        actual = [encode_char(ch) for ch in para.raw if encode_char(ch) is not None]
        if expected != actual:
            errors.append(f"paragraph {index} does not round-trip: {para.text[:40]!r}")
    return errors


def groundtruth_errors(paragraphs: list[Paragraph]) -> list[str]:
    """Gate C — the codepage must still meet the committed ground-truth baseline.

    Not verbatim reproduction: the site text and the printed کلیات are
    genuinely different editions (site-only provenance blocks, InPage
    typesetting conventions, misras run together, real textual variants), so
    asserting that all 11 known ghazals reproduce whole would raise false
    alarms on every review. Instead this checks the codepage still
    reproduces at least as many ground-truth lines letter-for-letter, and at
    least as many whole ghazals, as it did when the baseline
    (`tools.inpage.groundtruth.MIN_LINES_MATCHED` /
    `EXPECTED_LINES_TOTAL` / `MIN_WHOLE_GHAZALS`) was measured. A wrong
    codepage entry breaks hundreds of lines at once and still fails this;
    edition variance already present in the baseline does not.
    """
    report = line_match_report(paragraphs, KNOWN_GHAZALS)
    total = sum(len(results) for results in report.values())
    matched = sum(sum(results) for results in report.values())
    whole = sum(1 for results in report.values() if results and all(results))

    errors = []
    if total != EXPECTED_LINES_TOTAL:
        errors.append(
            f"ground truth corpus size changed: {total} lines total, expected {EXPECTED_LINES_TOTAL}"
        )
    if matched < MIN_LINES_MATCHED:
        errors.append(
            f"ground truth regression: only {matched}/{total} lines reproduce "
            f"(baseline: {MIN_LINES_MATCHED}/{EXPECTED_LINES_TOTAL})"
        )
    if whole < MIN_WHOLE_GHAZALS:
        errors.append(
            f"ground truth regression: only {whole} ghazals reproduce whole "
            f"(baseline: {MIN_WHOLE_GHAZALS})"
        )
    return errors


def lexicon_report(paragraphs: list[Paragraph], lexicon: set[str]) -> list[str]:
    """Gate D — words absent from the lexicon, most frequent first.

    Reported, never fatal: the lexicon cannot know this poet's vocabulary.
    A cluster of related outliers is the signature of a wrong table entry.
    """
    counts = collections.Counter(
        word for para in paragraphs for word in WORD.findall(para.text)
        if word not in lexicon
    )
    return [f"{word} ({n}x)" for word, n in counts.most_common(50)]


# The flag a piece carries when its text is not believable as text at all.
GARBAGE_FLAG = "likely-decode-garbage"

# The share of a piece's words that must already appear in the archive's own
# lexicon (`groundtruth.corpus_lexicon`) before the piece reads as language.
# Measured across both books:
#
#     piece                          words   1-char tokens   in lexicon
#     باغِ نشاط's critical essay      1659           0.009        0.794
#     تجاوز's critical essay          1695           0.014        0.784
#     the weakest real ghazal           86               -        0.767
#     باغِ نشاط's order-88 scratch      35           0.229        0.143
#
# Real text — prose and verse alike — never fell below 0.767; the one piece
# that is not text sits at 0.143, a gap of better than 5x. 0.4 is placed
# roughly in the middle of that gap on a ratio scale: 1.9x below the weakest
# real piece and 2.8x above the garbage, so neither a poet's unusually private
# vocabulary nor a lexicon that grows as the archive does can push a real
# piece across it, and a partial mis-decode has to be genuinely half-readable
# before it escapes. Hugging either measured figure would make the gate a
# record of these two books rather than a test of the next one.
GARBAGE_LEXICON_SHARE = 0.4

# Below this many words the share is too coarse to mean anything: a two-line
# قطعہ can be 8 words, where a single unfamiliar name already moves the score
# by 12 points. The shortest real piece in either book — باغِ نشاط's epigraph
# couplet — is 17 words, and the garbage piece is 35, so the exemption covers
# only pieces shorter than anything the gate could honestly judge. It also
# makes the division safe: an empty body has no words and is never scored.
MIN_WORDS_FOR_GARBAGE_CHECK = 12


def flag_decode_garbage(segments: list[Segment], lexicon: set[str]) -> list[str]:
    """Flag pieces whose text is probably mis-decoded, and name them.

    باغِ نشاط's stream ends in scratch material that segmented into a
    190-character `reviews` piece at order 88 — 35 "words", 23% of them a
    single character, 14% of them known to the archive. It is not text.

    It is still kept. Nothing this pipeline does not understand may be
    dropped: that rule has already caught three separate poem-loss bugs, and a
    decoder that discards what it cannot read is exactly how they happened. So
    the piece is flagged (`GARBAGE_FLAG`, which the report prints beside it)
    and named in the gate output, where a reviewer signing the approval cannot
    miss it. Mutates `flags`, like `clear_unverifiable_sections` mutates
    `section` — the finding has to travel with the piece into the report.
    """
    flagged: list[tuple[Segment, float, int]] = []
    for segment in segments:
        words = skeleton(segment.body).split()
        if len(words) < MIN_WORDS_FOR_GARBAGE_CHECK:
            continue
        share = sum(1 for word in words if word in lexicon) / len(words)
        if share >= GARBAGE_LEXICON_SHARE:
            continue
        if GARBAGE_FLAG not in segment.flags:
            segment.flags.append(GARBAGE_FLAG)
        flagged.append((segment, share, len(words)))
    if not flagged:
        return []
    listed = "; ".join(
        f"order {segment.order} ({segment.kind}) {segment.title[:30]!r} — "
        f"{share:.0%} of {count} words known"
        for segment, share, count in flagged
    )
    return [
        f"{len(flagged)} piece(s) flagged {GARBAGE_FLAG}: under "
        f"{GARBAGE_LEXICON_SHARE:.0%} of their words appear anywhere in the "
        f"archive, so they are probably mis-decoded rather than written. Kept, "
        f"not dropped — read them before approving: {listed}"
    ]


# The flag a piece carries when its whole body is one surviving line.
SINGLE_LINE_FLAG = "single-line-piece"


def flag_single_line_pieces(segments: list[Segment]) -> list[str]:
    """Flag a poem whose entire body is one non-empty line, and name it.

    کلیات جلد ۲ emits 33 of these, vol 1 emits 3, and they are not one
    thing: a dedication ("زُبیر ساجد کے لیے"), a possible nazm title
    orphaned from its own body ("کیا ہم کہیں کھڑے ہیں؟"), and outright
    decode garbage ("ب گینیگایںقرا ۔ ا  کج") all land here identically. A
    فرد — a real, single-sher poem — is also one line, so the shape alone
    cannot say which of these a given piece is.

    So it is never guessed at. This only flags and names the piece, the same
    "kept, not dropped, a human decides" contract as `flag_decode_garbage`:
    the piece stays exactly as segmented, still staged, still promotable,
    just carrying one more thing for a reviewer to look at before approving.
    """
    flagged = [
        segment for segment in segments
        if segment.kind in VERSE_KINDS
        and len([ln for ln in segment.body.split("\n") if ln.strip()]) == 1
    ]
    for segment in flagged:
        if SINGLE_LINE_FLAG not in segment.flags:
            segment.flags.append(SINGLE_LINE_FLAG)
    if not flagged:
        return []
    listed = "; ".join(
        f"order {segment.order} ({segment.kind}) {segment.title[:30]!r}"
        for segment in flagged[:5]
    )
    return [
        f"{len(flagged)} piece(s) flagged {SINGLE_LINE_FLAG}: a single "
        f"surviving line reads as a poem, but dedications, orphaned titles "
        f"and decode garbage are indistinguishable from a real فرد without "
        f"a human. Kept, not dropped — read them before approving: {listed}"
    ]


def toc_count_errors(
    paragraphs: list[Paragraph], segments: list[Segment]
) -> list[str]:
    """The POEM count must equal what the book's own فہرست declares.

    تجاوز's فہرست is numbered 1-100 and باغِ نشاط's 1-85, so the expected
    count is read from the file rather than judged. This turns "866 pieces
    looks wrong" into arithmetic.

    **Only for a book that is one book.** A gathering — a کلیات volume whose
    pieces carry a `collection` — has no whole-book numbering to read: جلد ۲'s
    numeric index yields 124 against 561 poems (it numbers one collection's
    contents, not the volume's), and جلد ۱ has no numeric index at all. Running
    this there produced a guaranteed `delta +437` on every report and a "could
    not run" on the other, which is noise a reviewer has to learn to ignore —
    and a gate a reviewer learns to ignore is worse than no gate. The
    equivalent for a gathering is `declared_collection_count_errors`, which
    asserts each collection against the count the volume declares for it.

    Counted against the poems, not every piece. Read in the source, each
    فہرست sits under the heading غزلیں and its numbering ends before the
    critical foreword that follows it — تجاوز's numbers run out at paragraph
    65 and Dr Saadat Saeed's essay starts at 67, signed and dated at 83. That
    essay is what becomes the `reviews` pieces (5 in تجاوز, 10 in
    باغِ نشاط), and it is not a numbered entry in either book. Comparing
    total pieces instead made the gate fail by exactly the review count in
    both books — +5 and +10 — while the poems matched the declared 100 and 85
    exactly. So the basis is the poems; the reviews are carried by the
    conservation gate and the report, not counted here.

    Poems before the first BODY heading are excluded, for the same reason.
    باغِ نشاط's epigraph couplet — باغِ نشاط کی طرف اپنے قدم نہیں بڑھے / جب
    سے ہمارے کھوج میں بادِ صبا نہیں رہی, the couplet the book takes its title
    from — was recovered as a real, correctly segmented poem, but it sits at
    paragraphs 129-130, before the book's first heading at 131, so it is not
    a numbered فہرست entry either. Counting every VERSE_KINDS piece made the
    gate read 86 against a declared 85.

    Excluded by POSITION (`Segment.precedes_first_heading`), not by an empty
    `section` string. The section is the wrong property to key on twice over:
    باغِ نشاط's only headings are both نعت, so its ghazals' section is a
    false label that `clear_unverifiable_sections` erases, and تجاوز now has
    no body heading at all, so every one of its poems carries `section: ""`
    — a section-based count read 0 against a declared 100. Position survives
    both: تجاوز has no body heading, so nothing is excluded and all 100
    poems count; باغِ نشاط excludes the one piece before paragraph 131 and
    counts 85. The epigraph is still emitted as a piece, still written to
    the book record, still promotable, just not counted against a فہرست that
    never numbered it.
    """
    if any(segment.collection for segment in segments):
        # A gathering. See the docstring: declared_collection_count_errors is
        # the gate that applies, and it runs per collection.
        return []
    expected = toc_count(paragraphs)
    if expected is None:
        return ["no فہرست found: the piece-count gate could not run"]
    actual = sum(
        1 for segment in segments
        if segment.kind in VERSE_KINDS and not segment.precedes_first_heading
    )
    if actual != expected:
        return [
            f"poem count {actual} does not match the فہرست's {expected} "
            f"(delta {actual - expected:+d})"
        ]
    return []


# Poem counts a gathering volume declares for the books it gathers, keyed by
# book slug then by collection. These are NOT judgements about how many poems
# look right; they are arithmetic the book prints about itself, in the same
# class as تجاوز's numbered فہرست of 100 (see `toc_count_errors`).
#
# کلیات جلد ۱'s فہرست, the piece at order 1, states each collection's sections
# and their sizes:
#
#   موسم    بہار، سعیر، برشگال، خزاں، زمہریر at بیس غزلیں (20) each,
#           plus قدیم at تیس غزلیں (30)                    = 130
#   عناصر   مٹّی، پانی، آگ، ہَوا، خواب at بیس غزلیں (20) each = 100
#
# They are worth asserting because they are independent of the boundary the
# segmenter finds: the title-page blocks and the declared counts are two
# separate structures in the book, and they agree to the poem. If a future
# change moves a boundary, one of these two numbers moves with it and this
# gate says by how much. Do NOT adjust a boundary to make a count come out —
# the whole value of these two figures is that the book declared them.
#
# The volume's other four collections — کتابِ صبح، آیندہ، معاملہ، روداد —
# declare no count anywhere in the source, so none is asserted for them. Their
# totals are reported by cmd_segment's "poems per collection" line and left at
# that; inventing a number to assert against would be worse than asserting
# nothing.
DECLARED_COLLECTION_COUNTS: dict[str, dict[str, int]] = {
    "kulliyat-jild-1": {"موسم": 130, "عناصر": 100},
}


def declared_collection_count_errors(
    segments: list[Segment], declared: dict[str, int]
) -> list[str]:
    """Each declared collection must hold exactly the poems it declares.

    Counted over VERSE_KINDS, like `toc_count_errors`: a دیباچہ inside a
    collection is a `reviews` piece and was never one of its غزلیں.

    A collection missing from the segmentation entirely reports its whole
    count as the delta rather than passing silently — that is the shape a
    broken boundary detector would take, and a gate that goes quiet when its
    subject disappears is not a gate.
    """
    counts = collections.Counter(
        piece.collection for piece in segments if piece.kind in VERSE_KINDS
    )
    errors = []
    for name, expected in declared.items():
        actual = counts.get(name, 0)
        if actual != expected:
            errors.append(
                f"collection {name} holds {actual} poems against the "
                f"{expected} the volume's own فہرست declares for it "
                f"(delta {actual - expected:+d})"
            )
    return errors


# The share of a book's poems one section may cover before the label stops
# being evidence of anything. باغِ نشاط is the measured case: its only two
# headings are both نعت (paragraphs 131 and 144), the غزلیں heading the book
# really prints never reaches the byte stream at all — InPage keeps some
# headings in separate text frames the linear stream does not carry — and so
# 85 ghazals inherited نعت, 85 of 86 poems, 98.8%.
#
# 0.9 is chosen as the point past which the label has stopped describing a
# section and started describing the whole book. What it really means is that
# the source gave us where a section BEGINS and never where it ENDS: there is
# no second heading to close it, so every poem after the first one keeps
# inheriting. That reading holds whether or not the book truly has one
# section, which is why the message says the boundary could not be determined
# rather than claiming the heading is wrong. Below 0.9 a book is genuinely
# divided and each heading is closed by the next, so the sections stand.
IMPLAUSIBLE_SECTION_SHARE = 0.9


def clear_unverifiable_sections(segments: list[Segment]) -> list[str]:
    """Report and erase a section that swallows most of the book.

    Mutates `segments`, which no other check here does, and deliberately:
    the finding and the remedy are the same act. `section` is written
    verbatim into content/books/*.yaml, so leaving it in place would publish
    نعت — the devotional form addressed to the Prophet — as the label on 85
    of this poet's ghazals. An empty section is honest about what the source
    supports; نعت on a ghazal is a fabrication, and the archive is the wrong
    place to keep one.

    The share is measured over poems (VERSE_KINDS) since that is what a
    section divides, but the label is cleared from every piece carrying it,
    reviews included. See IMPLAUSIBLE_SECTION_SHARE for the threshold.
    """
    poems = [s for s in segments if s.kind in VERSE_KINDS]
    if not poems:
        return []
    counts = collections.Counter(s.section for s in poems if s.section)
    messages = []
    for name, count in counts.most_common():
        if count / len(poems) < IMPLAUSIBLE_SECTION_SHARE:
            continue
        messages.append(
            f'section "{name}" covers {count} of {len(poems)} poems: no '
            f"further heading closes it, so its boundary could not be "
            f"determined — headings may be missing from the source. Cleared "
            f"the section on those pieces rather than asserting it."
        )
        for piece in segments:
            if piece.section == name:
                piece.section = ""
    return messages


def conservation_errors(
    paragraphs: list[Paragraph], segments: list[Segment]
) -> list[str]:
    """No verse text is missing or duplicated corpus-wide.

    Checked by matching the lines themselves, not by counting them. A plain
    count of emitted lines cannot express this: it is off by the prose a
    `reviews` piece legitimately carries (+7 lines in تجاوز, +11 in
    باغِ نشاط, all of them the foreword's paragraphs), and it would let a
    line dropped in one place be masked by a line duplicated in another.
    Comparing multisets of the text says what the gate actually proves —
    nothing lost, nothing emitted twice, across the corpus as a whole — and
    stays blind to the prose either way.

    Blind spot: the comparison is a global multiset, not a per-piece one, so
    it cannot see a line *moving* between pieces. A sher relocated from one
    ghazal to another conserves perfectly and this gate stays silent — it
    does not prove each verse paragraph lands in the *same* piece it started
    in, only that it lands in some piece, exactly once, somewhere.

    The duplication half is counted against the SOURCE's own multiset, not
    against one occurrence each. The critic's opening essay quotes the poet,
    and some of what it quotes is printed again as a ghazal later in the same
    book — تجاوز's بدن کے اپنے تقاضے ہیں، روح کے اپنے appears both in Dr
    Saadat Saeed's essay and in the غزل it is quoted from. The source holds
    that line twice, so emitting it twice is conservation, not duplication.
    Emitting it more often than the source prints it still fails.
    """
    kinds = classify(paragraphs)
    expected = collections.Counter(
        para.text.strip()
        for para, kind in zip(paragraphs, kinds)
        if kind == VERSE and para.text.strip()
    )
    in_source = collections.Counter(
        para.text.strip() for para in paragraphs if para.text.strip()
    )
    emitted = collections.Counter(
        line.strip()
        for segment in segments
        for line in segment.body.split("\n")
        if line.strip()
    )
    errors = []
    lost = expected - emitted
    if lost:
        total = sum(lost.values())
        sample = ", ".join(repr(text[:40]) for text in list(lost)[:3])
        errors.append(
            f"verse conservation failed: {total} of {sum(expected.values())} "
            f"verse paragraphs did not reach a piece: {sample}"
        )
    doubled = collections.Counter({
        text: emitted[text] - in_source[text]
        for text in expected
        if emitted[text] > in_source[text]
    })
    if doubled:
        total = sum(doubled.values())
        sample = ", ".join(repr(text[:40]) for text in list(doubled)[:3])
        errors.append(
            f"verse conservation failed: {total} verse paragraph(s) reached "
            f"more than one piece: {sample}"
        )
    return errors


def verse_errors(segments: list[Segment]) -> list[str]:
    """Gate E — every sher kept both of its misra."""
    errors = []
    for segment in segments:
        if segment.kind not in VERSE_KINDS:
            continue
        stanzas = [s for s in segment.body.split("\n\n") if s.strip()]
        for index, stanza in enumerate(stanzas, start=1):
            lines = [ln for ln in stanza.split("\n") if ln.strip()]
            if len(lines) % 2 and len(stanzas) > 1:
                errors.append(
                    f"{segment.kind}/{segment.title[:30]}: sher {index} has {len(lines)} misra"
                )
    return errors


def _ghazal_line_skeletons(slug: str) -> list[str]:
    """The committed site text of one known ghazal, one skeleton per line."""
    return [
        line for line in
        (skeleton(raw) for raw in site_text(slug).splitlines())
        if line
    ]


# Which کلیات volume prints each known ghazal. The 11 are spread across the
# two — 3 in جلد ۱, 8 in جلد ۲ — so a per-book gate must ask each volume only
# for the ghazals it actually contains: running all 11 against جلد ۱ alone
# reports the 8 that live in جلد ۲ as lost, every run. That is the same
# guaranteed false alarm that had to be unwired from gate C, arriving by a
# different route.
#
# Written out rather than discovered at run time, and deliberately: "which
# ghazals is this volume missing" is the question the gate exists to answer,
# so letting it answer that question from the segmentation it is checking
# would excuse a genuinely lost ghazal as belonging to the other book. Every
# one of the 11 is still gated, in the volume that prints it — a slug moved
# to the wrong volume here fails loudly in both.
KULLIYAT_VOLUMES: dict[str, tuple[str, ...]] = {
    "kulliyat-jild-1": (
        "agar-farman-roaii-sahab-i-toqir-ka-haq-hai",
        "ishq-se-aur-kar-dania-se-hazar-karta-hun-mein",
        "jahan-bhar-mein-mare-dil-sa-koi-gahar-ho-nahin-sakta",
    ),
    "kulliyat-jild-2": (
        "bian-us-bazm-mein-meri-kahani-ho-rahi-hai",
        "chalne-laga-hai-phir-se-mira-dil-ruka-hoa",
        "dikhe-ghalat-kaha-koi-soche-ghalat-kaha",
        "garadash-i-jam-kahin-garadash-i-mina-sakat",
        "hanas-raha-hai-jo-mari-halat-pah-jane-kaun-hai",
        "jahan-mein-dalte-rahte-hain-masioa-ki-tarah",
        "maoraie-saragh-hun-main-bhi",
        "ninad-warasah-hai-mira-khwab-amanat-hai-mari",
    ),
}


# How far a holder's own line count may exceed the site copy's before the
# piece is judged to hold something beyond the ghazal itself. Measured across
# all 11 real holders in the real جلد ۱ / جلد ۲ streams (holder lines minus
# site lines):
#
#     slug                                                    diff
#     agar-farman-roaii-sahab-i-toqir-ka-haq-hai                 0
#     bian-us-bazm-mein-meri-kahani-ho-rahi-hai                  0
#     chalne-laga-hai-phir-se-mira-dil-ruka-hoa                  0
#     dikhe-ghalat-kaha-koi-soche-ghalat-kaha                    0
#     garadash-i-jam-kahin-garadash-i-mina-sakat                +2
#     hanas-raha-hai-jo-mari-halat-pah-jane-kaun-hai              0
#     ishq-se-aur-kar-dania-se-hazar-karta-hun-mein               0
#     jahan-bhar-mein-mare-dil-sa-koi-gahar-ho-nahin-sakta       +2
#     jahan-mein-dalte-rahte-hain-masioa-ki-tarah                 0
#     maoraie-saragh-hun-main-bhi                                -3
#     ninad-warasah-hai-mira-khwab-amanat-hai-mari                0
#
# The spread runs -3 to +2, edition variance in both directions — the site
# copy and the printed کلیات are different editions, so a holder may
# legitimately lack a line the site has, or carry a line (or a line split)
# the site does not; see _ghazal_line_skeletons and gate C's own 169-139
# shortfall for the same variance measured a different way. A weld onto the
# end appends a whole second poem — every ghazal in these two volumes runs
# 12-30 lines — so a small margin past the measured +2 separates the two
# comfortably without hugging the measured figure: 5 clears every real
# holder with room while catching a fusion that appends even the shortest
# poem this corpus holds.
HOLDER_LINE_COUNT_TOLERANCE = 5


def segmentation_groundtruth_errors(
    segments: list[Segment], slugs: tuple[str, ...] = KNOWN_GHAZALS
) -> list[str]:
    """Each of the 11 known ghazals must be exactly one piece.

    They reached the site from WordPress, independently of this decoder, and
    live only in the کلیات volumes. A ghazal cut in half by a running page
    header, or fused with the one after it, fails here and nowhere else — the
    conservation gate sees the text survive either way, and the count gates
    only ever counted.

    Matched on the letter skeleton, since the site text and the printed
    edition are different editions — the same reason the codepage's
    ground-truth gate compares skeletons rather than demanding verbatim
    reproduction.

    Matched LINE BY LINE rather than by asking whether the ghazal's whole
    skeleton is a substring of the piece's, and that difference is the whole
    design. Measured across both volumes, 30 of the 169 ground-truth lines
    appear NOWHERE in the decoded corpus — not in another piece, not in a
    paragraph, nowhere. That is exactly the 169-139 shortfall gate C already
    records, and it is edition variance in the printed book, not text this
    decoder mislaid: conservation_errors is silent, and no segmentation can
    conjure a line the source does not contain. A whole-skeleton substring
    test therefore reports 10 of 11 ghazals broken no matter how perfect
    segmentation is, which is precisely the false alarm gate C had to be
    amended to stop raising (see MIN_WHOLE_GHAZALS, which stands at 1 for
    this same reason). Per-line matching asks the question segmentation can
    actually answer: of the lines the printed edition does reproduce, do they
    all land in ONE piece?

    Three conditions, because a holder count alone is half a gate, and an
    opening check alone is only half of the other half:

    * Exactly one piece holds the ghazal — a piece "holds" it when any of the
      ghazal's lines is in that piece. A ghazal split by a page header puts
      its opening in one piece and its tail in another, and reports 2.
    * That piece OPENS with the ghazal. This catches fusion where the known
      ghazal TRAILS — a missed matlaa welds an earlier, unknown poem onto the
      front of it. Both poems land in one piece, so the holder count alone
      sees 1 and stays silent; the first line of that piece is the unknown
      poem's, not this ghazal's, and that mismatch is what this condition
      catches. It catches nothing about what follows the ghazal's own last
      line — a piece that opens correctly and then keeps going is invisible
      to it, which is the asymmetry the next condition closes.
    * That piece does not run MATERIALLY PAST the ghazal's last line. This
      catches the mirror fusion, where the known ghazal LEADS and an unknown
      poem is welded onto its end — invisible to both conditions above, since
      the holder count still reads 1 and the ghazal still opens the piece.
      Measured across the 11 real holders in both volumes, a holder's own
      line count differs from the site copy's by -3 to +2 — edition
      variance, since the site text and the printed کلیات are different
      editions and either can hold a line, or a line split, the other
      lacks (see `_ghazal_line_skeletons` and gate C's own 169-139 shortfall
      for the same variance measured a different way). See
      HOLDER_LINE_COUNT_TOLERANCE for where the bound is set relative to
      that measured spread.

    Only VERSE_KINDS pieces are considered. The فہرست and the critic's essay
    both reproduce lines of these ghazals — measured, they hold 1-2 lines of
    three different slugs — and counting those prose pieces as holders would
    report a false split on every run.

    `slugs` narrows the check to one volume's share of the 11 (see
    KULLIYAT_VOLUMES); the default gates all of them, which is what the
    cross-volume test does.
    """
    poems = [
        (piece, skeleton(piece.body)) for piece in segments
        if piece.kind in VERSE_KINDS
    ]
    errors = []
    for slug in slugs:
        lines = _ghazal_line_skeletons(slug)
        holders = [
            piece for piece, body in poems
            if any(line in body for line in lines)
        ]
        if len(holders) != 1:
            errors.append(
                f"{slug} is held by {len(holders)} pieces, not 1: the ghazal "
                f"reached the site independently of this decoder, so it must "
                f"segment as a single piece"
            )
            continue
        holder = holders[0]
        holder_lines = [
            line for line in
            (skeleton(raw) for raw in holder.body.split("\n")) if line
        ]
        opening = holder_lines[0] if holder_lines else ""
        if not any(
            opening.startswith(line) or line.startswith(opening)
            for line in lines
        ):
            errors.append(
                f"{slug} does not open the piece holding it (order "
                f"{holder.order}, which begins {holder.title[:30]!r}): "
                f"the ghazal is fused behind another"
            )
        elif len(holder_lines) > len(lines) + HOLDER_LINE_COUNT_TOLERANCE:
            errors.append(
                f"{slug}'s holder (order {holder.order}) runs {len(holder_lines)} "
                f"lines against the site copy's {len(lines)} — more than the "
                f"{HOLDER_LINE_COUNT_TOLERANCE}-line tolerance for edition "
                f"variance, so something else was likely welded onto its end"
            )
    return errors


# How many of کلیات جلد ۱'s front-matter verse-length lines matched a poem's
# matlaa when this was measured, and the same figure for جلد ۲. A FLOOR in the
# manner of the codepage's 139/169 baseline, and emphatically NOT a census:
# جلد ۱ prints 136 verse-length lines in its front matter against 570 poems,
# because its فہرست indexes collections by range and quotes only a partial
# selection of opening lines. 78 of 570 is an artefact of that partial index,
# not coverage of the book, and nothing should ever be inferred from the gap.
#
# Kept per book rather than as one number for the same reason gate C is not
# wired per book: جلد ۲ measures 14 of 56, so a single shared floor would
# make جلد ۲ fail every run — the guaranteed false alarm this gate exists to
# avoid being.
TOC_FIRST_LINE_BASELINE = {
    "kulliyat-jild-1": 78,
    "kulliyat-jild-2": 14,
}


def toc_first_line_baseline_errors(
    paragraphs: list[Paragraph], segments: list[Segment], minimum: int
) -> list[str]:
    """At least `minimum` front-matter verse lines must match a poem's matlaa.

    A regression guard, not a count of anything meaningful. The book's فہرست
    quotes some opening lines among its entries; each one that still matches
    the matlaa of some segmented poem is one more piece of evidence that the
    boundaries landed where the book itself says they do. If a segmentation
    change drops the number, matlaa detection moved.

    NOT a census — see TOC_FIRST_LINE_BASELINE. The فہرست indexes only a
    fraction of the poems, so this number can never reach the poem count and
    must never be read as coverage.

    Front matter is everything before `body_start_index`, restricted to
    verse-length paragraphs so that page numbers, headings and the title
    block are not counted as unmatched lines.
    """
    start = body_start_index(paragraphs)
    front = [
        line for line in
        (skeleton(para.text.strip()) for para in paragraphs[:start]
         if _is_verse_length(para.text.strip()))
        if line
    ]
    matlaas = {
        line for line in (
            skeleton(piece.body.split("\n")[0]) for piece in segments
            if piece.kind in VERSE_KINDS and piece.body.strip()
        ) if line
    }
    matched = sum(1 for line in front if line in matlaas)
    if matched < minimum:
        return [
            f"only {matched} of {len(front)} front-matter verse lines match a "
            f"poem's matlaa (baseline: {minimum}) — matlaa detection has "
            f"regressed. This is a floor, not a census: the فہرست indexes only "
            f"part of the book."
        ]
    return []
