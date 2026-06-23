"""Source adapter interface.

Every payer/competitor we pull is implemented as a SourceAdapter. The adapter
knows how to (1) enumerate the catalog and (2) fetch a single document. Everything
downstream (text extraction, field parsing, the SQLite store) is shared and
source-agnostic, so adding a new competitor means writing one new adapter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass
class CatalogEntry:
    """One row in a source's catalog of documents.

    A single underlying document may appear under several categories; each
    appearance is its own CatalogEntry but they share the same ``doc_key``.
    """

    source: str                  # short slug, e.g. "bcbsfl"
    doc_key: str                 # stable per-document id within the source (e.g. PDF code)
    title: str                   # human title from the catalog
    category_path: str           # "Current Guidelines > By Category > Pharmacy"
    fetch_ref: str               # opaque token the adapter uses in fetch_document()
    source_url: str              # canonical URL to view the document
    file_type: str               # "pdf", "doc", "form", ...
    # Optional source-supplied fields. When the catalog already knows these more
    # authoritatively than PDF parsing would (e.g. Oscar's code/version live in
    # the listing, not in MCG-style headers), set them and the pipeline prefers
    # them over the values extracted from the PDF.
    policy_id: Optional[str] = None
    version: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class FetchedDocument:
    content: bytes
    content_type: str
    final_url: str


class SourceAdapter:
    """Base class. Subclasses implement ``slug``, ``catalog`` and ``fetch_document``."""

    slug: str = "base"

    def catalog(self) -> Iterable[CatalogEntry]:
        raise NotImplementedError

    def fetch_document(self, entry: CatalogEntry) -> Optional[FetchedDocument]:
        raise NotImplementedError
