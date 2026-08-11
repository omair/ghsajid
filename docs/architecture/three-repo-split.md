# Splitting ghsajid into three repositories

**Status:** proposal, for review. Nothing here is built yet.

## Why

Today one repository holds three things that change for different reasons and
by different hands:

1. **Generation tooling** — `tools/inpage/` (InPage `.INP` → markdown) and
   `tools/migrate/` (the one-time WordPress bootstrap), plus their `tests/`.
2. **The archive itself** — the markdown in `content/`.
3. **The public website** — the Astro app in `src/` and the Cloudflare worker.

The tooling is developer work. The website is developer work. But the *content*
is your father's work, and right now the only way to add or change a piece is to
run scripts. We want him to add and edit pieces himself, through a web UI, without
touching code — and we want the generator to keep running without ever clobbering
what he writes by hand.

The split below makes each of those a separate concern, and the **provenance
field** (§3) is the single mechanism that lets tool-generated and
human-authored content live side by side safely.

## Decisions locked in

- **Public site stays Astro.** All existing RTL Nastaliq typography, the
  `Piece`/`Base` components, the zod-validated content schema, the ghazal
  search, and the remark-breaks misra handling are preserved. No Jekyll rewrite.
- **Your father's editor is Sveltia CMS** — a modern, git-backed CMS with strong
  Urdu/RTL support, Decap-config-compatible.
- **Plan first.** This document is the plan; execution is phased (§6).

## 1. The three repositories

### A. `ghsajid-generator` — "meta: InPage → markdown"

The generator, extracted whole.

| Moves in                        | Notes                                            |
| ------------------------------- | ------------------------------------------------ |
| `tools/inpage/`                 | InPage decode → segment → review → promote       |
| `tools/migrate/`                | WordPress WXR bootstrap (historical, kept as record) |
| `tools/fetch_media.py`          | media fetching                                   |
| `tests/` (all 25 files)         | they import `tools`, so they belong here         |
| `tools/__init__.py`, packaging  | stays a stdlib-only Python package               |

Inputs stay local and git-ignored, exactly as now: `inp/`, `in/`, `data/export.xml`,
`tools/bin/`, `out/` staging.

**Output:** markdown pieces + `worker/postmap.json`, written into a checkout of
repo B. Every emitted file is stamped `origin: tool` (§3). The emitter **never
overwrites a file marked `origin: human`** (§3, the linchpin rule).

**How output reaches repo B:** the generator opens a **pull request** against
`ghsajid` rather than committing directly. This mirrors the pipeline's existing
"review before promote" ethos — tool output is proposed, a human merges it.

### B. `ghsajid` — source + public site

What the world sees. No generation scripts.

| Stays / lives here                                  |
| --------------------------------------------------- |
| `src/` (Astro app), `public/`                       |
| `content/` (the archive, every piece with provenance)|
| `worker/` (asset serving + `?p=` legacy redirects)  |
| `astro.config.mjs`, `package.json`, `wrangler.jsonc`|
| `CONTRIBUTING.md`, `README.md`                       |

| Leaves                          |
| ------------------------------- |
| `tools/` → repo A               |
| `tests/` → repo A               |

This is the repo that already deploys to Cloudflare; that pipeline is unchanged.
`content.config.ts` gains the provenance field in its schema (§3).

### C. `ghsajid-studio` — your father's editor

A small deployment of **Sveltia CMS**: an `admin/` with `index.html` +
`config.yml`, served at its own subdomain (e.g. `studio.ghsajid.com`).

- Authenticates the editor via a **GitHub OAuth app**; a tiny Cloudflare Worker
  handles the OAuth token exchange (Sveltia requires this, ~40 lines).
- Reads and writes `content/` **in repo B** through the GitHub backend — every
  save is a real commit.
- Every piece created or edited here is stamped **`origin: human`** (§3), so the
  generator will never overwrite it.
- Exposes friendly, RTL-aware fields for each collection, including the existing
  `tags` array so he can tag freely.

Why a separate repo (not `ghsajid.com/admin`): it keeps the editor's auth,
deploy, and access wholly apart from the public site, and lets him have a stable
"come here to add things" address that never changes even if the site does.

## 2. How content flows

```
                  InPage / WordPress originals (local, git-ignored)
                                  │
                        ghsajid-generator (repo A)
                                  │  stamps origin: tool
                                  │  skips origin: human
                                  ▼
                        Pull request  ──────────────►  ghsajid (repo B)
                                                          content/
                                                            ▲
                          PR, origin: human                 │
                          (auto-merge if a safe edit,        │
                           else held for review)            │
                        ghsajid-studio (repo C)  ───────────┘
                        (Sveltia, your father edits)
                                  │
                                  ▼
                        Astro build → Cloudflare  →  ghsajid.com
```

Two writers, one archive, no collisions — because of the provenance field.

## 3. The provenance model (the linchpin)

Every piece carries who last authored it:

```yaml
origin: tool     # generated; the generator may overwrite it
# ── or ──
origin: human    # written or corrected by a person; the generator must NOT touch it
```

Optionally, richer detail without changing the rule:

```yaml
provenance:
  origin: tool
  generator: inpage        # or "migrate"
  generated: 2026-07-21
```

**The one rule everything depends on** — in the generator's emit step, for each
target file:

| Target state                     | Generator does           |
| -------------------------------- | ------------------------ |
| does not exist                   | write it, `origin: tool` |
| exists, `origin: tool`           | overwrite                |
| exists, `origin: human`          | **skip** (and log)       |

