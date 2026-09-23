# ghsajid.com

Literary archive of **Ghulam Hussain Sajid** (غلام حسین ساجد) — Urdu and
Punjabi poetry, criticism, and memoir.

Content lives in `content/` as markdown. The site is built with Astro and
deployed to Cloudflare Pages.

## Migration

The corpus was migrated once from a WordPress export:

    cp <wordpress-export.xml> data/export.xml
    python3 -m tools.migrate

`tools/migrate/` is kept as the record of exactly how `content/` was derived.
It uses only the Python standard library, so it stays runnable without a
package manager.

## InPage ingestion

Most of the poetry was ingested from the InPage (`.INP`) files the books were
typeset in:

    python3 -m tools.inpage decode  <book-slug>
    python3 -m tools.inpage segment <book-slug>
    python3 -m tools.inpage promote <book-slug>

`segment` stages pieces in `out/` with a review report; `promote` refuses to
run until that report is approved. The `.INP` sources live in `inp/`, which is
not committed.

Unlike `tools/migrate/`, this needs one third-party package, `olefile`, to read
the OLE container InPage files are stored in:

    python3 -m pip install --user -r requirements.txt

## Tests

The InPage tests need `requirements.txt` installed (see above); then:

    python3 -m unittest discover -s tests -t . -v

## Development

    npm install
    npm run dev
