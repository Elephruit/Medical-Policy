"""Document -> text + structured fields.

Source-agnostic. Given raw PDF bytes, pull the full text and best-effort parse
the fields useful for cross-payer comparison: policy/MCG number, effective and
revision dates, and CPT/HCPCS procedure codes.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import List, Optional

from pypdf import PdfReader

# BCBS-FL MCG numbers look like 09-J4000-96 / 02-61000-30. Kept reasonably
# general; other payers can register their own patterns later.
MCG_NUM = re.compile(r"\b\d{2}-[A-Z0-9]{4,6}-\d{1,3}\b")
_D = (r"(\d{1,2}/\d{1,2}/\d{2,4}|"
      r"(?:January|February|March|April|May|June|July|August|"
      r"September|October|November|December)\s+\d{1,2},\s+\d{4})")
# Labeled headers in these MCG PDFs are reliable; try most-specific labels first.
EFFECTIVE = re.compile(r"(?:Original\s+Effective\s+Date|Effective\s+Date)\s*:?\s*" + _D, re.I)
REVISED = re.compile(r"(?:Revised|Revision)\s*:?\s*" + _D, re.I)
REVIEWED = re.compile(r"(?:Reviewed|Last\s+Review)\s*:?\s*" + _D, re.I)
SUBJECT = re.compile(r"Subject\s*:\s*([^\n\r]{3,160})", re.I)
CPT = re.compile(r"\b(?:\d{4}[A-Z]|\d{5}|[A-Z]\d{4})\b")  # CPT + HCPCS Level II


@dataclass
class Extracted:
    text: str = ""
    page_count: int = 0
    policy_id: Optional[str] = None
    subject: Optional[str] = None        # payer's authoritative title from the PDF
    effective_date: Optional[str] = None
    revised_date: Optional[str] = None
    cpt_codes: List[str] = field(default_factory=list)
    ok: bool = False
    error: Optional[str] = None


def extract_pdf(content: bytes) -> Extracted:
    out = Extracted()
    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [p.extract_text() or "" for p in reader.pages]
        out.text = "\n".join(pages).strip()
        out.page_count = len(pages)
    except Exception as e:  # malformed/encrypted PDFs shouldn't kill the run
        out.error = f"{type(e).__name__}: {e}"
        return out

    text = out.text
    head = text[:4000]  # identifying fields live near the top
    if m := MCG_NUM.search(head) or MCG_NUM.search(text):
        out.policy_id = m.group(0)
    if m := SUBJECT.search(head):
        out.subject = m.group(1).strip()
    if m := EFFECTIVE.search(head):
        out.effective_date = m.group(1)
    # Prefer an explicit "Revised" date; fall back to "Reviewed".
    if m := REVISED.search(head):
        out.revised_date = m.group(1)
    elif m := REVIEWED.search(head):
        out.revised_date = m.group(1)

    # CPT/HCPCS often cluster in a coding section; dedupe, keep order, cap noise.
    seen, codes = set(), []
    for m in CPT.finditer(text):
        c = m.group(0)
        if c not in seen:
            seen.add(c)
            codes.append(c)
    out.cpt_codes = codes[:400]
    out.ok = bool(text)
    return out
