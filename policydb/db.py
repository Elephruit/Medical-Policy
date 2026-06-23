"""SQLite store with an FTS5 full-text index.

One row per (source, doc_key) in ``policies``; the many category placements of a
document are kept in ``placements``. ``policies_fts`` mirrors title + full_text
for keyword search. ``content_hash`` lets re-pulls detect real changes so you can
track when a payer revises a policy.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Iterator, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS policies (
    source          TEXT NOT NULL,
    doc_key         TEXT NOT NULL,
    policy_id       TEXT,             -- payer's policy/guideline number (e.g. 09-E0000-14, CG013)
    version         TEXT,             -- document version, when the payer tracks one
    title           TEXT NOT NULL,    -- catalog title (from the site navigation)
    subject         TEXT,             -- authoritative title parsed from the PDF
    file_type       TEXT,
    source_url      TEXT,
    effective_date  TEXT,
    revised_date    TEXT,
    page_count      INTEGER,
    cpt_codes       TEXT,             -- JSON array
    full_text       TEXT,
    content_hash    TEXT,             -- sha256 of raw document bytes
    extract_ok      INTEGER DEFAULT 0,
    extract_error   TEXT,
    first_seen      TEXT,             -- caller-supplied ISO timestamp
    last_pulled     TEXT,
    PRIMARY KEY (source, doc_key)
);

CREATE TABLE IF NOT EXISTS placements (
    source         TEXT NOT NULL,
    doc_key        TEXT NOT NULL,
    category_path  TEXT NOT NULL,
    PRIMARY KEY (source, doc_key, category_path)
);

-- Standalone FTS5 index (not external-content): we keep its rowids in sync with
-- policies.rowid ourselves in upsert_policy(), so we control delete/insert fully.
CREATE VIRTUAL TABLE IF NOT EXISTS policies_fts USING fts5(
    title, full_text, source UNINDEXED, doc_key UNINDEXED
);
"""


@contextmanager
def connect(path: str) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


# Columns that may be missing on databases created by an earlier schema.
# CREATE TABLE IF NOT EXISTS won't add them, so patch them in idempotently.
_EXPECTED = {
    "subject": "TEXT",
    "version": "TEXT",
}


def _migrate(conn: sqlite3.Connection) -> None:
    have = {r["name"] for r in conn.execute("PRAGMA table_info(policies)")}
    for col, decl in _EXPECTED.items():
        if col not in have:
            conn.execute(f"ALTER TABLE policies ADD COLUMN {col} {decl}")


def get_existing_hash(conn: sqlite3.Connection, source: str, doc_key: str) -> Optional[str]:
    row = conn.execute(
        "SELECT content_hash FROM policies WHERE source=? AND doc_key=?",
        (source, doc_key),
    ).fetchone()
    return row["content_hash"] if row else None


def upsert_policy(conn: sqlite3.Connection, rec: dict) -> None:
    """Insert or update one policy row and refresh its FTS entry."""
    cols = [
        "source", "doc_key", "policy_id", "version", "title", "subject", "file_type",
        "source_url", "effective_date", "revised_date", "page_count", "cpt_codes",
        "full_text", "content_hash", "extract_ok", "extract_error", "first_seen", "last_pulled",
    ]
    if isinstance(rec.get("cpt_codes"), list):
        rec = {**rec, "cpt_codes": json.dumps(rec["cpt_codes"])}

    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("source", "doc_key", "first_seen"))
    conn.execute(
        f"INSERT INTO policies ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(source, doc_key) DO UPDATE SET {updates}",
        [rec.get(c) for c in cols],
    )
    rowid = conn.execute(
        "SELECT rowid FROM policies WHERE source=? AND doc_key=?",
        (rec["source"], rec["doc_key"]),
    ).fetchone()["rowid"]
    conn.execute("DELETE FROM policies_fts WHERE rowid=?", (rowid,))
    conn.execute(
        "INSERT INTO policies_fts (rowid, title, full_text, source, doc_key) VALUES (?,?,?,?,?)",
        (rowid, rec.get("title"), rec.get("full_text") or "", rec["source"], rec["doc_key"]),
    )


def replace_placements(conn: sqlite3.Connection, source: str, doc_key: str, paths: List[str]) -> None:
    conn.execute("DELETE FROM placements WHERE source=? AND doc_key=?", (source, doc_key))
    conn.executemany(
        "INSERT OR IGNORE INTO placements (source, doc_key, category_path) VALUES (?,?,?)",
        [(source, doc_key, p) for p in paths],
    )
