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

## Tests

    python3 -m unittest discover -s tests -t . -v

## Development

    npm install
    npm run dev
