"""Orchestrate a pull: catalog -> fetch -> extract -> store.

Source-agnostic. Dedupes catalog entries by ``doc_key`` (a document listed under
N categories is fetched once, with N placements). Uses ``content_hash`` to skip
re-extraction of unchanged documents on subsequent pulls.
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, Optional

from . import db
from .extract import extract_pdf
from .sources.base import CatalogEntry, SourceAdapter


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_pull(
    adapter: SourceAdapter,
    db_path: str,
    *,
    limit: Optional[int] = None,
    workers: int = 6,
    delay: float = 0.1,
    log: Callable[[str], None] = print,
) -> dict:
    """Pull a source into ``db_path``. Returns a summary dict."""
    # 1) Catalog: group placements by document.
    entries: dict[str, CatalogEntry] = {}
    placements: dict[str, list[str]] = defaultdict(list)
    for e in adapter.catalog():
        entries.setdefault(e.doc_key, e)
        placements[e.doc_key].append(e.category_path)
    keys = list(entries)
    if limit:
        keys = keys[:limit]
    log(f"[{adapter.slug}] catalog: {len(keys)} documents "
        f"({sum(len(v) for v in placements.values())} placements)")

    stats = defaultdict(int)

    def process(key: str) -> tuple[str, Optional[dict], Optional[str]]:
        entry = entries[key]
        if entry.file_type != "pdf":
            return key, None, "skipped_non_pdf"
        if delay:
            time.sleep(delay)
        doc = adapter.fetch_document(entry)
        if not doc:
            return key, None, "fetch_failed"
        h = hashlib.sha256(doc.content).hexdigest()
        ex = extract_pdf(doc.content)
        rec = {
            "source": entry.source, "doc_key": entry.doc_key,
            # Prefer catalog-supplied identity over PDF-parsed when the adapter set it.
            "policy_id": entry.policy_id or ex.policy_id, "version": entry.version,
            "title": entry.title, "subject": ex.subject,
            "file_type": entry.file_type, "source_url": entry.source_url,
            "effective_date": ex.effective_date, "revised_date": ex.revised_date,
            "page_count": ex.page_count, "cpt_codes": ex.cpt_codes,
            "full_text": ex.text, "content_hash": h,
            "extract_ok": int(ex.ok), "extract_error": ex.error,
        }
        return key, rec, None

    now = _now()
    sequential = getattr(adapter, "sequential", False)

    def store(conn, key, rec, skip) -> None:
        if skip:
            stats[skip] += 1
        else:
            prior = db.get_existing_hash(conn, rec["source"], rec["doc_key"])
            rec["first_seen"] = now
            rec["last_pulled"] = now
            db.upsert_policy(conn, rec)
            stats["changed" if prior != rec["content_hash"] else "unchanged"] += 1
            if not rec["extract_ok"]:
                stats["extract_failed"] += 1
        db.replace_placements(conn, entries[key].source, key, placements[key])

    with db.connect(db_path) as conn:
        if sequential:
            # Stateful session: prime once, then crawl strictly in order.
            if hasattr(adapter, "prime"):
                log(f"[{adapter.slug}] priming session ...")
                adapter.prime()
            for done, key in enumerate(keys, 1):
                store(conn, *process(key))
                if done % 25 == 0:
                    log(f"  {done}/{len(keys)} ...")
                    conn.commit()
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(process, k): k for k in keys}
                for done, fut in enumerate(as_completed(futures), 1):
                    store(conn, *fut.result())
                    if done % 50 == 0:
                        log(f"  {done}/{len(keys)} ...")

    log(f"[{adapter.slug}] done: {dict(stats)}")
    return {"documents": len(keys), **stats}
