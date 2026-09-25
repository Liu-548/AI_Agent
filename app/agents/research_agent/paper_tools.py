"""Ba tool lá của scholar_agent: paper_search, pubmed_search, doi_lookup.

Cùng hợp đồng với mọi tool của dự án (app/core/contracts.py):
- nhận đúng một tham số `text: str`, trả về `str`;
- KHÔNG raise: lỗi -> "ERROR: <MÃ> | <thông điệp>";
- return_direct=False; description tiếng Anh, nói rõ KHI NÀO dùng.

Điểm khác tool cũ: kết quả tool mang ĐỦ dữ liệu để trích dẫn — dòng `Label:` chép
được nguyên văn và `Published:` là ngày nộp đúng. Grounding dùng chính văn bản
này làm bằng chứng, nên mọi mã (DOI, PMID...) trong nhãn đều nằm trong output.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from app.agents.research_agent.profiles import SearchProfile
from app.agents.research_agent.sources import (
    arxiv_source,
    crossref_source,
    openalex_source,
    pubmed_source,
    semantic_scholar_source,
)
from app.agents.research_agent.sources.base import (
    PaperRecord,
    SourceError,
    cat_gon,
    dedupe_records,
    rank_records,
)
from app.agents.research_agent.tools import SearchBudget, SearchInput
from app.core.contracts import tool_error

# Tên nguồn trong SearchProfile.paper_sources -> module nguồn (gọi .search lúc chạy
# để test thay được bằng monkeypatch).
NGUON_PAPER = {
    "arxiv": arxiv_source,
    "openalex": openalex_source,
    "semantic_scholar": semantic_scholar_source,
}

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
SO_TAC_GIA_TOI_DA = 3

DESC_PAPER_SEARCH = (
    "Search scholarly papers (journal articles, conference papers, preprints) across "
    "arXiv, OpenAlex and Semantic Scholar at once, with duplicates merged. Use this "
    "FIRST whenever you need to find, list or cite research papers. Input: a short "
    "English keyword query (2-6 words). Not for plain definitions."
)
DESC_PUBMED_SEARCH = (
    "Search PubMed for biomedical and clinical literature (medicine, biology, health, "
    "genetics, pharmacology). Use IN ADDITION to paper_search when the question is "
    "biomedical. Input: English keywords."
)
DESC_DOI_LOOKUP = (
    "Look up authoritative metadata (title, year, venue, authors) of ONE paper by its "
    "DOI via Crossref. Use it to verify a paper's year or venue before stating them. "
    "Input: a DOI like 10.xxxx/yyyy."
)


# --------------------------------------------------------------------------- #
# Định dạng kết quả — thứ LLM đọc (SPEC §5.5)
# --------------------------------------------------------------------------- #
def _khoi_bai(stt: int, r: PaperRecord, abstract_chars: int) -> str:
    nhan = r.primary_label() or "(no citable ID)"
    # "Other IDs": mọi mã còn lại, đúng dạng grounding đọc được (doi:..., pmid:...).
    khac = [f"{k}:{v}" for k, v in r.ids.items() if k != "arxiv" and f"[{k}: {v}]" != nhan]
    tac_gia = ", ".join(r.authors[:SO_TAC_GIA_TOI_DA])
    if len(r.authors) > SO_TAC_GIA_TOI_DA:
        tac_gia += " et al."
    dong = [
        f"[{stt}] Title: {r.title}",
        f"    Label: {nhan}",
    ]
    if khac:
        dong.append(f"    Other IDs: {' | '.join(khac)}")
    dong += [
        f"    Published: {r.published or r.year or 'n/a'} | Venue: {r.venue or 'n/a'} | "
        f"Citations: {r.citations if r.citations is not None else 'n/a'}",
        f"    Authors: {tac_gia or 'n/a'}",
        f"    Found in: {', '.join(r.found_in)}",
        f"    Abstract: {cat_gon(r.abstract, abstract_chars) or 'n/a'}",
    ]
    return "\n".join(dong)


def format_records(
    tieu_de: str,
    nguon_da_goi: List[str],
    nguon_loi: Dict[str, str],
    tong_hit: int,
    records: List[PaperRecord],
    abstract_chars: int,
) -> str:
    dau = [
        f"{tieu_de}",
        f"Sources: {', '.join(nguon_da_goi)} | {len(records)} papers after merging {tong_hit} hits",
    ]
    if nguon_loi:
        dau.append("Sources unavailable: " + ", ".join(f"{s} ({c})" for s, c in nguon_loi.items()))
    khoi = [_khoi_bai(i, r, abstract_chars) for i, r in enumerate(records, 1)]
    cuoi = (
        "Cite every claim with the exact Label of the paper it comes from. "
        "Use the Published date for the year."
    )
    return "\n".join(dau) + "\n\n" + "\n\n".join(khoi) + "\n\n" + cuoi


def _tim_nguon(
    ten: str, mod, query: str, limit: int
) -> Tuple[List[PaperRecord], Optional[str]]:
    """Gọi một nguồn. Trả (bản ghi, mã lỗi). Không bao giờ raise."""
    try:
        return mod.search(query, limit), None
    except SourceError as exc:
        return [], exc.code
    except Exception:  # parser gặp dữ liệu bất ngờ: coi như nguồn hỏng, đi tiếp
        return [], f"{ten.upper()}_BAD_RESPONSE"


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
def make_paper_tools(budget: SearchBudget, profile: SearchProfile) -> list:
    """Dựng ba tool dùng chung một sổ lượt tìm kiếm (budget) và một profile."""
    from langchain_core.tools import StructuredTool

    da_tra_cuu: Dict[str, str] = {}   # DOI -> kết quả đã có, để tra trùng không gọi lại API
    so_lan_tra_cuu = [0]

    def paper_search(text: str) -> str:
        if not text or not text.strip():
            return tool_error("EMPTY_QUERY", "Cần một truy vấn để tìm bài báo.")
        tu_choi = budget.xin_luot("paper_search", text)
        if tu_choi is not None:
            return tu_choi
        q = text.strip()

        gop: List[PaperRecord] = []
        loi: Dict[str, str] = {}
        for ten in profile.paper_sources:  # TUẦN TỰ, không song song
            ket_qua, ma_loi = _tim_nguon(ten, NGUON_PAPER[ten], q, profile.per_source_limit)
            if ma_loi:
                loi[ten] = ma_loi
            gop += ket_qua
        if len(loi) == len(profile.paper_sources):
            return tool_error("ALL_SOURCES_FAILED", "; ".join(f"{s}: {c}" for s, c in loi.items()))
        if not gop:
            return (
                f'No papers found for "{q}" in {", ".join(profile.paper_sources)}. '
                "Try broader or different English keywords."
            )
        chon = rank_records(dedupe_records(gop), profile.max_results)
        return format_records(
            f'paper_search results for "{q}"',
            list(profile.paper_sources), loi, len(gop), chon, profile.abstract_chars,
        )

    def pubmed_search(text: str) -> str:
        if not text or not text.strip():
            return tool_error("EMPTY_QUERY", "Cần một truy vấn để tìm trên PubMed.")
        tu_choi = budget.xin_luot("pubmed_search", text)
        if tu_choi is not None:
            return tu_choi
        q = text.strip()
        ket_qua, ma_loi = _tim_nguon("pubmed", pubmed_source, q, profile.per_source_limit)
        if ma_loi:
            return tool_error(ma_loi, "PubMed không trả được kết quả.")
        if not ket_qua:
            return f'No papers found for "{q}" in pubmed. Try broader or different English keywords.'
        chon = rank_records(ket_qua, profile.max_results)
        return format_records(
            f'pubmed_search results for "{q}"', ["pubmed"], {}, len(ket_qua), chon, profile.abstract_chars
        )

    def doi_lookup(text: str) -> str:
        if not text or not text.strip():
            return tool_error("EMPTY_QUERY", "Cần một DOI.")
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)", "", text.strip(), flags=re.IGNORECASE).lower()
        if not DOI_RE.match(doi):
            return tool_error("INVALID_DOI", f"{text.strip()!r} không phải DOI dạng 10.xxxx/yyyy.")
        if doi in da_tra_cuu:  # tra trùng: trả lại kết quả cũ, không gọi API, không tốn lượt
            return da_tra_cuu[doi]
        if so_lan_tra_cuu[0] >= profile.max_lookups_per_topic:
            return tool_error(
                "LOOKUP_BUDGET_EXCEEDED",
                f"Tối đa {profile.max_lookups_per_topic} lượt tra DOI. Trả lời bằng dữ liệu đã có.",
            )
        so_lan_tra_cuu[0] += 1
        try:
            r = crossref_source.lookup(doi)
        except SourceError as exc:
            return tool_error(exc.code, exc.message)
        except Exception:
            return tool_error("CROSSREF_BAD_RESPONSE", "Không đọc được phản hồi của Crossref.")
        r.ids.setdefault("doi", doi)
        ket_qua = format_records(
            f"doi_lookup result for {doi}", ["crossref"], {}, 1, [r], profile.abstract_chars
        )
        da_tra_cuu[doi] = ket_qua
        return ket_qua

    meta = {"search_budget": budget}
    return [
        StructuredTool.from_function(
            func=paper_search, name="paper_search", description=DESC_PAPER_SEARCH,
            args_schema=SearchInput, metadata=meta,
        ),
        StructuredTool.from_function(
            func=pubmed_search, name="pubmed_search", description=DESC_PUBMED_SEARCH,
            args_schema=SearchInput, metadata=meta,
        ),
        StructuredTool.from_function(
            func=doi_lookup, name="doi_lookup", description=DESC_DOI_LOOKUP,
            args_schema=SearchInput,
        ),
    ]
