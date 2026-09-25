"""Nguồn Semantic Scholar — GET https://api.semanticscholar.org/graph/v1/paper/search.

Header x-api-key chỉ gửi khi có SEMANTIC_SCHOLAR_API_KEY. Không có key thì hay dính
429 -> được phép thất bại; paper_search vẫn trả kết quả từ các nguồn còn lại.
"""

from __future__ import annotations

from typing import List

from app.agents.research_agent.sources.base import PaperRecord, SourceError, http_get

NGUON = "semantic_scholar"
URL = "https://api.semanticscholar.org/graph/v1/paper/search"
CHON_TRUONG = "paperId,title,abstract,year,publicationDate,authors,venue,citationCount,externalIds,url"


def parse_paper(p: dict, rank: int = 0) -> PaperRecord:
    ngoai = p.get("externalIds") or {}
    ids = {}
    if p.get("paperId"):
        ids["s2"] = p["paperId"].lower()
    if ngoai.get("DOI"):
        ids["doi"] = ngoai["DOI"].lower()
    if ngoai.get("ArXiv"):
        ids["arxiv"] = ngoai["ArXiv"]
    if ngoai.get("PubMed"):
        ids["pmid"] = str(ngoai["PubMed"])
    return PaperRecord(
        title=" ".join((p.get("title") or "").split()),
        year=p.get("year"),
        published=p.get("publicationDate"),
        authors=[a["name"] for a in (p.get("authors") or []) if a.get("name")],
        venue=p.get("venue") or None,
        abstract=p.get("abstract") or None,
        citations=p.get("citationCount"),
        ids=ids,
        url=p.get("url"),
        found_in=[NGUON],
        rank=rank,
    )


def search(query: str, limit: int) -> List[PaperRecord]:
    from app.core import config

    key = config.settings.semantic_scholar_api_key
    data = http_get(
        NGUON,
        URL,
        params={"query": query, "limit": limit, "fields": CHON_TRUONG},
        headers={"x-api-key": key} if key else None,
    )
    if not isinstance(data, dict) or not isinstance(data.get("data", []), list):
        raise SourceError("SEMANTIC_SCHOLAR_BAD_RESPONSE", "thiếu trường 'data'")
    return [parse_paper(p, i) for i, p in enumerate(data.get("data") or [])]
