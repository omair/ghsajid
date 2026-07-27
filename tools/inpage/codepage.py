"""The InPage byte <-> Unicode table.

InPage stores text as (font_selector, char_code) byte pairs. Only ~132 distinct
char codes occur across the corpus, and they are per-LETTER codes, not
per-ligature glyph ids — so a lookup table is sufficient and no font
reverse-engineering is required.

Every entry carries the evidence that established it. A wrong entry corrupts
every occurrence of that letter, silently, in every poem at once; character
counts and round-trip checks are both blind to it. Do not add an entry you
cannot justify here.
"""

from typing import Iterable

_ALPHABET = "ابپتٹثجچحخدڈذرڑزژسشصضطظعغفقکگلمن"
_ALPHABET_EVIDENCE = (
    "0x81-0xA0 follow the Urdu alphabet order; confirmed by decoding "
    "the prose preface of TAJAWUZ into fluent Urdu"
)

# byte code -> (unicode text, evidence)
CODEPAGE: dict[int, tuple[str, str]] = {
    0x20: (" ", "literal ASCII space; 19% of all codes, the word separator"),
}
for _i, _ch in enumerate(_ALPHABET):
    CODEPAGE[0x81 + _i] = (_ch, _ALPHABET_EVIDENCE)

CODEPAGE.update({
    0xA1: ("ں", "noon-ghunna; from زبانوں / میں in the TAJAWUZ preface"),
    0xA2: ("و", "wao; from اور / خوش in the TAJAWUZ preface"),
    0xA3: ("ئ", "hamza-ye; from مسائل / کئی in the TAJAWUZ preface"),
    0xA4: ("ی", "choti ye; 7.4% freq, from حسین / کی"),
    0xA5: ("ے", "bari ye; from سے / ہے"),
    0xA6: ("ہ", "gol he; from ہیں / عہد"),
    0xA7: ("ھ", "do-chashmi he; 1.9% freq, the remaining he form"),
    0xAC: ("ُ", "pesh/damma; from اُردو / اُنہوں"),
    0xF3: ("۔", "Urdu full stop; sentence-final throughout the preface"),
})

# --- Marks and letters solved by aligning the کلیات against the 11 ghazals
# already on the site (tools/inpage/groundtruth.py). Each entry below was read
# off a character-level diff of a decoded paragraph against its committed
# WordPress-era text, not guessed from position in the table.

CODEPAGE.update({
    0xAA: (
        "ِ",
        "zer/kasra; the izafat. Site line رنگِ ادب پبلی کیشنز and "
        "خلق ِ خدا align this code onto U+0650 (11 direct diff votes, "
        "4383 occurrences in MAZAMEER (1) — izafat is everywhere in ghazal)",
    ),
    0xAB: (
        "َ",
        "zabar/fatha; site مَیں (ماورائے سراغ ہوں مَیں بھی) and سَر put "
        "U+064E exactly here (7 direct diff votes)",
    ),
    0xAD: (
        "ّ",
        "tashdid/shadda; site چکّر in ایک چکّر ہے مرے پاؤں میں زنجیر نہیں, "
        "plus مٹّی / تکلّف / تمنّا in the TAJAWUZ preface (7 direct diff votes)",
    ),
    0xB3: (
        "ٓ",
        "madda, written after its alef: 0x81 0xB3 spells آ — ا+0xB3+نے والوں "
        "= آنے والوں, ا+0xB3+یندہ = آیندہ, ا+0xB3+فس = آفس. 29 site آ "
        "aligned onto the pair, so this code is the combining mark, not آ",
    ),
    0xC8: (
        "آ",
        "alef-madda as one code — the other spelling of آ. Bare 0xC8 begins "
        "آسماں / آئنے / آدھی رات / آخری with no alef before it; 17 site آ "
        "aligned onto this single code",
    ),
    0xBF: (
        "ٔ",
        "hamza above, written after its bearer: ہ+0xBF is the ۂ of izafat — "
        "خانۂ دنیا, حلقۂ دیوار, نغمۂ شادی, قریۂ وہم",
    ),
    0xC7: (
        "ً",
        "tanwin/fathatan, written after its alef: قطعاً, نسبتاً, خالصتاً in "
        "the TAJAWUZ preface — Arabic adverbs, all with the same ending",
    ),
    0xCF: (
        "ؔ",
        "takhallus mark: occurs only after a pen-name — ساجدؔ (the poet's "
        "own), دردؔ, شاعرؔ — and never inside a word",
    ),
    0xED: (
        "،",
        "Urdu comma; 12 site ، aligned onto it, e.g. رنگِ ادب پبلی کیشنز ، "
        "کراچی and the address اُردو بازار، کراچی",
    ),
    0xEE: (
        "؟",
        "Urdu question mark; 2 site ؟ aligned onto it at end of "
        "interrogative misras",
    ),
    0xFE: (
        "‘",
        "opening single quote, doubled to make a double quote: 0xFE 0xFE "
        "opens and 0xFD 0xFD closes the quoted متاع and عناصر, and a single "
        'site " aligned onto the 0xFE pair. Role (open) is from position; '
        "U+2018 is the convention for the curly form",
    ),
    0xFD: (
        "’",
        "closing single quote, the partner of 0xFE: 0xFD 0xFD closes every "
        'run 0xFE 0xFE opens, and a single site " aligned onto the pair',
    ),
})

