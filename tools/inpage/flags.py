"""Flags a piece can carry, and which of them bar it from the site.

Their own module because the checks that SET them and the code that ACTS on
them sit on opposite sides of the pipeline: `checks` sets three of them,
`segment` sets the fourth, and `promote`, the count gate and the book
records all read the set. Anywhere else, one of those imports the other.

Every flag here marks real text the source contains. Nothing is dropped —
the piece is staged, and the report names it — but a piece carrying one of
these is not a poem and not criticism, so it does not reach content/.
"""

# Text that is not believable as text: end-of-stream scratch.
GARBAGE_FLAG = "likely-decode-garbage"

# A piece whose whole body is one line. A poem cannot be one line — a فرد is
# a whole sher, two misras — so this is a byline, a stray title, or half a
# sher whose partner was lost. عناصر's ابتدائیہ byline was staged as a نظم
# AND counted as its hundredth poem, which hid a ghazal missing from ہَوا.
SINGLE_LINE_FLAG = "single-line-piece"

# A `reviews` piece that is really the book's own فہرست: a list of opening
# misras rather than criticism.
INDEX_FLAG = "first-line-index"

# A collection's title-page block — imprint, dedication, epigraph couplet —
# which segments as a poem because its lines are verse-length. Left
# unattributed it already stays out of every contents list and every count,
# but it would still publish as poetry: an imprint and a dedication to the
# poet's parents, presented as poems of موسم.
TITLE_PAGE_FLAG = "collection-title-page"

UNPUBLISHABLE = frozenset(
    {GARBAGE_FLAG, SINGLE_LINE_FLAG, INDEX_FLAG, TITLE_PAGE_FLAG}
)
