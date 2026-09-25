"""Test ba tool lá của scholar_agent: paper_search, pubmed_search, doi_lookup. OFFLINE.

Các nguồn được thay bằng hàm giả (monkeypatch `search`/`lookup`), nên không có
lời gọi HTTP nào. Test parser và HTTP nằm ở test_research_sources.py.
"""

from __future__ import annotations

from app.agents.research_agent import paper_tools
from app.agents.research_agent.profiles import PROFILES
from app.agents.research_agent.sources.base import PaperRecord, SourceError
from app.agents.research_agent.tools import SearchBudget
from app.core.contracts import validate_tool


def _bo_tool(profile="standard", max_searches=None):
    p = PROFILES[profile]
    budget = SearchBudget(max_calls=max_searches or p.max_searches_per_topic)
    return {t.name: t for t in paper_tools.make_paper_tools(budget, p)}


def _gia_nguon(monkeypatch, **theo_nguon):
    """theo_nguon: tên nguồn -> list bản ghi (trả về) hoặc Exception (ném ra)."""
    for ten, gia_tri in theo_nguon.items():
        def search(q, limit, _v=gia_tri):
            if isinstance(_v, Exception):
                raise _v
            return list(_v)
        monkeypatch.setattr(paper_tools.NGUON_PAPER[ten], "search", search)


ROFORMER_ARXIV = PaperRecord(
    title="RoFormer: Enhanced Transformer with Rotary Position Embedding", year=2021, published="2021-04-20",
    authors=["A", "B", "C", "D"], venue="arXiv", abstract="x" * 900, ids={"arxiv": "2104.09864v5"},
    found_in=["arxiv"],
)
ROFORMER_OA = PaperRecord(
    title="RoFormer: Enhanced Transformer with Rotary Position Embedding", year=2023, published="2023-12-01",
    citations=1200, ids={"doi": "10.1016/j.neucom.2023.127063", "openalex": "W3155807546", "arxiv": "2104.09864"},
    found_in=["openalex"],
)


def test_paper_tools_dung_hop_dong_ba_tool():
    tools = _bo_tool()
    assert set(tools) == {"paper_search", "pubmed_search", "doi_lookup"}
    for t in tools.values():
        validate_tool(t)
        assert t.return_direct is False
        assert t.description.isascii() and len(t.description) >= 20


def test_paper_search_dinh_dang_dung_spec(monkeypatch):
    _gia_nguon(
        monkeypatch,
        arxiv=[ROFORMER_ARXIV],
        openalex=[ROFORMER_OA],
        semantic_scholar=SourceError("SEMANTIC_SCHOLAR_RATE_LIMITED", "429"),
    )
    kq = _bo_tool()["paper_search"].invoke({"text": "rotary position embedding"})
    assert 'paper_search results for "rotary position embedding"' in kq
    assert "Sources: arxiv, openalex, semantic_scholar | 1 papers after merging 2 hits" in kq
    assert "Sources unavailable: semantic_scholar (SEMANTIC_SCHOLAR_RATE_LIMITED)" in kq
    assert "Label: [http://arxiv.org/abs/2104.09864v5]" in kq
    assert "Other IDs: doi:10.1016/j.neucom.2023.127063 | openalex:W3155807546" in kq
    assert "Published: 2021-04-20" in kq  # ngày nộp của arXiv thắng 2023-12-01
    assert "Authors: A, B, C et al." in kq
    assert "Found in: arxiv, openalex" in kq
    abstract = kq.split("Abstract: ")[1].split("\n")[0]
    assert len(abstract) <= PROFILES["standard"].abstract_chars + 3
    assert kq.rstrip().endswith("Use the Published date for the year.")


def test_paper_search_bang_chung_qua_duoc_grounding(monkeypatch):
    from app.core.grounding import kiem_tra_grounding

    _gia_nguon(monkeypatch, arxiv=[ROFORMER_ARXIV], openalex=[ROFORMER_OA], semantic_scholar=[])
    kq = _bo_tool()["paper_search"].invoke({"text": "rope"})
    cau = (
        "RoPE rotates query and key vectors to encode position [http://arxiv.org/abs/2104.09864v5]. "
        "It was later published in a journal [doi: 10.1016/j.neucom.2023.127063]."
    )
    assert kiem_tra_grounding(cau, [kq]) == []


def test_paper_search_mot_nguon_loi_van_co_ket_qua(monkeypatch):
    _gia_nguon(
        monkeypatch,
        arxiv=[ROFORMER_ARXIV],
        openalex=SourceError("OPENALEX_NOT_CONFIGURED", "no key"),
        semantic_scholar=[],
    )
    kq = _bo_tool()["paper_search"].invoke({"text": "rope"})
    assert not kq.startswith("ERROR")
    assert "openalex (OPENALEX_NOT_CONFIGURED)" in kq  # thiếu key = nguồn không khả dụng, không chết