# --- Punctuation that occurs only in TAJAWUZ and the MAZAMEER volumes, so the
# کلیات-only pass that produced the block above never saw it.

CODEPAGE.update({
    0xDA: (
        "!",
        "exclamation mark. Direct alignment vote: the site nazm taqtib.md "
        "line دو قدم اُس سے زیادہ چل سکوں! matches a decoded MAZAMEER "
        "paragraph letter-for-letter with 0xDA sitting exactly under the ! "
        "(the site text reached the archive through the WordPress migration, "
        "not through this decoder). Corroborated by its 88 non-final "
        "occurrences, every one after an exclamatory phrase or a vocative — "
        "شہزادی!/میاں!/دوستو! ناراض نہ ہونا, مَیں کیا کروں گا! مجھے خود پتا "
        "نہیں — and by 517 line-final occurrences, largely on the radeef "
        "کیا کہنے!. 605 occurrences and no other code in the table is !",
    ),
    0xE9: (
        ":",
        "colon. Its 16 non-final occurrences are all a colon introducing what "
        "follows and nothing else can stand there: غزل پر دواعتراض ہمیشہ کیے "
        "گئے: ایک قافیے ردیف کی قید، دوسرا ریزہ خیالی, ساجد کے ہاں دو "
        "استعارے بار بار اُبھرتے ہیں: ایک آئینہ دوسرا شمشیر, بہت کچھ لکھا "
        "ہے: افسانہ، تنقید، نظم…, کسی نے کہا تھا: غزل کے لیے تغزل شرط ہے, "
        "کچھ مزید اشعار دیکھیے:. This settles the colon-vs-tab ambiguity "
        "left open earlier: a tab cannot introduce an enumeration. The "
        "colophon labels شاعر:/ناشر:/قیمت:/پرنٹر:/ترجمہ: are the same code",
    ),
    0xE2: (
        "(",
        "opening parenthesis. Written before its content, 0xE1 after it "
        "(same logical-order convention as 0xFE/0xFD): حمدِ بہار(بیس غزلیں), "
        "حمدِ قدیم(تیس غزلیں), (جلد اوّل), (کلیاتِ غلام حسین ساجدؔ), "
        "(پروفیسر امریطس), (ترجمہ: محمد سلیم الرحمن), (موسم، عناصر، کتابِ "
        "صبح، آیندہ، معاملہ اور رُوداد). Every one of the 197 occurrences is "
        "a parenthetical gloss — a count, a volume number, a title, a "
        "byline — never a quotation, which the book spells 0xFE/0xFD",
    ),
    0xE1: (
        ")",
        "closing parenthesis, the partner of 0xE2: it closes every run 0xE2 "
        "opens, 201 occurrences against 197 (the surplus are runs whose "
        "opener sits in a preceding paragraph)",
    ),
    0xDF: (
        "-",
        "dash separating two items. Role established by all 14 occurrences: "
        "the acknowledgements list pairs a critic with the book he wrote "
        "about — مرزا حامد بیگ- ‘‘موسم’’, خالد اقبال یاسر- ‘‘عناصر’’, شمس "
        "الرحمن فاروقی- ‘‘آیندہ’’, بیدل حیدری- ‘‘معاملہ’’, صابر ظفر- "
        "‘‘رُوداد’’ — and it also spans a month range inside running prose, "
        "جولائی- اگست میں ایک ہی تخلیقی لہر کے تحت, which rules out a line "
        "break, plus dated signature lines ۵-مئی ۲۰۲۳ء and سنِ اشاعت-پہلی "
        "بار. The exact codepoint is the hyphen-minus an InPage typist's `-` "
        "key produces; like 0xFE/0xFD the role is observed and the codepoint "
        "is convention. It never enters the skeleton tier",
    ),
    0xBD: (
        "ٰ",
        "dagger alef (superscript alef), written after its bearer like the "
        "madda 0xB3 and the hamza 0xBF. Every one of its 47 occurrences "
        "completes a word that is only spelt with U+0670 and is not a word "
        "without it: دعوی+0xBD = دعویٰ (کس کو دعویٰ ہے سرفروشی کا), "
        "اعلی+0xBD = اعلیٰ, ادنی+0xBD = ادنیٰ, ہیولی+0xBD = ہیولیٰ, "
        "ال+0xBD+ہ آباد = الٰہ آباد. All five spellings occur in the site "
        "corpus written with U+0670",
    ),
})

