#!/usr/bin/env python3
"""Export the SQLite dataset into the static bundle the website ships.

    python scripts/export_web.py --db data/policies.db --out web/public/data

Produces:
    index.json          all policy metadata + topic_id (drives browse/search)
    topics.json         cross-payer topic clusters (drives side-by-side compare)
    text/<id>.json      full text + codes + coverage excerpt (lazy-loaded)
"""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from policydb.match import build_topics

SOURCE_LABELS = {"bcbsfl": "BCBS Florida", "oscar": "Oscar Health"}

# Headings that introduce the coverage/position section, in priority order.
COVERAGE_HEADS = [
    r"Position\s+Statement",
    r"Coverage\s+Rationale",
    r"Clinical\s+Indications?",
    r"Medical(?:ly)?\s+Necess",
    r"Indications?\s+(?:for\s+)?Coverage",
    r"Coverage",
]


def make_id(source: str, doc_key: str) -> str:
    return f"{source}__" + re.sub(r"[^A-Za-z0-9]+", "_", doc_key).strip("_")


def _prose_score(window: str) -> int:
    """Rough 'is this real prose vs a heading list' score: lowercase run length."""
    return sum(1 for ch in window if ch.islower())


def excerpt(text: str, limit: int = 700) -> str:
    """Best-effort coverage/position snippet.

    A coverage heading like "Position Statement" often appears first in the PDF's
    table of contents (followed by more headings, not prose). So we collect every
    heading match and pick the one whose following window reads most like prose.
    """
    if not text:
        return ""
    candidates = []
    for pat in COVERAGE_HEADS:
        for m in re.finditer(pat, text, re.I):
            start = m.start()
            candidates.append((_prose_score(text[start: start + 300]), start))
    if candidates:
        candidates.sort(reverse=True)
        best = candidates[0][1]
        return re.sub(r"\s+", " ", text[best: best + limit]).strip()
    # fallback: start after the disclaimer boilerplate
    m = re.search(r"(NOT\s+AN\s+AUTHORIZATION|Disclaimer)", text, re.I)
    start = m.end() if m else 0
    return re.sub(r"\s+", " ", text[start: start + limit]).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/policies.db")
    ap.add_argument("--out", default="web/public/data")
    ap.add_argument("--threshold", type=float, default=0.5)
    args = ap.parse_args()

    out = Path(args.out)
    (out / "text").mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM policies").fetchall()

    # placements -> categories per (source, doc_key)
    cats = {}
    for r in conn.execute("SELECT source, doc_key, category_path FROM placements"):
        cats.setdefault((r["source"], r["doc_key"]), []).append(r["category_path"])

    docs_for_match = []
    index = []
    for r in rows:
        pid = make_id(r["source"], r["doc_key"])
        codes = json.loads(r["cpt_codes"]) if r["cpt_codes"] else []
        category = (cats.get((r["source"], r["doc_key"])) or [None])[0]
        index.append({
            "id": pid,
            "source": r["source"],
            "sourceLabel": SOURCE_LABELS.get(r["source"], r["source"]),
            "policy_id": r["policy_id"],
            "version": r["version"],
            "title": r["title"],
            "category": category,
            "effective_date": r["effective_date"],
            "revised_date": r["revised_date"],
            "page_count": r["page_count"],
            "n_codes": len(codes),
            "source_url": r["source_url"],
        })
        docs_for_match.append({
            "id": pid, "source": r["source"],
            "title": r["title"], "policy_id": r["policy_id"],
        })
        # per-policy text file
        (out / "text" / f"{pid}.json").write_text(json.dumps({
            "id": pid,
            "title": r["title"],
            "codes": codes,
            "excerpt": excerpt(r["full_text"] or ""),
            "full_text": r["full_text"] or "",
        }))

    id_to_topic, topics = build_topics(docs_for_match, threshold=args.threshold)
    for item in index:
        item["topic_id"] = id_to_topic.get(item["id"])

    (out / "index.json").write_text(json.dumps(index))
    (out / "topics.json").write_text(json.dumps(topics))

    cross = [t for t in topics if t["cross_payer"]]
    meta = {
        "policy_count": len(index),
        "topic_count": len(topics),
        "cross_payer_topics": len(cross),
        "sources": [
            {"slug": s, "label": SOURCE_LABELS.get(s, s),
             "count": sum(1 for i in index if i["source"] == s)}
            for s in sorted({i["source"] for i in index})
        ],
    }
    (out / "meta.json").write_text(json.dumps(meta))

    print(f"exported {len(index)} policies, {len(topics)} topics "
          f"({len(cross)} cross-payer) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
