"""Nguồn Crossref — tra metadata chính thống của MỘT bài theo DOI.

GET https://api.crossref.org/works/{doi}. Dùng để xác nhận năm/venue trước khi
trích. Crossref không có `search` ở đây; chỉ có `lookup`.
"""

from __future__ import annotations

import re
from typing import Optional

from app.agents.research_agent.sources.base import PaperRecord, SourceError, http_get

NGUON = "crossref"
URL = "https://api.crossref.org/works/"
_THE_XML_RE = re.compile(r"<[^>]+>")


def _dau_tien(gia_tri) -> Optional[str]:
    return gia_tri[0] if isinstance(gia_tri, list) and gia_tri else None


def parse_message(m: dict) -> PaperRecord:
    moc = ((m.get("issued") or {}).get("date-parts") or [[None]])[0]
    nam = moc[0] if moc else None
    ngay = None
    if len(moc) == 3 and all(moc):
        ngay = f"{moc[0]:04d}-{moc[1]:02d}-{moc[2]:02d}"
    doi = (m.get("DOI") or "").lower()
    tac_gia = [
        " ".join(p for p in (a.get("given"), a.get("family")) if p)
        for a in (m.get("author") or [])
    ]
    # Abstract của Crossref là JATS XML (<jats:p>...) -> bỏ thẻ, giữ chữ.
    abstract = " ".join(_THE_XML_RE.sub(" ", m.get("abstract") or "").split())
    return PaperRecord(
        title=" ".join((_dau_tien(m.get("title")) or "").split()),
        year=nam,
        published=ngay,
        authors=[t for t in tac_gia if t],
        venue=_dau_tien(m.get("container-title")),
        abstract=abstract or None,
        citations=m.get("is-referenced-by-count"),
        ids={"doi": doi} if doi else {},
        url=m.get("URL") or (f"https://doi.org/{doi}" if doi else None),
        found_in=[NGUON],
    )


def lookup(doi: str) -> PaperRecord:
    from app.core import config

    email = config.settings.openalex_mailto
    try:
        data = http_get(NGUON, URL + doi, params={"mailto": email} if email else None)
    except SourceError as exc:
        if exc.status == 404:
            raise SourceError("DOI_NOT_FOUND", f"Crossref không có DOI {doi}") from None
        raise
    if not isinstance(data, dict) or not isinstance(data.get("message"), dict):
        raise SourceError("CROSSREF_BAD_RESPONSE", "thiếu trường 'message'")
    return parse_message(data["message"])
