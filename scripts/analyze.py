#!/usr/bin/env python3
"""Cross-payer coverage analysis -> web/public/data/analysis.json.

Programmatic breadth across every matched topic and both gap directions:
  * overlap / gap counts (overall and by category)
  * per-policy coverage signals (criteria, experimental/investigational,
    not-medically-necessary, step therapy, age limit, prior auth, specialist)
  * a focused coverage-criteria excerpt per policy
  * per cross-payer topic: both payers side by side + computed difference tags

The narrative "key findings" are authored separately (analysis_findings.json)
after deep-reading a curated set; this script merges them in if present.
"""
import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.export_web import make_id, SOURCE_LABELS  # reuse id scheme + labels

SIGNALS = {
    "criteria": re.compile(r"medically\s+necessary\s+(?:when|if|for|in)", re.I),
    "experimental": re.compile(r"experimental\s+(?:or|/|and)\s+investigational|investigational", re.I),
    "not_med_nec": re.compile(r"not\s+(?:considered\s+)?medically\s+necessary", re.I),
    "step_therapy": re.compile(r"tried\s+and\s+failed|inadequate\s+response|step\s+therapy|trial\s+of|failure\s+of|intoleran", re.I),
    "age_limit": re.compile(r"\b\d{1,2}\s+years?\s+(?:of\s+age|or\s+older|and\s+older)|\bage\s+\d", re.I),
    "prior_auth": re.compile(r"prior\s+authorization|preauthorization|prior\s+approval", re.I),
    "specialist": re.compile(r"prescribed\s+by\s+.{0,40}?(?:specialist|ologist)|in\s+consultation\s+with\s+a", re.I),
    "quantity": re.compile(r"quantity\s+limit|maximum\s+(?:dose|of)|not\s+to\s+exceed|per\s+\d+\s+(?:days|weeks|months)", re.I),
}
COVERAGE_HEADS = [
    r"Position\s+Statement", r"Coverage\s+Rationale", r"Clinical\s+Indications?",
    r"Medical(?:ly)?\s+Necess", r"Indications?\s+(?:for\s+)?Coverage", r"Criteria", r"Coverage",
]


def normalize(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "")).strip()


# Generic UM disclaimer that must NOT be mistaken for coverage criteria.
BOILERPLATE = re.compile(r"criteria\s+for\s+utilization\s+management\s+decisions", re.I)
CONSOLIDATED = re.compile(r"consolidated\s+to\s+a\s+single\s+MCG:\s*([0-9A-Z\-]+)", re.I)
CRIT_HEAD = re.compile(
    r"(?:meets?\s+the\s+definition\s+of\s+medical\s+necessity|"
    r"medically\s+necessary)\s+when\b|covered\s+when\b", re.I)


def drug_terms(title: str):
    """Pull generic + brand tokens from a title for locating a drug in a parent doc."""
    terms = re.findall(r"\(([^)]+)\)", title)  # bracketed brand/generic
    lead = re.split(r"[(,]", title)[0]
    terms.append(lead)
    out = []
    for t in terms:
        t = re.sub(r"[^A-Za-z\- ]", " ", t).strip()
        for w in t.split():
            if len(w) > 4 and w.lower() not in ("brand", "tablet", "tablets", "capsule",
                                                "oral", "injection", "ver"):
                out.append(w.lower())
    return out


