"""Class-guideline ↔ per-drug-policy matching (content-based, one-to-many).

Oscar frequently consolidates a drug class into ONE guideline (e.g.
"Antineoplastics - HER2-Targeted Agents", CG101) while Florida Blue publishes a
SEPARATE policy per drug (Kadcyla, Perjeta, Enhertu, …). Title similarity can't
bridge these, so we read the class guideline's drug table — entries look like
``Brand (generic) [J-code]`` — and map each member drug to the other payer's
per-drug policy by brand/generic name.

The result is a list of "drug families": one consolidating guideline plus the
individual per-drug policies it corresponds to on the other payer.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

# A class-style title names a drug *category*, not a single brand.
CLASS_TITLE = re.compile(
    r"\b(agents?|products?|inhibitors?|antagonists?|biologics|antineoplastics?|"
    r"modulators?|analogs?|stimulating\s+factors?|monoclonal)\b",
    re.I,
)
# Reference/formulary/exception master docs that list drugs but aren't a single
# coverage class — exclude so they don't swamp the families.
EXCLUDE_TITLE = re.compile(
    r"preferred\s+physician-administered\s+specialty|site-of-service|"
    r"site-of-care|concomitant|exceptions?\s+(criteria\s+)?for\s+certain|"
    r"specialty\s+exceptions|formulary|all\s+other|experimental\s+or\s+investigational",
    re.I,
)
# Trailing "(CG101, Ver. 3)" / "- Medical Benefit Preferred …" boilerplate in titles.
TITLE_CODE = re.compile(r"\s*\([A-Za-z]{1,5}\d+[A-Za-z]?\s*,?\s*Ver\.?\s*\d+\)\s*$", re.I)
# Drug rows are bulleted in the preferred-products list: "● Brand (generic) [J1234]".
# Anchoring on the bullet is what separates real class members from drugs merely
# mentioned in prose (references, interactions, "also called …") elsewhere in the PDF.
DRUG_ROW = re.compile(
    r"[●❖➢•*⇅]\s*([A-Z][A-Za-z][A-Za-z\-]{2,}(?:\s+[A-Z][A-Za-z]+)?)\s*"
    r"\(([a-z][A-Za-z0-9\-,/ ]{4,}?)\)"
)
_NOT_BRAND = {
    "table", "note", "plan", "the", "for", "see", "products", "drug", "drugs",
    "class", "figure", "appendix", "formulary", "preferred", "summary", "ver",
    "criteria", "coverage", "policy", "section", "list", "other", "both", "and",
}
# Dosage-form suffixes on a brand ("Austedo XR", "Ingrezza Sprinkle") — strip so
# variants of the same brand collapse.
_FORM_SUFFIX = re.compile(r"\s+(XR|SR|ER|IR|IV|SQ|LAR|Depot|Sprinkle|SPRINKLES?|ODT)\b.*$", re.I)


def extract_members(text: str) -> Dict[str, str]:
    """Brand -> generic for every bulleted drug listed in a class guideline."""
    flat = re.sub(r"[ \t]+", " ", text)
    out: Dict[str, str] = {}
    for m in DRUG_ROW.finditer(flat):
        brand = _FORM_SUFFIX.sub("", m.group(1)).strip()
        generic = m.group(2).strip()
        if brand.lower() in _NOT_BRAND or len(brand) < 3:
            continue
        out.setdefault(brand, generic)
    return out


def _title_key(title: str) -> str:
    """Lowercased title with non-alnum collapsed to spaces, padded for word search."""
    return " " + re.sub(r"[^a-z0-9]+", " ", title.lower()).strip() + " "


def _match_drug(brand: str, generic: str, pool: list) -> Optional[dict]:
    """Match a class member to a per-drug policy by whole-word brand or generic
    name. Word-boundary matching avoids spurious substring hits (e.g. the brand
    'Aria' inside 'ovarian')."""
    # Try the BRAND first (most specific — distinguishes Phesgo from Perjeta even
    # though both list "pertuzumab"), then the PRIMARY active ingredient only.
    # Secondary components of combo products (e.g. the "hyaluronidase" excipient in
    # Phesgo) are excluded — they are shared across unrelated drugs and cause false
    # links (Vyvgart Hytrulo also contains hyaluronidase).
    ordered = [brand.lower().strip()]
    primary = re.split(r"[,/]", generic)[0].strip().lower()
    if primary:
        ordered.append(primary)
        base = re.sub(r"-[a-z]{2,4}$", "", primary)  # margetuximab-cmkb -> margetuximab
        if base != primary and len(base) >= 5:
            ordered.append(base)
    seen = set()
    for k in ordered:
        if len(k) < 4 or k in seen:
            continue
        seen.add(k)
        for policy, key in pool:
            if f" {k} " in key:
                return policy
    return None


def build_families(policies: List[dict]) -> List[dict]:
    """policies: dicts with source, doc_key, policy_id, version, title, full_text.

    Returns drug families: an Oscar class guideline mapped to the matching
    per-drug policies on each payer.
    """
    # Dedupe each source's guidelines by policy_id, keeping the highest version.
    def latest(src: str) -> list:
        best: Dict[str, dict] = {}
        for p in policies:
            if p["source"] != src or not p.get("policy_id"):
                continue
            k = p["policy_id"]
            if k not in best or int(p.get("version") or 0) > int(best[k].get("version") or 0):
                best[k] = p
        return list(best.values())

    oscar = latest("oscar")
    bcbsfl = latest("bcbsfl")
    fl_pool = [(p, _title_key(p["title"])) for p in bcbsfl]
    os_pool = [(p, _title_key(p["title"])) for p in oscar]

    families: List[dict] = []
    for cg in oscar:
        title = cg["title"]
        if not CLASS_TITLE.search(title) or EXCLUDE_TITLE.search(title):
            continue
        members = extract_members(cg["full_text"])
        if not (2 <= len(members) <= 25):
            continue

        member_rows = []
        seen_fl = set()  # collapse phantom sub-brands that resolve to the same FL policy
        for brand, generic in sorted(members.items()):
            fl = _match_drug(brand, generic, fl_pool)
            if fl and fl["policy_id"] in seen_fl:
                continue
            # Skip self-matching the class guideline among Oscar per-drug policies.
            os_pd = _match_drug(brand, generic,
                                [(p, t) for p, t in os_pool if p["policy_id"] != cg["policy_id"]])
            if fl:
                seen_fl.add(fl["policy_id"])
            member_rows.append({
                "drug": brand,
                "generic": generic,
                "bcbsfl": {"policy_id": fl["policy_id"], "title": fl["title"],
                           "doc_key": fl["doc_key"]} if fl else None,
                "oscar_perdrug": {"policy_id": os_pd["policy_id"], "title": os_pd["title"],
                                  "doc_key": os_pd["doc_key"]} if os_pd else None,
            })

        matched = sum(1 for r in member_rows if r["bcbsfl"])
        if matched < 2:  # needs to actually illuminate a class-vs-per-drug split
            continue
        families.append({
            "oscar_class": {
                "policy_id": cg["policy_id"],
                "title": TITLE_CODE.sub("", re.sub(r"\s*-\s*Medical Benefit.*$", "", title)).strip(),
                "full_title": title,
                "doc_key": cg["doc_key"],
                "version": cg["version"],
            },
            "n_listed": len(members),
            "n_matched_bcbsfl": matched,
            "members": member_rows,
        })

    families.sort(key=lambda f: -f["n_matched_bcbsfl"])
    return families