def test_paper_search_moi_nguon_loi(monkeypatch):
    _gia_nguon(
        monkeypatch,
        arxiv=SourceError("ARXIV_UNAVAILABLE", "x"),
        openalex=SourceError("OPENALEX_NOT_CONFIGURED", "x"),
        semantic_scholar=SourceError("SEMANTIC_SCHOLAR_RATE_LIMITED", "x"),
    )
    kq = _bo_tool()["paper_search"].invoke({"text": "rope"})
    assert kq.startswith("ERROR: ALL_SOURCES_FAILED |")
    assert "arxiv: ARXIV_UNAVAILABLE" in kq and "openalex: OPENALEX_NOT_CONFIGURED" in kq


def test_paper_search_khong_co_ket_qua_tra_cau_thong_bao(monkeypatch):
    _gia_nguon(monkeypatch, arxiv=[], openalex=[], semantic_scholar=[])
    kq = _bo_tool()["paper_search"].invoke({"text": "xqzvbn"})
    assert kq.startswith('No papers found for "xqzvbn"')


def test_paper_search_parser_nem_exception_bat_ngo_van_tra_chuoi(monkeypatch):
    _gia_nguon(monkeypatch, arxiv=[ROFORMER_ARXIV], openalex=KeyError("boom"), semantic_scholar=[])
    kq = _bo_tool()["paper_search"].invoke({"text": "rope"})
    assert isinstance(kq, str) and "openalex (OPENALEX_BAD_RESPONSE)" in kq


def test_paper_search_truy_van_rong_trung_va_het_luot(monkeypatch):
    _gia_nguon(monkeypatch, arxiv=[ROFORMER_ARXIV], openalex=[], semantic_scholar=[])
    t = _bo_tool(max_searches=2)["paper_search"]
    assert t.invoke({"text": "  "}).startswith("ERROR: EMPTY_QUERY")
    assert not t.invoke({"text": "rope"}).startswith(("ERROR", "DA TIM"))
    assert t.invoke({"text": "ROPE"}).startswith("DA TIM TRUY VAN NAY ROI")  # trùng, không phân biệt hoa thường
    assert not t.invoke({"text": "other query"}).startswith("HET LUOT")
    assert t.invoke({"text": "third query"}).startswith("HET LUOT TIM KIEM")


def test_pubmed_search_dung_loi_va_chung_so_luot(monkeypatch):
    bai = PaperRecord(
        title="CRISPR in SCD", year=2021, ids={"pmid": "31000001", "doi": "10.1056/x"}, found_in=["pubmed"]
    )
    monkeypatch.setattr(paper_tools.pubmed_source, "search", lambda q, n: [bai])
    tools = _bo_tool(max_searches=1)
    kq = tools["pubmed_search"].invoke({"text": "crispr sickle"})
    assert "Label: [doi: 10.1056/x]" in kq and "pmid:31000001" in kq
    # Chung sổ với paper_search: đã hết 1 lượt thì paper_search cũng bị từ chối.
    assert tools["paper_search"].invoke({"text": "anything"}).startswith("HET LUOT TIM KIEM")

    def hong(q, n):
        raise SourceError("PUBMED_RATE_LIMITED", "429")

    monkeypatch.setattr(paper_tools.pubmed_source, "search", hong)
    assert _bo_tool()["pubmed_search"].invoke({"text": "x"}).startswith("ERROR: PUBMED_RATE_LIMITED")


def test_doi_lookup_dung_va_loi(monkeypatch):
    def lookup(doi):
        if doi.endswith("none"):
            raise SourceError("DOI_NOT_FOUND", "khong co")
        return PaperRecord(title="RoFormer", year=2024, venue="Neurocomputing", found_in=["crossref"])

    monkeypatch.setattr(paper_tools.crossref_source, "lookup", lookup)
    t = _bo_tool()["doi_lookup"]
    kq = t.invoke({"text": "https://doi.org/10.1016/J.NEUCOM.2023.127063"})
    assert "Label: [doi: 10.1016/j.neucom.2023.127063]" in kq and "Venue: Neurocomputing" in kq
    assert t.invoke({"text": "10.9999/none"}).startswith("ERROR: DOI_NOT_FOUND")
    assert t.invoke({"text": "not a doi"}).startswith("ERROR: INVALID_DOI")
    assert t.invoke({"text": ""}).startswith("ERROR: EMPTY_QUERY")


def test_doi_lookup_tra_trung_khong_goi_lai_va_co_tran_rieng(monkeypatch):
    goi = []
    monkeypatch.setattr(
        paper_tools.crossref_source,
        "lookup",
        lambda doi: goi.append(doi) or PaperRecord(title="T", found_in=["crossref"]),
    )
    p = PROFILES["eco"]  # max_lookups_per_topic = 1
    t = {x.name: x for x in paper_tools.make_paper_tools(SearchBudget(max_calls=5), p)}["doi_lookup"]
    truoc = t.invoke({"text": "10.1234/aaa"})
    assert t.invoke({"text": "10.1234/AAA"}) == truoc and len(goi) == 1  # tra trùng: không gọi API lần hai
    assert t.invoke({"text": "10.1234/bbb"}).startswith("ERROR: LOOKUP_BUDGET_EXCEEDED")
    assert len(goi) == 1