def best_criteria(text: str, near=None, limit: int = 1500) -> str:
    """Extract the coverage-criteria passage, preferring a real criteria heading
    (optionally nearest a drug mention), skipping the UM boilerplate."""
    if not text:
        return ""
    flat = normalize(text)
    region = flat
    offset = 0
    if near:
        for term in near:
            m = re.search(re.escape(term), flat, re.I)
            if m:
                offset = max(0, m.start() - 250)
                region = flat[offset: offset + 4000]
                break
    # 1) explicit criteria heading within the region
    for m in CRIT_HEAD.finditer(region):
        if not BOILERPLATE.search(region[m.start(): m.start() + 80]):
            return region[m.start(): m.start() + limit].strip()
    # 2) coverage section heading with the most prose, skipping boilerplate
    best, best_score = None, -1
    for pat in COVERAGE_HEADS:
        for m in re.finditer(pat, flat, re.I):
            w = flat[m.start(): m.start() + 300]
            if BOILERPLATE.search(w):
                continue
            score = sum(ch.islower() for ch in w)
            if score > best_score:
                best, best_score = m.start(), score
    if best is not None:
        return flat[best: best + limit].strip()
    return flat[:limit].strip()


def signals_for(text: str) -> dict:
    flat = normalize(text)
    return {k: bool(rx.search(flat)) for k, rx in SIGNALS.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/policies.db")
    ap.add_argument("--out", default="web/public/data/analysis.json")
    ap.add_argument("--findings", default="data/analysis_findings.json")
    ap.add_argument("--digest", action="store_true", help="print a readable digest")
    ap.add_argument("--llm", action="store_true",
                    help="enrich each cross-payer topic with an LLM criteria comparison")
    ap.add_argument("--model", default=None,
                    help="model for --llm (default: policydb.llm_compare.DEFAULT_MODEL)")
    ap.add_argument("--llm-cache", default="data/llm_cache",
                    help="directory for cached LLM comparisons")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM policies").fetchall()
    by_id = {}
    bcbs_by_pid = {}
    for r in rows:
        pid = make_id(r["source"], r["doc_key"])
        by_id[pid] = r
        if r["source"] == "bcbsfl" and r["policy_id"]:
            bcbs_by_pid[r["policy_id"]] = r

    def criteria_text(row):
        """The text that actually holds coverage criteria, following Florida
        Blue's consolidations to the parent class guideline. Returns
        (extracted_excerpt, was_consolidated, parent_id)."""
        text = row["full_text"] or ""
        if row["source"] == "bcbsfl":
            m = CONSOLIDATED.search(normalize(text))
            if m and m.group(1) in bcbs_by_pid and m.group(1) != row["policy_id"]:
                parent = bcbs_by_pid[m.group(1)]
                return (best_criteria(parent["full_text"], near=drug_terms(row["title"])),
                        True, m.group(1))
            return best_criteria(text), False, None
        return best_criteria(text), False, None

    def llm_text(row):
        """A larger criteria slice for the LLM (follows FL consolidation), so the
        model can find the real medical-necessity section even when our short
        excerpt grabbed the wrong part of a messy PDF."""
        text = row["full_text"] or ""
        if row["source"] == "bcbsfl":
            m = CONSOLIDATED.search(normalize(text))
            if m and m.group(1) in bcbs_by_pid and m.group(1) != row["policy_id"]:
                parent = bcbs_by_pid[m.group(1)]
                return best_criteria(parent["full_text"], near=drug_terms(row["title"]), limit=7000)
        return best_criteria(text, limit=7000)
    cats = {}
    for r in conn.execute("SELECT source, doc_key, category_path FROM placements"):
        cats.setdefault(make_id(r["source"], r["doc_key"]), []).append(r["category_path"])

    index = json.loads(Path("web/public/data/index.json").read_text())
    id2meta = {p["id"]: p for p in index}
    topics = json.loads(Path("web/public/data/topics.json").read_text())

    def category_of(pid):
        c = (cats.get(pid) or [""])[0] or ""
        return c.replace("Current Guidelines > By Category > ", "").split(" > ")[-1] or "Other"

    def best_member(members, source):
        """Pick the most substantive policy for a payer within a topic."""
        cand = [m for m in members if id2meta[m]["source"] == source and id2meta[m]["policy_id"]]
        cand = cand or [m for m in members if id2meta[m]["source"] == source]
        if not cand:
            return None
        return max(cand, key=lambda m: len(by_id[m]["full_text"] or ""))

    DIFF_LABELS = {
        "step_therapy": "step-therapy requirement",
        "age_limit": "age restriction",
        "prior_auth": "prior authorization",
        "specialist": "specialist-prescriber requirement",
        "quantity": "quantity/dose limit",
        "experimental": "deems some uses experimental/investigational",
    }

    comparisons = []
    for t in topics:
        if not t["cross_payer"]:
            continue
        sides = {}
        for src in ("bcbsfl", "oscar"):
            m = best_member(t["members"], src)
            if not m:
                continue
            row = by_id[m]
            excerpt, consolidated, parent_id = criteria_text(row)
            sides[src] = {
                "id": m,
                "policy_id": id2meta[m]["policy_id"],
                "title": id2meta[m]["title"],
                "version": id2meta[m]["version"],
                "effective_date": id2meta[m]["effective_date"],
                "revised_date": id2meta[m]["revised_date"],
                "page_count": id2meta[m]["page_count"],
                "signals": signals_for(excerpt),
                "excerpt": excerpt,
                "consolidated_into": parent_id if consolidated else None,
            }
        if len(sides) < 2:
            continue
        # difference tags: signal present on one side but not the other
        diffs = []
        for key, label in DIFF_LABELS.items():
            a = sides["bcbsfl"]["signals"].get(key)
            b = sides["oscar"]["signals"].get(key)
            if a != b:
                who = "Florida Blue" if a else "Oscar"
                diffs.append({"key": key, "label": label, "only": who})
        comparisons.append({
            "topic_id": t["topic_id"],
            "label": re.sub(r"\([^)]*\)$", "", t["label"]).strip() or t["label"],
            "score": t["score"],
            "category": category_of(sides["bcbsfl"]["id"]),
            "bcbsfl": sides["bcbsfl"],
            "oscar": sides["oscar"],
            "diffs": diffs,
            "llm_matched": t.get("llm_matched", False),
        })
    comparisons.sort(key=lambda c: (-len(c["diffs"]), -c["score"]))

    # Optional: enrich each comparison with an LLM-aligned criteria comparison.
    if args.llm:
        from policydb.env import load_env
        load_env()
        import anthropic
        from policydb import llm_compare

        client = anthropic.Anthropic()
        model = args.model or llm_compare.DEFAULT_MODEL
        cache_dir = Path(args.llm_cache)
        n = len(comparisons)
        print(f"LLM comparison: {n} topics, model={model}, cache={cache_dir}")
        for i, c in enumerate(comparisons, 1):
            fl_text = llm_text(by_id[c["bcbsfl"]["id"]])
            os_text = llm_text(by_id[c["oscar"]["id"]])
            try:
                c["llm"] = llm_compare.compare(
                    client, label=c["label"], fl_text=fl_text, os_text=os_text,
                    model=model, cache_dir=cache_dir, topic_id=c["topic_id"],
                )
            except Exception as e:  # don't lose the whole run to one bad call
                print(f"  ! topic {c['topic_id']} ({c['label']}): {type(e).__name__}: {e}")
                c["llm"] = None
            if i % 10 == 0 or i == n:
                print(f"  {i}/{n}")

    # gaps: single-payer topics that are real guidelines
    def topic_real(t):
        return any(id2meta[m]["policy_id"] for m in t["members"])

    def gap_list(source):
        out = []
        for t in topics:
            if t["sources"] == [source] and topic_real(t):
                m = next((m for m in t["members"] if id2meta[m]["policy_id"]), t["members"][0])
                out.append({
                    "topic_id": t["topic_id"],
                    "label": re.sub(r"\([^)]*\)$", "", t["label"]).strip() or t["label"],
                    "policy_id": id2meta[m]["policy_id"],
                    "category": category_of(m),
                })
        out.sort(key=lambda g: (g["category"], g["label"]))
        return out

    bcbs_gaps = gap_list("bcbsfl")
    oscar_gaps = gap_list("oscar")

    def cat_counts(items):
        return dict(Counter(i["category"] for i in items).most_common())

    # Drug-family stats (class-guideline ↔ per-drug, content-based).
    from policydb.drug_families import build_families
    families = build_families([dict(r) for r in rows])

    # Restrictiveness rollup (only populated when --llm ran).
    restr = [c["llm"]["restrictiveness"] for c in comparisons
             if c.get("llm") and c["llm"].get("restrictiveness")]
    restrictiveness_summary = None
    if restr:
        restrictiveness_summary = {
            "scored": len(restr),
            "by_payer": dict(Counter(r["more_restrictive"] for r in restr)),
            "substantial": {
                "Florida Blue": sum(1 for r in restr if r["more_restrictive"] == "Florida Blue"
                                    and r.get("magnitude") == "substantial"),
                "Oscar": sum(1 for r in restr if r["more_restrictive"] == "Oscar"
                             and r.get("magnitude") == "substantial"),
            },
        }

    summary = {
        "total_policies": len(rows),
        "by_source": {s: sum(1 for r in rows if r["source"] == s) for s in sorted({r["source"] for r in rows})},
        "cross_payer_topics": len(comparisons),
        "drug_families": len(families),
        "drug_family_links": sum(f["n_matched_bcbsfl"] for f in families),
        "bcbsfl_only": len(bcbs_gaps),
        "oscar_only": len(oscar_gaps),
        "topics_with_diffs": sum(1 for c in comparisons if c["diffs"]),
        "diff_type_counts": dict(Counter(d["label"] for c in comparisons for d in c["diffs"]).most_common()),
        "bcbsfl_gap_categories": cat_counts(bcbs_gaps),
        "oscar_gap_categories": cat_counts(oscar_gaps),
        "llm_matched_topics": sum(1 for c in comparisons if c.get("llm_matched")),
        "restrictiveness": restrictiveness_summary,
        "source_labels": SOURCE_LABELS,
    }

    findings = []
    fp = Path(args.findings)
    if fp.exists():
        findings = json.loads(fp.read_text())
        # Topic ids renumber whenever matching changes (e.g. --llm-links merges).
        # Re-point each hand-curated finding example to the current topic by its
        # leading subject token (the generic drug name), so "Compare:" links stay
        # correct.
        by_first = {}
        for c in comparisons:
            toks = c["label"].split()
            if toks:
                by_first.setdefault(toks[0].lower(), c["topic_id"])
        for fnd in findings:
            for e in fnd.get("examples", []):
                toks = (e.get("label") or "").split()
                if toks and toks[0].lower() in by_first:
                    e["topic_id"] = by_first[toks[0].lower()]

    out = {
        "summary": summary,
        "findings": findings,
        "comparisons": comparisons,
        "gaps": {"bcbsfl": bcbs_gaps, "oscar": oscar_gaps},
    }
    Path(args.out).write_text(json.dumps(out))
    print(f"wrote {args.out}: {len(comparisons)} comparisons, "
          f"{len(bcbs_gaps)} BCBS-only, {len(oscar_gaps)} Oscar-only, {len(findings)} findings")

    if args.digest:
        print("\n=== DIFF-TYPE COUNTS ===", summary["diff_type_counts"])
        print("\n=== TOP COMPARISONS BY # OF DIFFERENCES ===")
        for c in comparisons[:30]:
            tags = ", ".join(f"{d['label']}→{d['only']}" for d in c["diffs"]) or "no signal diffs"
            print(f"\n● {c['label']}  [{c['category']}]  match={c['score']}")
            print(f"   FL {c['bcbsfl']['policy_id']}: {c['bcbsfl']['excerpt'][:230]}")
            print(f"   OS {c['oscar']['policy_id']}: {c['oscar']['excerpt'][:230]}")
            print(f"   diffs: {tags}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