When your father edits a *tool-generated* piece in the studio, the save flips
that piece to `origin: human` — so his correction is protected from the next
regeneration too. This is the formal version of what the pipeline already does
informally with `restamp` ("a human hand-corrected after approval").

`content.config.ts` gets `origin: z.enum(["tool", "human"])` and the optional
`provenance` object, so a missing or misspelled value fails the build.

## 4. Sveltia CMS shape (repo C)

`config.yml` sketch — one collection per content type, mirroring the zod schema:

- **backend:** `github`, repo `omair/ghsajid`, with
  `publish_mode: editorial_workflow` so every save opens a pull request (see the
  review model below).
- **collections — all existing categories:** every category he'd contribute to
  is visible — **`ghazals`, `nazms`, `reviews`, `memoir`, `videos`** — matching
  what a reader sees in the site nav. `books` and `containers` are never
  exposed; they are kept in sync automatically (see couplings).
- **fields — as simple as each category allows,** `dir: rtl` where the value is
  Urdu: the verse categories (`ghazals`, `nazms`) show title + body; `reviews`
  add the reviewed book/author; `videos` need their source + link fields
  (`source`, `url`, `video_id`). No tags on any of them.
- **hidden field** `origin` defaulted to `human` on create, so every save he
  makes is correctly stamped.
- **tags are not in his editor.** He won't be tagging; that stays your job.
  Tags remain in the schema (default `[]`), just hidden from the studio. The
  natural moment to add them is the review of a new piece (below) — so tagging
  costs no extra step.

### Review model — the middle ground

He doesn't want everything gated, and he doesn't want everything unguarded.
Sveltia runs in **editorial-workflow** mode, so every save becomes a pull
request; a small **auto-merge GitHub Action** then decides each PR's fate:

| The edit is…                                             | Outcome                        |
| -------------------------------------------------------- | ------------------------------ |
| a text change to an **existing** poem                    | **auto-merged** — live in ~1 min |
| a **new** poem, or a **deletion**                        | **held** for your review       |

Corrections stay frictionless; a work entering or leaving the archive — where a
mistake is costly — waits for you. That review is also **where you add the
tags** to a new poem before merging, so tagging never becomes a separate chore.
From his side it is always one "publish" button; from yours it is a short queue
holding only the consequential changes. The Action reads the PR's file diff
(created/deleted vs. modified) and either merges or applies a `needs-review`
label.

### Couplings kept in sync automatically (decided)

Two indexes depend on separate list files (both noted in `CONTRIBUTING.md`).
Rather than ask him to edit them, a **build step rebuilds them from the pieces**:

- `content/containers/dars-gah.yaml` is regenerated from the `content/memoir/`
  files (ordered by their `part`), so a new chapter can never 404.
- each book's `contents` is regenerated from the pieces that name it via
  `source_book` / `book_order`.

Because these are generated, the studio does not expose them for hand-editing.

## 5. Risks & open questions

1. **Generator → repo B coupling.** PR-based (proposed) keeps a review gate but
   means the generator needs a GitHub token and PR permissions. Direct-commit is
   simpler but unreviewed. — *Recommend PR-based.*
2. **OAuth hosting.** Sveltia needs a token-exchange endpoint. A Cloudflare
   Worker is the natural home (we already use Cloudflare). One-time setup.
3. **Does `migrate/` even belong in the generator repo,** or should it be
   archived read-only? It was a one-shot. — *Recommend: move it, mark it
   historical; it documents how the corpus was born.*
4. **Studio review model — DECIDED.** Editorial-workflow + auto-merge Action:
   text/tag edits to existing pieces go live, new pieces / deletions / renames
   wait for review (§4).
5. **Container & book sync — DECIDED.** A build step regenerates
   `dars-gah.yaml` and each book's `contents` from the pieces; the studio never
   exposes them (§4).
6. **Auto-merge policy.** With his editor limited to title + body on existing
   poems, the rule is simple: **modified file = auto-merge, created/deleted file
   = review.** A title fix on an existing poem thus auto-merges (it's a
   correction); only a genuinely new or removed poem waits. Confirm that's the
   line you want before Phase 2.
7. **Repo names** — `ghsajid-generator`, `ghsajid`, `ghsajid-studio` are
   placeholders; rename freely.

## 6. Execution plan (phased, each phase shippable)

- **Phase 0 — provenance, in place (no split yet).**
  Add `origin` to `content.config.ts`; stamp every existing piece `origin: tool`
  (all current content is tool-derived); teach both emitters to write it and to
  honor the never-overwrite-human rule. Safe and useful on its own.

- **Phase 1 — extract the generator (repo A).**
  Create `ghsajid-generator`; move `tools/` + `tests/`; point its output at a
  checkout of `ghsajid` and switch it to open PRs. Delete `tools/`, `tests/`
  from `ghsajid`; update both READMEs.

- **Phase 2 — stand up the studio (repo C).**
  Create `ghsajid-studio` with Sveltia config for all editable categories
  (`ghazals`, `nazms`, `reviews`, `memoir`, `videos`), per-category RTL fields,
  no tags, `origin: human` default, and `editorial_workflow`. Add the GitHub
  OAuth app + token Worker. Deploy to `studio.ghsajid.com`. Add the
  **auto-merge Action** on `ghsajid` (modified = live, created/deleted =
  review). Verify a text edit auto-merges and a new piece waits for you to tag
  and approve.

- **Phase 3 — close the loops.**
  Build step to regenerate `dars-gah.yaml` and book `contents` from the pieces;
  CI on `ghsajid` validating schema on every studio commit; a short one-page
  guide for your father.

Each phase is independently reviewable and leaves a working system.
