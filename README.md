# policydb

Pull payer **medical & drug coverage policies** into a single queryable SQLite
dataset, then compare them across competitors — via CLI or a deployable website.

Sources so far:
- **Blue Cross Blue Shield of Florida** (https://mcgs.bcbsfl.com) — 754 policies
- **Oscar Health** (https://www.hioscar.com/clinical-guidelines) — medical + pharmacy

The design is source-agnostic — each new payer is one new *adapter*; extraction,
schema, queries, cross-payer matching, and the website are shared.

## Website

`web/` is a React + Vite app (deploys to **Firebase Hosting**, data shipped as a
static bundle — no DB billing) that shows **side-by-side comparisons** of equivalent
policies across payers, plus full-text browse/search. Cross-payer topics are matched
automatically (`policydb/match.py`). See [`web/README.md`](web/README.md) for build
and deploy steps.

```bash
python scripts/export_web.py --db data/policies.db --out web/public/data  # build bundle
cd web && npm install && npm run dev                                       # preview
```

## Layout

```
policydb/
  sources/base.py      SourceAdapter interface (catalog + fetch_document)
  sources/bcbsfl.py    BCBS-FL adapter (see "How BCBS-FL works" below)
  sources/oscar.py     Oscar adapter (Next.js/Contentful; stateless, parallel)
  extract.py           PDF -> text + parsed fields (policy#, subject, dates, CPT/HCPCS)
  match.py             cross-payer topic clustering (IDF-cosine over titles)
  db.py                SQLite schema + FTS5 full-text index (self-migrating)
  pipeline.py          orchestration: catalog -> fetch -> extract -> store
scripts/
  pull.py              CLI: pull a source into the dataset
  query.py             CLI: stats / search / show / compare
  export_web.py        build the website's static data bundle
web/                   React + Vite comparison site (Firebase Hosting)
data/                  the SQLite dataset lives here (git-ignored)
```

## Usage

```bash
pip install requests pypdf            # deps

# Pull (BCBS-FL is ~757 documents; sequential, allow ~20-40 min)
python scripts/pull.py bcbsfl --db data/policies.db
python scripts/pull.py bcbsfl --db data/policies.db --limit 20   # quick test

# Query
python scripts/query.py --db data/policies.db stats
python scripts/query.py --db data/policies.db search "continuous glucose monitor"
python scripts/query.py --db data/policies.db show 09-E0000-14
python scripts/query.py --db data/policies.db compare "cgm" "glucose monitor"
```

The dataset is a plain SQLite file — query it with any SQL tool, BI client, or
pandas. Full-text search uses the `policies_fts` FTS5 table; structured fields
(MCG number, dates, category, CPT codes) live in `policies`.

## Schema

`policies` — one row per document (`source`, `doc_key`):
`policy_id` (payer MCG#), `title` (site nav), `subject` (authoritative title from
the PDF), `effective_date`, `revised_date`, `page_count`, `cpt_codes` (JSON),
`full_text`, `content_hash` (change detection on re-pulls), `source_url`.
`placements` holds each category a document is filed under.

## How BCBS-FL works (for maintainers)

The site is ASP.NET WebForms + Telerik RadPanelBar. Two non-obvious facts drive
the adapter:

1. **The catalog is fully in the landing page.** Titles live in `<span class="rpText">`
   and internal file paths in a Telerik `itemData` JSON tree of identical shape.
   Each document has a *hierarchical index* (e.g. `1:1:230`).

2. **PDFs are not directly addressable.** `/mcg?FilePath=<x>` returns whatever the
   server *session* currently has selected — `<x>` is ignored. To select a
   document you must replay the RadPanelBar click postback (`__EVENTTARGET`,
   `__EVENTARGUMENT=<index>`, and `RadPanelBar1_ClientState` with the selected +
   expanded items), carrying ViewState forward. The response embeds a fresh
   numeric handle; fetching `/mcg?FilePath=<handle>` in the same session returns
   the PDF.

   Gotchas the adapter handles: the *first* postback after loading doesn't take
   (we prime once), and re-clicking the already-selected item is a no-op (we
   crawl distinct items in order, and prime on the last leaf so it differs from
   the first). Because the session is stateful, fetching is **sequential**.

Titles/categories from the nav are treated as hints — the authoritative title,
MCG number, and dates are parsed from the PDF content itself.

## Adding a competitor

Implement a `SourceAdapter` (`catalog()` yielding `CatalogEntry` rows, and
`fetch_document()`), register it in `policydb/__init__.py`, and run `pull.py`.
Stateless sites can set `sequential = False` to fetch in parallel.
