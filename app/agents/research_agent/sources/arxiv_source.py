"""Nguồn arXiv — bọc tim_arxiv() có sẵn, KHÔNG sửa hàm đó.

tim_arxiv() trả về dict có `published` là NGÀY NỘP bài (không phải ngày sửa bản
mới nhất), nên PaperRecord.published của arXiv luôn là ngày nộp.
"""

from __future__ import annotations

from typing import List

from app.agents.research_agent.sources.base import PaperRecord, SourceError
from app.agents.research_agent.tools import tim_arxiv

NGUON = "arxiv"


def parse_items(items: List[dict]) -> List[PaperRecord]:
    """Đổi danh sách dict của tim_arxiv() thành PaperRecord. Bài bị tác giả rút thì bỏ."""
    ket_qua: List[PaperRecord] = []
    for it in items:
        if it.get("withdrawn"):
            continue
        entry_id = it.get("entry_id") or ""
        ma = entry_id.split("/abs/")[-1] if "/abs/" in entry_id else ""
        published = it.get("published") or None
        ket_qua.append(
            PaperRecord(
                title=" ".join((it.get("title") or "").split()),
                year=int(published[:4]) if published else None,
                published=published,
                authors=[a.strip() for a in (it.get("authors") or "").split(",") if a.strip()],
                venue="arXiv",
                abstract=" ".join((it.get("summary") or "").split()) or None,
                ids={"arxiv": ma} if ma else {},
                url=entry_id or None,
                found_in=[NGUON],
                rank=len(ket_qua),
            )
        )
    return ket_qua


def search(query: str, limit: int) -> List[PaperRecord]:
    try:
        from langchain_community.utilities import ArxivAPIWrapper

        wrapper = ArxivAPIWrapper(top_k_results=limit)
        return parse_items(tim_arxiv(wrapper, query))
    except SourceError:
        raise
    except Exception as exc:  # mạng lỗi, arXiv 503/429, parse lỗi...
        ma = "ARXIV_RATE_LIMITED" if "429" in str(exc) else "ARXIV_UNAVAILABLE"
        raise SourceError(ma, type(exc).__name__) from None
