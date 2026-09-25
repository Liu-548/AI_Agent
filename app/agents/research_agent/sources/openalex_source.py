"""Nguồn OpenAlex — GET https://api.openalex.org/works.

Từ 02/2026 API bắt buộc có key (miễn phí, có hạn mức theo ngày). Thiếu
OPENALEX_API_KEY thì ném OPENALEX_NOT_CONFIGURED NGAY, không gọi HTTP — paper_search
coi đó là "nguồn không khả dụng" chứ không phải lỗi chết.

Đây là nguồn dành cho paper_search, tách biệt với tool `openalex_search` cũ
(chế độ single, dùng mailto không key) trong tools.py.
"""

from __future__ import annotations

import re
from typing import List, Optional

from app.agents.research_agent.sources.base import PaperRecord, SourceError, http_get

NGUON = "openalex"
URL = "https://api.openalex.org/works"
CHON_TRUONG = (
    "id,doi,display_name,publication_year,publication_date,authorships,"
    "primary_location,cited_by_count,abstract_inverted_index,ids"
)
_ARXIV_RE = re.compile(r"arxiv\.org/abs/([^\s?#]+)", re.IGNORECASE)


def dung_lai_abstract(inverted_index: Optional[dict]) -> str:
    """OpenAlex trả abstract dạng {từ: [các vị trí]} — sắp lại theo vị trí để ra câu văn."""
    if not inverted_index:
        return ""
    theo_vi_tri = {}
    for tu, vi_tri in inverted_index.items():
        for v in vi_tri:
            theo_vi_tri[v] = tu
    return " ".join(theo_vi_tri[v] for v in sorted(theo_vi_tri))


def parse_work(w: dict, rank: int = 0) -> PaperRecord:
    ids = {}
    ma = (w.get("id") or "").rsplit("/", 1)[-1]
    if ma:
        ids["openalex"] = ma
    doi = (w.get("doi") or "").replace("https://doi.org/", "").strip().lower()
    if doi:
        ids["doi"] = doi
    pmid = ((w.get("ids") or {}).get("pmid") or "").rstrip("/").rsplit("/", 1)[-1]
    if pmid.isdigit():
        ids["pmid"] = pmid

    vi_tri_chinh = w.get("primary_location") or {}
    khop = _ARXIV_RE.search(vi_tri_chinh.get("landing_page_url") or "")
    if khop:
        ids["arxiv"] = khop.group(1)

    return PaperRecord(
        title=" ".join((w.get("display_name") or "").split()),
        year=w.get("publication_year"),
        published=w.get("publication_date"),
        authors=[
            (a.get("author") or {}).get("display_name", "")
            for a in (w.get("authorships") or [])
            if (a.get("author") or {}).get("display_name")
        ],
        venue=((vi_tri_chinh.get("source") or {}).get("display_name")),
        abstract=dung_lai_abstract(w.get("abstract_inverted_index")) or None,
        citations=w.get("cited_by_count"),
        ids=ids,
        url=(f"https://doi.org/{doi}" if doi else vi_tri_chinh.get("landing_page_url")),
        found_in=[NGUON],
        rank=rank,
    )


def search(query: str, limit: int) -> List[PaperRecord]:
    from app.core import config

    key = config.settings.openalex_api_key
    if not key:
        raise SourceError("OPENALEX_NOT_CONFIGURED", "thiếu OPENALEX_API_KEY")
    data = http_get(
        NGUON,
        URL,
        params={"search": query, "per_page": limit, "select": CHON_TRUONG, "api_key": key},
    )
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise SourceError("OPENALEX_BAD_RESPONSE", "thiếu trường 'results'")
    return [parse_work(w, i) for i, w in enumerate(data["results"])]
