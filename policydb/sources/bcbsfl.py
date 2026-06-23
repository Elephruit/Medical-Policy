"""Blue Cross Blue Shield of Florida — Medical Coverage Guidelines.

Site: https://mcgs.bcbsfl.com  (ASP.NET WebForms + Telerik RadPanelBar)

Retrieval mechanism (reverse-engineered)
----------------------------------------
The catalog ships in the landing page: a Telerik ``itemData`` JSON tree whose
leaves carry an internal file path, structurally mirrored by the ``<li>`` tree
that holds the titles. Each leaf has a *hierarchical index* (e.g. "1:1:230").

The PDFs are NOT directly addressable: ``/mcg?FilePath=<anything>`` returns
whatever document the server session currently has selected. Selecting a document
requires replaying the RadPanelBar click postback:

    __EVENTTARGET = "RadPanelBar1"
    __EVENTARGUMENT = "<hierarchical index>"
    RadPanelBar1_ClientState = {"expandedItems":[<ancestor indices>],
                                "logEntries":[], "selectedItems":["<index>"]}

plus the page's ViewState/EventValidation. The postback response embeds a fresh
numeric handle in ``mcg.aspx?FilePath=<n>``; fetching ``/mcg?FilePath=<n>`` in the
same session then returns the selected PDF. Two gotchas, both handled here:

  * The first postback after loading the landing page doesn't "take" — ViewState
    must be settled first. We prime with one throwaway postback.
  * Clicking the already-selected item is a client-side no-op (Telerik's
    ``set_selected`` early-returns). We crawl distinct items in sequence so
    consecutive selections always differ, and detect/recover the rare stale read.

Because the session is stateful, fetching is strictly sequential.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Iterable, List, Optional, Tuple

import requests

from .base import CatalogEntry, FetchedDocument, SourceAdapter

BASE = "https://mcgs.bcbsfl.com"
HIDDEN = re.compile(r"<input[^>]*type=\"hidden\"[^>]*>")
NAME_RE = re.compile(r"name=\"([^\"]*)\"")
VAL_RE = re.compile(r"value=\"([^\"]*)\"")
HANDLE_RE = re.compile(r"FilePath=(\d+)")


def _ext_to_type(path: str) -> str:
    low = path.lower()
    if low.endswith(".pdf"):
        return "pdf"
    if low.endswith(".doc") or low.endswith(".docx"):
        return "doc"
    return "form"


def _hidden_fields(html: str) -> dict:
    f = {}
    for m in HIDDEN.finditer(html):
        tag = m.group(0)
        n = NAME_RE.search(tag)
        if n:
            v = VAL_RE.search(tag)
            f[n.group(1)] = v.group(1) if v else ""
    return f


def _item_data(html: str) -> list:
    k = html.find('"itemData":')
    if k == -1:
        raise ValueError("itemData not found — site markup changed")
    start = html.index("[", k)
    depth, i = 0, start
    while i < len(html):
        c = html[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return json.loads(html[start : i + 1])


class _Node:
    __slots__ = ("name", "children")

    def __init__(self):
        self.name = None
        self.children = []


class _PanelParser(HTMLParser):
    """Builds the <li> nesting tree, capturing rpText titles."""

    def __init__(self):
        super().__init__()
        self.stack = [_Node()]
        self.grab = False
        self.buf = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "li":
            n = _Node()
            self.stack[-1].children.append(n)
            self.stack.append(n)
        elif tag == "span" and a.get("class") == "rpText":
            self.grab = True
            self.buf = ""

    def handle_endtag(self, tag):
        if tag == "li" and len(self.stack) > 1:
            self.stack.pop()
        elif tag == "span" and self.grab:
            self.grab = False
            if self.stack[-1].name is None:
                self.stack[-1].name = self.buf.strip()

    def handle_data(self, data):
        if self.grab:
            self.buf += data


class BcbsflAdapter(SourceAdapter):
    slug = "bcbsfl"
    sequential = True  # stateful session — pipeline must not parallelize

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (policydb research)"})
        self.fields: dict = {}
        self._loaded = False

    # ----- catalog -----
    def _load(self) -> Tuple[list, _Node, str]:
        html = self.session.get(BASE + "/", timeout=60).text
        self.fields = _hidden_fields(html)
        item_data = _item_data(html)
        start = html.find('id="RadPanelBar1"')
        ul0 = html.find("<ul", start)
        end = html.find("RadPanelBar1_ClientState", start)
        parser = _PanelParser()
        parser.feed(html[ul0:end])
        self._loaded = True
        return item_data, parser.stack[0], html

    def catalog(self) -> Iterable[CatalogEntry]:
        item_data, root, _ = self._load()
        seen: set[str] = set()  # dedupe by internal path; keep first placement

        def walk(inodes, dnodes, path: List[int], cats: List[str]):
            for ix, (inode, dn) in enumerate(zip(inodes, dnodes)):
                name = dn.name or ""
                if "items" in inode:
                    yield from walk(inode["items"], dn.children, path + [ix], cats + [name])
                    continue
                value = inode.get("value", "")
                code = value.rsplit("/", 1)[-1]
                if not code or code in seen:
                    continue
                seen.add(code)
                idx = ":".join(map(str, path + [ix]))
                ancestors = [":".join(map(str, (path + [ix])[:j])) for j in range(1, len(path) + 1)]
                yield CatalogEntry(
                    source=self.slug,
                    doc_key=code,                       # stable internal filename
                    title=name,                         # hint; authoritative title comes from PDF
                    category_path=" > ".join(cats),     # hint
                    fetch_ref=json.dumps({"idx": idx, "anc": ancestors}),
                    source_url=f"{BASE}/  (select: {name})",
                    file_type=_ext_to_type(code),
                    extra={"internal_path": value},
                )

        yield from walk(item_data, root.children, [], [])

    # ----- stateful fetch -----
    def _postback(self, idx: str, anc: List[str]) -> Optional[str]:
        """Select an item; return the numeric session handle for its PDF."""
        f = dict(self.fields)
        f["__EVENTTARGET"] = "RadPanelBar1"
        f["__EVENTARGUMENT"] = idx
        f["RadPanelBar1_ClientState"] = json.dumps(
            {"expandedItems": anc, "logEntries": [], "selectedItems": [idx]}
        )
        r = self.session.post(BASE + "/", data=f, timeout=120, headers={"Referer": BASE + "/"})
        if r.status_code != 200:
            return None
        self.fields = _hidden_fields(r.text)  # carry ViewState forward
        m = HANDLE_RE.search(r.text)
        return m.group(1) if m else None

    def prime(self) -> None:
        """Settle ViewState with one throwaway postback so later fetches register.

        We select the *last* leaf so the session's current selection differs from
        the first catalog entry (re-clicking the selected item is a no-op).
        """
        item_data, root, _ = self._load()
        last = []  # mutable holder for the last leaf seen

        def visit(inodes, dnodes, path):
            for ix, (inode, dn) in enumerate(zip(inodes, dnodes)):
                if "items" in inode:
                    visit(inode["items"], dn.children, path + [ix])
                else:
                    last.clear()
                    last.append(path + [ix])

        visit(item_data, root.children, [])
        if last:
            p = last[0]
            idx = ":".join(map(str, p))
            anc = [":".join(map(str, p[:j])) for j in range(1, len(p))]
            self._postback(idx, anc)

    def fetch_document(self, entry: CatalogEntry) -> Optional[FetchedDocument]:
        ref = json.loads(entry.fetch_ref)
        handle = self._postback(ref["idx"], ref["anc"])
        if not handle:
            return None
        r = self.session.get(
            f"{BASE}/mcg?FilePath={handle}", timeout=120, headers={"Referer": BASE + "/"}
        )
        if r.status_code != 200 or not r.content:
            return None
        return FetchedDocument(
            content=r.content,
            content_type=r.headers.get("Content-Type", ""),
            final_url=r.url,
        )
