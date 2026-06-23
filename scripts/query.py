#!/usr/bin/env python3
"""Query the policy dataset.

Examples:
    python scripts/query.py stats
    python scripts/query.py search "continuous glucose monitor"
    python scripts/query.py search "tens unit" --source bcbsfl
    python scripts/query.py show 09-J4000-96
    python scripts/query.py compare "cgm" "glucose monitor"   # title keyword across sources
"""
import argparse
import sqlite3
import sys
import textwrap


def conn(db):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return c


def cmd_stats(c, _):
    rows = c.execute("""
        SELECT source, COUNT(*) docs,
               SUM(extract_ok) extracted,
               COUNT(policy_id) with_id
        FROM policies GROUP BY source
    """).fetchall()
    for r in rows:
        print(f"{r['source']:10}  docs={r['docs']:5}  text_extracted={r['extracted']:5}  with_policy_id={r['with_id']:5}")
    total = c.execute("SELECT COUNT(*) n FROM policies").fetchone()["n"]
    print(f"{'TOTAL':10}  docs={total}")


def cmd_search(c, a):
    q = "SELECT p.source, p.policy_id, p.title, snippet(policies_fts,1,'[',']','…',12) snip " \
        "FROM policies_fts f JOIN policies p ON p.rowid=f.rowid WHERE policies_fts MATCH ?"
    params = [a.query]
    if a.source:
        q += " AND p.source=?"
        params.append(a.source)
    q += " ORDER BY rank LIMIT ?"
    params.append(a.limit)
    for r in c.execute(q, params):
        print(f"\n● [{r['source']}] {r['policy_id'] or '—'}  {r['title']}")
        print("   " + textwrap.shorten(r["snip"].replace("\n", " "), 160))


def cmd_show(c, a):
    r = c.execute("SELECT * FROM policies WHERE policy_id=? OR doc_key=?", (a.id, a.id)).fetchone()
    if not r:
        print("not found"); return
    print(f"[{r['source']}] {r['policy_id'] or '—'}  {r['title']}")
    print(f"url: {r['source_url']}")
    print(f"effective={r['effective_date']}  revised={r['revised_date']}  pages={r['page_count']}")
    cats = c.execute("SELECT category_path FROM placements WHERE source=? AND doc_key=?",
                     (r["source"], r["doc_key"])).fetchall()
    print("categories: " + "; ".join(x["category_path"] for x in cats))
    print("\n--- text (first 1500 chars) ---")
    print((r["full_text"] or "")[:1500])


def cmd_compare(c, a):
    """List, per source, policies whose title matches any keyword — the seed of
    cross-payer comparison: same topic, different payers, side by side."""
    like = " OR ".join("LOWER(title) LIKE ?" for _ in a.keywords)
    params = [f"%{k.lower()}%" for k in a.keywords]
    rows = c.execute(
        f"SELECT source, policy_id, title FROM policies WHERE {like} ORDER BY title, source",
        params).fetchall()
    for r in rows:
        print(f"[{r['source']:8}] {r['policy_id'] or '—':14} {r['title']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/policies.db")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats")
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--source"); s.add_argument("--limit", type=int, default=10)
    s = sub.add_parser("show"); s.add_argument("id")
    s = sub.add_parser("compare"); s.add_argument("keywords", nargs="+")
    a = ap.parse_args()
    c = conn(a.db)
    {"stats": cmd_stats, "search": cmd_search, "show": cmd_show, "compare": cmd_compare}[a.cmd](c, a)


if __name__ == "__main__":
    main()
