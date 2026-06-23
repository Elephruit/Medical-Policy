#!/usr/bin/env python3
"""Pull a source into the dataset.

Usage:
    python scripts/pull.py bcbsfl --db data/policies.db
    python scripts/pull.py bcbsfl --db data/policies.db --limit 20   # quick test
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import policydb
from policydb.pipeline import run_pull


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=sorted(policydb.SOURCES))
    ap.add_argument("--db", default="data/policies.db")
    ap.add_argument("--limit", type=int, default=None, help="cap documents (for testing)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--delay", type=float, default=0.1, help="per-request politeness delay (s)")
    args = ap.parse_args()

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    adapter = policydb.SOURCES[args.source]()
    run_pull(adapter, args.db, limit=args.limit, workers=args.workers, delay=args.delay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
