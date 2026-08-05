# Contributing

Thank you for helping care for this archive. It gathers the Urdu and Punjabi
work of **Ghulam Hussain Sajid** (غلام حسین ساجد) — poetry, criticism, and
memoir. The most valuable contributions are usually small: a corrected letter,
a restored diacritic, a fixed line break. Accuracy to the source matters more
than anything.

## Ways to help

- **Fix a text error.** Typos, dropped words, wrong diacritics, or a misra
  (hemistich) that has fused with the next line.
- **Improve provenance.** Add a missing `source_book`, publication note, or the
  date and place of composition when you can cite it.
- **Add a missing piece.** A ghazal, nazm, review, or memoir chapter that
  belongs in the corpus but isn't here yet.
- **Report a problem.** If you aren't comfortable editing, open an issue on
  [GitHub](https://github.com/omair/ghsajid/issues) describing what's wrong and
  where.

## Where the content lives

All texts are plain markdown under `content/`, one file per piece:

| Folder                 | Contents                          |
| ---------------------- | --------------------------------- |
| `content/ghazals/`     | Ghazals                           |
| `content/nazms/`       | Nazms                             |
| `content/reviews/`     | Criticism and reviews (تبصرے)     |
| `content/memoir/`      | Memoir chapters (درس گاہ)         |
| `content/videos/`      | Recordings (آواز)                 |
| `content/books/`       | Book definitions (YAML)           |
| `content/containers/`  | Ordered chapter lists (YAML)      |

Each markdown file opens with a YAML frontmatter block, then the text. A ghazal
looks like this:

```markdown
---
title: "خواب کی دنیا الگ ہے، نیند کی دنیا الگ"
slug: "khwab-ki-dania-alag-he-ninad-ki-dania-alag"
language: "urdu"
script: "nastaliq"
source_book: "tajawuz"
book_order: 3
---

خواب کی دنیا الگ ہے، نیند کی دنیا الگ
کیا کوئی آئینہ گر ہے ان چراغوں کا الگ
```

The full set of allowed fields and their types is defined in
`src/content.config.ts` — that file is the source of truth. If a field you add
isn't listed there, the build will reject it.

### Editing conventions

- **One newline between the two misra of a sher; a blank line between ashaar.**
  A single newline renders as a `<br>`; a blank line starts a new stanza. Don't
  collapse them, or both hemistichs fuse into one run-on line.
- **Preserve the source.** Keep the original spelling and diacritics. Don't
  modernize or "correct" the poet — only fix genuine transcription errors.
- **Never guess a fact.** Leave a date, year, or book unset rather than
  inventing one. Omission is honest; a wrong `published` year is not.
- **Keep the slug stable.** The `slug` is the piece's URL. Changing it breaks
  every existing link, so leave it alone once a piece is published.

## Running the site locally

Requires Node ≥ 22.12.

```bash
npm install
npm run dev
```

Then open the printed local URL. Before opening a pull request, confirm the
site still builds — a bad frontmatter field or a broken cross-reference fails
the build:

```bash
npm run build
```

## The migration tool

`content/` was generated once from a WordPress export by `tools/migrate/`
(standard-library Python only). It's kept as the record of how the corpus was
derived. If you touch it, run its tests:

```bash
python3 -m unittest discover -s tests -t . -v
```

For ordinary content edits you don't need to run the migration — edit the
markdown in `content/` directly.

## Opening a pull request

1. Create a branch for your change.
2. Keep each pull request focused — one piece, or one kind of fix.
3. In the description, cite your source for any factual change (which book,
   which page) so an editor can verify it.
4. Make sure `npm run build` passes.

Small, well-sourced corrections are always welcome. Thank you for tending the
archive.
