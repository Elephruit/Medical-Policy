#!/usr/bin/env python3
"""Phase 1: normalize every policy with the LLM, then derive cross-payer links.

    ANTHROPIC_API_KEY=... python -m scripts.llm_normalize

Writes:
    data/llm_profiles.json   id -> normalized profile (cached per policy on disk)
    data/llm_links.json      [[id_a, id_b], ...] conservative same-subject links

Run this before `export_web --llm-links` and `analyze --llm`. It's incremental:
each policy's profile is cached by content hash, so re-runs only call the model
for new/changed policies.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.export_web import make_id
from policydb import llm_normalize


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/policies.db")
    ap.add_argument("--model", default=None)
    ap.add_argument("--cache", default="data/llm_cache/normalize")
    ap.add_argument("--profiles-out", default="data/llm_profiles.json")
    ap.add_argument("--links-out", default="data/llm_links.json")
    ap.add_argument("--limit", type=int, default=0, help="cap policies processed (0=all, for testing)")
    args = ap.parse_args()

    from policydb.env import load_env
    load_env()
    import anthropic
    client = anthropic.Anthropic()
    model = args.model or llm_normalize.DEFAULT_MODEL
    cache_dir = Path(args.cache)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT source, doc_key, title, full_text FROM policies").fetchall()
    if args.limit:
        rows = rows[: args.limit]

    profiles: dict[str, dict] = {}
    sources: dict[str, str] = {}
    n = len(rows)
    print(f"normalizing {n} policies, model={model}, cache={cache_dir}")
    for i, r in enumerate(rows, 1):
        pid = make_id(r["source"], r["doc_key"])
        sources[pid] = r["source"]
        try:
            profiles[pid] = llm_normalize.normalize_policy(
                client, pid=pid, title=r["title"], full_text=r["full_text"] or "",
                model=model, cache_dir=cache_dir,
            )
        except Exception as e:
            print(f"  ! {pid}: {type(e).__name__}: {e}")
            profiles[pid] = None
        if i % 50 == 0 or i == n:
            print(f"  {i}/{n}")

    Path(args.profiles_out).write_text(json.dumps(profiles))
    links = llm_normalize.derive_links(profiles, sources)
    Path(args.links_out).write_text(json.dumps(links))
    print(f"wrote {args.profiles_out} ({sum(1 for p in profiles.values() if p)} profiles), "
          f"{args.links_out} ({len(links)} links)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
