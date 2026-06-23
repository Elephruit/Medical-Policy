"""Phase 1: normalize every policy into a compact, comparable profile.

One LLM call per policy (cheap model), cached on disk by content hash. The
profile's ``canonical_subject`` becomes a matching key so we can link the same
drug/service across payers even when their titles differ — the matches the
lexical title matcher misses.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional

PROMPT_VERSION = "1"
DEFAULT_MODEL = "claude-haiku-4-5"

PROFILE_TOOL = {
    "name": "record_profile",
    "description": "Record a normalized profile of a single health-plan coverage policy.",
    "input_schema": {
        "type": "object",
        "properties": {
            "canonical_subject": {
                "type": "string",
                "description": (
                    "The single thing this policy governs, normalized for matching "
                    "across payers. For a drug, the INN/generic name lowercased "
                    "(e.g. 'ponesimod', 'eladocagene exuparvovec'). For a "
                    "service/procedure/device, a short canonical name lowercased "
                    "(e.g. 'sacroiliac joint fusion'). No brand names, no dosage "
                    "form, no payer codes."
                ),
            },
            "brand_names": {
                "type": "array", "items": {"type": "string"},
                "description": "Brand/trade names mentioned (e.g. ['Ponvory']). Empty if none.",
            },
            "subject_type": {
                "type": "string",
                "enum": ["drug", "biologic", "device", "procedure", "lab_test",
                         "imaging", "service", "class_guideline", "other"],
                "description": "What kind of thing this is. Use 'class_guideline' if it covers a whole drug class / many drugs.",
            },
            "drug_class": {
                "type": "string",
                "description": "Therapeutic/device class if applicable, else empty string.",
            },
            "one_liner": {
                "type": "string",
                "description": "One sentence: what this policy covers and its general stance.",
            },
            "requirements": {
                "type": "array", "items": {"type": "string"},
                "description": (
                    "The key medical-necessity requirements the policy imposes, each "
                    "as a concise standalone phrase with specifics (ages, durations, "
                    "doses, prior therapies). Empty if the text has no real criteria."
                ),
            },
        },
        "required": ["canonical_subject", "brand_names", "subject_type",
                     "drug_class", "one_liner", "requirements"],
    },
}

SYSTEM = (
    "You normalize U.S. health-insurance coverage policies (extracted from PDFs, so "
    "formatting may be rough). Read the policy and record a compact profile: what it "
    "governs (canonical subject + brand names + type) and its key medical-necessity "
    "requirements. Be precise about the canonical subject — it is used to match the "
    "same drug/service across different insurers, so use the generic/INN drug name or "
    "a standard service name, never a payer-specific title. Quote concrete thresholds "
    "in requirements. Ignore boilerplate, disclaimers, and coding tables."
)


def _hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def _input_text(title: str, full_text: str, limit: int = 6000) -> str:
    flat = re.sub(r"\s+", " ", full_text or "").strip()
    return f"Title: {title}\n\nPolicy text (may be truncated):\n{flat[:limit]}"


def normalize_policy(
    client, *, pid: str, title: str, full_text: str, model: str, cache_dir: Path,
) -> Optional[dict]:
    key = _hash(PROMPT_VERSION, model, title, full_text or "")
    cache_path = cache_dir / f"{pid}.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text())
        if cached.get("key") == key:
            return cached["result"]

    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        system=SYSTEM,
        tools=[PROFILE_TOOL],
        tool_choice={"type": "tool", "name": "record_profile"},
        messages=[{"role": "user", "content": _input_text(title, full_text)}],
    )
    result = None
    for block in resp.content:
        if block.type == "tool_use" and block.name == "record_profile":
            result = block.input
            break
    if result is None:
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"key": key, "result": result}))
    return result


# --- conservative cross-payer linking from profiles ------------------------

_FORM = set("tablet tablets capsule capsules oral injection injectable solution "
            "suspension infusion intravenous subcutaneous powder cream gel".split())


def _norm_key(s: str) -> str:
    s = re.sub(r"\([^)]*\)", " ", (s or "").lower())
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    toks = [t for t in s.split() if t not in _FORM and len(t) > 2]
    return " ".join(toks).strip()


def derive_links(profiles: dict[str, dict], sources: dict[str, str]) -> list[list[str]]:
    """profiles: id -> profile. sources: id -> source slug. Returns cross-source
    force-link pairs to feed into the topic matcher. Conservative: a drug links
    only when generic OR a brand name matches exactly; a service links only on an
    exact normalized canonical_subject match. Class guidelines are left to the
    existing drug-family logic (skipped here to avoid over-merging)."""
    DRUGGY = {"drug", "biologic"}
    by_key: dict[str, list[str]] = defaultdict(list)

    for pid, prof in profiles.items():
        if not prof:
            continue
        if prof.get("subject_type") == "class_guideline":
            continue
        keys = set()
        subj = _norm_key(prof.get("canonical_subject", ""))
        if subj and len(subj) >= 4:
            keys.add(subj)
        if prof.get("subject_type") in DRUGGY:
            for b in prof.get("brand_names", []):
                bk = _norm_key(b)
                if bk and len(bk) >= 4:
                    keys.add(bk)
        for k in keys:
            by_key[k].append(pid)

    # Drop keys that are too common to be a reliable identity (e.g. a generic
    # service phrase that many unrelated policies share).
    seen: set[tuple[str, str]] = set()
    links: list[list[str]] = []
    for k, ids in by_key.items():
        ids = sorted(set(ids))
        if len(ids) > 8:
            continue
        if len({sources.get(i) for i in ids}) < 2:
            continue  # need a cross-source link to matter
        anchor = ids[0]
        for other in ids[1:]:  # chain every member of the key to one anchor
            pair = (anchor, other)
            if pair not in seen:
                seen.add(pair)
                links.append([anchor, other])
    return links
