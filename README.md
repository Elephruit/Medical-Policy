# policydb

Pull payer **medical coverage policies** into a single queryable SQLite dataset so
they can be searched and compared across competitors.

First source: **Blue Cross Blue Shield of Florida** Medical Coverage Guidelines
(https://mcgs.bcbsfl.com). The design is source-agnostic — each new payer is one
new *adapter*; extraction, schema, and queries are shared.

## Layout

```
policydb/
  sources/base.py      SourceAdapter interface (catalog + fetch_document)
  sources/bcbsfl.py    BCBS-FL adapter (see "How BCBS-FL works" below)
  extract.py           PDF -> text + parsed fields (MCG#, subject, dates, CPT/HCPCS)
  db.py                SQLite schema + FTS5 full-text index
  pipeline.py          orchestration: catalog -> fetch -> extract -> store
scripts/
  pull.py              CLI: pull a source into the dataset
  query.py             CLI: stats / search / show / compare
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
