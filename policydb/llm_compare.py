"""LLM-backed cross-payer criteria comparison.

For a matched topic, send both payers' coverage-criteria text to Claude and get
back a structured, aligned comparison: normalized per-payer criteria, the
requirements they share (and whether those agree or differ), and the criteria
unique to each payer. Results are cached on disk keyed by content hash so
re-running the pipeline is free and deterministic unless the inputs change.

Uses forced tool-use for structured output (works across SDK versions). The
model is configurable; we default to a cost-effective model since this runs once
per cross-payer topic (~120 calls).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Optional

# Bump when the prompt or schema changes, to invalidate the on-disk cache.
PROMPT_VERSION = "2"
DEFAULT_MODEL = "claude-sonnet-4-6"

FL = "Florida Blue"
OS = "Oscar"

COMPARISON_TOOL = {
    "name": "record_comparison",
    "description": (
        "Record a structured comparison of two payers' coverage criteria for the "
        "same drug/service."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": (
                    "One or two plain-English sentences a reviewer can read at a "
                    "glance: the single most important way these two policies "
                    "differ (or that they substantively agree)."
                ),
            },
            "shared": {
                "type": "array",
                "description": (
                    "Requirements BOTH payers impose. One entry per distinct "
                    "requirement they have in common."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Short label, e.g. 'Age', 'Genetic testing', 'Specialist prescriber'.",
                        },
                        "florida_blue": {
                            "type": "string",
                            "description": "What Florida Blue requires for this item, concise.",
                        },
                        "oscar": {
                            "type": "string",
                            "description": "What Oscar requires for this item, concise.",
                        },
                        "agreement": {
                            "type": "string",
                            "enum": ["same", "differs"],
                            "description": (
                                "'same' if the requirement is substantively "
                                "equivalent; 'differs' if both require this kind "
                                "of thing but with materially different specifics "
                                "(e.g. different age thresholds)."
                            ),
                        },
                    },
                    "required": ["category", "florida_blue", "oscar", "agreement"],
                },
            },
            "florida_blue_only": {
                "type": "array",
                "description": "Requirements Florida Blue imposes that Oscar does not.",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "detail": {"type": "string"},
                    },
                    "required": ["category", "detail"],
                },
            },
            "oscar_only": {
                "type": "array",
                "description": "Requirements Oscar imposes that Florida Blue does not.",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "detail": {"type": "string"},
                    },
                    "required": ["category", "detail"],
                },
            },
            "restrictiveness": {
                "type": "object",
                "description": (
                    "Which payer is harder to get this approved under — the more "
                    "aggressive utilization-management posture."
                ),
                "properties": {
                    "more_restrictive": {
                        "type": "string",
                        "enum": ["Florida Blue", "Oscar", "neither"],
                        "description": "Which payer's criteria are harder to satisfy overall.",
                    },
                    "magnitude": {
                        "type": "string",
                        "enum": ["none", "minor", "moderate", "substantial"],
                        "description": "How much harder. 'none' when they're effectively equivalent.",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "1-2 sentences citing the specific criteria that make one tighter.",
                    },
                    "cost_note": {
                        "type": "string",
                        "description": (
                            "One sentence on the business implication: tighter criteria "
                            "likely reduce utilization/cost for that payer, weighed "
                            "against member/provider abrasion."
                        ),
                    },
                },
                "required": ["more_restrictive", "magnitude", "rationale", "cost_note"],
            },
        },
        "required": ["summary", "shared", "florida_blue_only", "oscar_only", "restrictiveness"],
    },
}

SYSTEM = (
    "You compare U.S. health-insurance medical/pharmacy coverage policies. You are "
    "given the coverage-criteria text (extracted from PDFs, so formatting may be "
    "rough) for the SAME drug or service from two payers, Florida Blue and Oscar. "
    "Identify the distinct medical-necessity requirements each payer imposes, then "
    "align them: which requirements both share (noting whether the specifics match "
    "or differ), and which are unique to one payer. Treat 'medically necessary "
    "when ALL of the following' criteria as the requirements. Ignore boilerplate, "
    "disclaimers, billing/coding sections, and 'non-covered indications' lists "
    "unless they state an actual eligibility requirement. Be concise and concrete; "
    "quote specific thresholds (ages, durations, doses) when present. If a payer's "
    "text doesn't actually contain coverage criteria, return empty arrays for it. "
    "Finally, judge which payer is MORE RESTRICTIVE — harder to get approved under "
    "(more required trials, tighter age/dose limits, more documentation, specialist "
    "gates). A more restrictive payer typically saves cost via lower utilization, at "
    "the price of member/provider abrasion; note that trade-off."
)


def _hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def _user_prompt(label: str, fl_text: str, os_text: str) -> str:
    return (
        f"Drug/service topic: {label}\n\n"
        f"=== FLORIDA BLUE coverage criteria ===\n{fl_text or '(no text)'}\n\n"
        f"=== OSCAR coverage criteria ===\n{os_text or '(no text)'}\n\n"
        "Call record_comparison with the aligned comparison."
    )


def compare(
    client,
    *,
    label: str,
    fl_text: str,
    os_text: str,
    model: str,
    cache_dir: Path,
    topic_id: int,
) -> Optional[dict]:
    """Return the structured comparison dict, using the on-disk cache when the
    inputs (and prompt version + model) are unchanged."""
    key = _hash(PROMPT_VERSION, model, label, fl_text, os_text)
    cache_path = cache_dir / f"{topic_id}.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text())
        if cached.get("key") == key:
            return cached["result"]

    resp = client.messages.create(
        model=model,
        max_tokens=4000,
        system=SYSTEM,
        tools=[COMPARISON_TOOL],
        tool_choice={"type": "tool", "name": "record_comparison"},
        messages=[{"role": "user", "content": _user_prompt(label, fl_text, os_text)}],
    )
    result = None
    for block in resp.content:
        if block.type == "tool_use" and block.name == "record_comparison":
            result = block.input
            break
    if result is None:
        return None

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"key": key, "result": result}))
    return result


def normalize(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "")).strip()