# Digits, keyed off dates in the کلیات colophons. The stream stores a number
# in visual (left-to-right) order, so the run reads reversed: 0xD5 0xD8 0xD9
# 0xD1 after نومبر is 1985, 0xD3 0xD0 0xD0 0xD2 after مارچ is 2003. The nine
# cited dates directly exercise 0xD0-0xD5, 0xD7, 0xD8, 0xD9 — every occurrence
# resolves to a plausible Gregorian year (1985, 1987, 1989, 1993, 2003, 2004)
# or a day of the month (15, 23, 28) under 0xD0+n == n, and under no other
# offset. 0xD6 (۶) never appears in any cited date; it is not directly
# observed and is instead inferred from contiguity with the rest of the block.
_DIGIT_EVIDENCE = (
    "0xD0+n is the digit n; from colophon dates — نومبر ۱۹۸۵ء, فروری ۱۹۸۹ء, "
    "اپریل ۱۹۹۳ء, مارچ ۲۰۰۳ء, دسمبر ۲۰۰۴ء (digits run left-to-right in the "
    "stream, so they read reversed). These dates directly exercise "
    "0xD0-0xD5, 0xD7, 0xD8, 0xD9; 0xD6 is not directly observed in any cited "
    "date and is inferred from contiguity with the rest of the block, not "
    "from a direct occurrence"
)
def _add_digit_block() -> None:
    """Assign 0xD0-0xD9 to the digits, asserting no key is already present.

    A loop indexing into CODEPAGE would silently clobber a pre-existing key
    if one ever collided with this range; an explicit assert makes that
    impossible instead of merely unlikely. Loop temporaries stay local to
    this function rather than leaking into the module namespace.
    """
    for offset, digit in enumerate("۰۱۲۳۴۵۶۷۸۹"):
        code = 0xD0 + offset
        assert code not in CODEPAGE, f"{code:#04x} already mapped, refusing to clobber it"
        CODEPAGE[code] = (digit, _DIGIT_EVIDENCE)


_add_digit_block()

# Genuine duplicate codes, if any are discovered: alias -> canonical code.
# Declared explicitly so the injectivity test stays meaningful.
ALIASES: dict[int, int] = {}

_REVERSE: dict[str, int] = {
    text: code
    for code, (text, _) in CODEPAGE.items()
    if code not in ALIASES
}


def decode_byte(code: int) -> str | None:
    """Return the Unicode text for one InPage char code, or None if unmapped."""
    entry = CODEPAGE.get(code)
    return entry[0] if entry else None


def encode_char(text: str) -> int | None:
    """Return the canonical InPage char code for `text`, or None."""
    return _REVERSE.get(text)


def unmapped(codes: Iterable[int]) -> set[int]:
    """Return the subset of `codes` this table cannot decode."""
    return {code for code in codes if code not in CODEPAGE}
