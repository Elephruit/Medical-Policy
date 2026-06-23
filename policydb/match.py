"""Cross-payer topic matching.

Groups equivalent policies across payers into *topics* so the website can show
them side by side. Approach: IDF-weighted cosine over normalized title tokens,
link pairs above a threshold (across sources, or same policy_id within a source),
then union-find into connected components. Drug policies match near-perfectly
(brand + generic overlap); medical/surgical matches are fuzzier, so we keep the
score for the UI to surface as a confidence signal.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

# Boilerplate / payer / dosage-form words that don't help identify a topic.
STOP = set(
    "the a an of for and or to in on with without used use as at by from is are "
    "guideline guidelines policy policies clinical medical pharmacy oscar bcbs "
    "florida blue services service therapy therapies treatment treatments "
    "tablet tablets capsule capsules oral injection injectable injections solution "
    "cream powder products product approved accepted off label necessity per ver "
    "version brand generic iv sq im subcutaneous intravenous infusion "
    "agent agents preferred physician administered exceptions criteria benefit".split()
)
# Strip embedded codes: (CG013, Ver. 11), (PG264, Ver. 3), 09-E0000-14.
CODE = re.compile(
    r"\([A-Za-z]{1,5}\d+[A-Za-z]?(?:\s*,?\s*ver\.?\s*\d+)?\)|\b\d{2}-[A-Z0-9]{4,6}-\d{1,3}\b",
    re.I,
)
_SUFFIXES = ("ation", "ization", "ising", "izing", "ing", "ions", "ion", "ents", "ent", "ers", "es", "s")


def _stem(w: str) -> str:
    """Light suffix stemmer so inhibitor/inhibitors and affirming/affirmation align."""
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def tokenize(title: str) -> List[str]:
    # Hyphens become spaces, so "Bio-Engineered" -> "bio engineered" and
    # "Gender-Affirming" -> "gender affirming" (both match their unhyphenated forms).
    t = CODE.sub(" ", title).lower()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return [_stem(w) for w in t.split() if w not in STOP and len(w) > 2]


class _UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def build_topics(
    docs: List[dict], threshold: float = 0.40
) -> Tuple[Dict[str, int], List[dict]]:
    """docs: [{id, source, title, policy_id}]. Returns (id->topic_id, topics)."""
    toks = [tokenize(d["title"]) for d in docs]

    df: Dict[str, int] = defaultdict(int)
    for tk in toks:
        for w in set(tk):
            df[w] += 1
    n = max(len(docs), 1)
    idf = {w: math.log(n / (1 + c)) for w, c in df.items()}

    def vec(tk: List[str]) -> Dict[str, float]:
        v: Dict[str, float] = defaultdict(float)
        for w in tk:
            v[w] += idf.get(w, 0.0)
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items()}

    vecs = [vec(tk) for tk in toks]

    def cos(a: Dict[str, float], b: Dict[str, float]) -> float:
        if len(a) > len(b):
            a, b = b, a
        return sum(x * b.get(w, 0.0) for w, x in a.items())

    uf = _UnionFind(len(docs))
    scores: Dict[int, float] = {}  # best link score per doc, for confidence display

    # Same policy_id within a source => same topic (e.g. versioned/upcoming docs).
    by_pid: Dict[tuple, List[int]] = defaultdict(list)
    for i, d in enumerate(docs):
        if d.get("policy_id"):
            by_pid[(d["source"], d["policy_id"])].append(i)
    for idxs in by_pid.values():
        for j in idxs[1:]:
            uf.union(idxs[0], j)

    # Cross-source links above threshold. Block by shared token to avoid O(n^2).
    by_token: Dict[str, List[int]] = defaultdict(list)
    for i, tk in enumerate(toks):
        for w in set(tk):
            by_token[w].append(i)

    checked: set = set()
    for w, members in by_token.items():
        if len(members) > 400:  # ultra-common token — skip as a blocking key
            continue
        # A near-unique term shared across payers (a drug name, "viscosupplementation",
        # "ciltacabtagene") is decisive on its own — link regardless of cosine. This
        # rescues long/verbose titles whose cosine is diluted. df<=3 keeps it safe:
        # moderately common words like "growth" or "tissue" never qualify.
        rare = df[w] <= 3 and len(w) >= 7
        for a_i in range(len(members)):
            i = members[a_i]
            for b_i in range(a_i + 1, len(members)):
                j = members[b_i]
                if docs[i]["source"] == docs[j]["source"]:
                    continue
                key = (i, j) if i < j else (j, i)
                if key in checked:
                    continue
                checked.add(key)
                sc = cos(vecs[i], vecs[j])
                # The rare term only *rescues* a borderline pair (cosine floor 0.28),
                # never creates one from a single generic word like "accessories"
                # (which would otherwise chain unrelated topics via union-find).
                if sc >= threshold or (rare and sc >= 0.28):
                    uf.union(i, j)
                    link = max(sc, 0.9) if rare else sc
                    scores[i] = max(scores.get(i, 0), link)
                    scores[j] = max(scores.get(j, 0), link)

    # Assemble components into topics.
    comp: Dict[int, List[int]] = defaultdict(list)
    for i in range(len(docs)):
        comp[uf.find(i)].append(i)

    id_to_topic: Dict[str, int] = {}
    topics: List[dict] = []
    tid = 0
    for root, members in comp.items():
        sources = sorted({docs[i]["source"] for i in members})
        # Topic label: shortest cleaned title among members (usually the crispest).
        label = min((docs[i]["title"] for i in members), key=len)
        label = CODE.sub("", label).strip(" -")
        for i in members:
            id_to_topic[docs[i]["id"]] = tid
        topics.append(
            {
                "topic_id": tid,
                "label": label,
                "size": len(members),
                "sources": sources,
                "cross_payer": len(sources) > 1,
                "members": [docs[i]["id"] for i in members],
                "score": round(max((scores.get(i, 0) for i in members), default=0.0), 3),
            }
        )
        tid += 1
    return id_to_topic, topics
