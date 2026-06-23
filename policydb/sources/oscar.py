"""Oscar Health — Clinical Guidelines (Medical + Pharmacy).

Pages: https://www.hioscar.com/clinical-guidelines/medical
       https://www.hioscar.com/clinical-guidelines/pharmacy

A Next.js + Contentful site. Both listing pages embed a ``__NEXT_DATA__`` JSON
blob whose ``expandableList`` modules hold the catalog: each item has a title
like ``"Acupuncture (CG013, Ver. 11)"`` and a link href like ``/medical/cg013v11``.

The doc page is NOT the PDF — it embeds the real PDF from Contentful's CDN at
``modules[0].fields.file.url`` (``//assets.ctfassets.net/.../*.pdf``). So fetching
is two stateless GETs per document (doc page -> asset URL -> PDF) and can run in
parallel. Oscar's code/version come from the listing title (the PDFs don't carry
an MCG-style number), so the adapter supplies ``policy_id``/``version`` directly.
"""
from __future__ import annotations

import json
import re
from typing import Iterable, List, Optional

import requests

from .base import CatalogEntry, FetchedDocument, SourceAdapter

BASE = "https://www.hioscar.com"
PAGES = {
    "medical": f"{BASE}/clinical-guidelines/medical",
    "pharmacy": f"{BASE}/clinical-guidelines/pharmacy",
}
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
# Title codes: "(CG013, Ver. 11)", "(PG033, Ver. 7)", sometimes "(CG061)".
CODE_VER = re.compile(r"\(([A-Za-z]{1,5}\d+[A-Za-z]?)(?:\s*,?\s*Ver\.?\s*(\d+))?\)", re.I)
DOC_HREF = re.compile(r"^/(medical|pharmacy)/")


def _next_data(html: str) -> dict:
    m = NEXT_DATA.search(html)
    if not m:
        raise ValueError("__NEXT_DATA__ not found — Oscar page markup changed")
    return json.loads(m.group(1))


class OscarAdapter(SourceAdapter):
    slug = "oscar"
    sequential = False  # stateless CDN fetches — safe to parallelize

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (policydb research)"})

    def catalog(self) -> Iterable[CatalogEntry]:
        # Dedupe by href; a doc can be cross-listed (e.g. under both pages or under
        # "Upcoming Policy Changes"). Merge the section labels it appears under.
        seen: dict[str, CatalogEntry] = {}

        for domain_page, url in PAGES.items():
            data = _next_data(self.session.get(url, timeout=60).text)
            modules = data["props"]["pageProps"]["modules"]
            for mod in modules:
                if mod.get("contentTypeId") != "landing.expandableList":
                    continue
                header = mod.get("fields", {}).get("header", "")
                for item, href in self._iter_items(mod["fields"].get("listItems", [])):
                    if not href or not DOC_HREF.match(href):
                        continue
                    domain = href.split("/")[1]            # authoritative: medical|pharmacy
                    slug = href.lstrip("/")                # "medical/cg013v11" — stable key
                    section = f"Oscar > {domain.title()} > {header}"
                    if slug in seen:
                        # already catalogued under another section; record placement
                        prev = seen[slug].category_path
                        if section not in prev:
                            seen[slug].category_path = prev + " | " + section
                        continue
                    # The href (e.g. /medical/cg103v2) is the canonical code+version
                    # source — more reliable than the title, where an abbreviation
                    # like "(VMAT2)" can otherwise be mis-read as the code.
                    code, ver = None, None
                    hm = re.match(r"(CG|PG)(\d+)(?:v(\d+))?$", slug.split("/")[-1], re.I)
                    if hm:
                        code = (hm.group(1) + hm.group(2)).upper()
                        ver = hm.group(3)
                    else:
                        m = CODE_VER.search(item)
                        code = m.group(1).upper() if m else None
                        ver = m.group(2) if (m and m.lastindex and m.group(2)) else None
                    seen[slug] = CatalogEntry(
                        source=self.slug,
                        doc_key=slug,
                        title=item,
                        category_path=section,
                        fetch_ref=href,
                        source_url=f"{BASE}{href}",
                        file_type="pdf",
                        policy_id=code,
                        version=ver,
                    )
        yield from seen.values()

    def _iter_items(self, items: List[dict]):
        """Flatten listItems, recursing into nestedItems (pharmacy groups)."""
        for it in items:
            if it.get("nestedItems"):
                yield from self._iter_items(it["nestedItems"])
            link = it.get("link") or {}
            href = link.get("href")
            if href:
                yield it.get("item", "").strip(), href

    def fetch_document(self, entry: CatalogEntry) -> Optional[FetchedDocument]:
        # 1) doc page -> Contentful asset URL
        page = self.session.get(f"{BASE}{entry.fetch_ref}", timeout=60)
        if page.status_code != 200:
            return None
        asset = self._asset_url(page.text)
        if not asset:
            return None
        # 2) download the PDF from the CDN
        r = self.session.get(asset, timeout=120)
        if r.status_code != 200 or not r.content:
            return None
        return FetchedDocument(
            content=r.content,
            content_type=r.headers.get("Content-Type", ""),
            final_url=r.url,
        )

    def _asset_url(self, doc_html: str) -> Optional[str]:
        # The embedded PDF lives on an "embeddedAsset" module. Don't filter by a
        # .pdf extension — Contentful filenames like "..._v6.1" drop it, yet the
        # asset is still served as application/pdf.
        data = _next_data(doc_html)
        modules = data["props"]["pageProps"].get("modules", [])
        candidates = [m for m in modules if m.get("contentTypeId") == "landing.embeddedAsset"]
        for mod in candidates or modules:
            url = (mod.get("fields", {}).get("file") or {}).get("url")
            if url:
                return "https:" + url if url.startswith("//") else url
        return None
