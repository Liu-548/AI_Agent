"""Test lớp nguồn học thuật + tool lá của scholar_agent. Chạy OFFLINE hoàn toàn.

HTTP được giả bằng cách thay `requests.get` trong sources.base; dữ liệu mẫu nằm
ở tests/fixtures/research/ (đã cắt gọn, không chứa key hay email thật).
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest
import requests

from app.agents.research_agent.sources import base
from app.agents.research_agent.sources import (
    arxiv_source,
    crossref_source,
    openalex_source,
    pubmed_source,
    semantic_scholar_source,
)
from app.agents.research_agent.sources.base import PaperRecord, SourceError, dedupe_records, rank_records
from app.core import config

FIXTURES = Path(__file__).parent / "fixtures" / "research"


def doc(ten: str) -> str:
    return (FIXTURES / ten).read_text(encoding="utf-8")


class FakeResp:
    def __init__(self, status=200, text="{}"):
        self.status_code = status
        self.text = text

    def json(self):
        return json.loads(self.text)


class FakeHttp:
    """Thay requests.get: trả lần lượt các phản hồi đã hẹn, ghi lại mọi lời gọi."""

    def __init__(self, *phan_hoi):
        self.phan_hoi = list(phan_hoi)
        self.goi = []

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.goi.append({"url": url, "params": params, "headers": headers})
        p = self.phan_hoi.pop(0) if len(self.phan_hoi) > 1 else self.phan_hoi[0]
        if isinstance(p, Exception):
            raise p
        return p


@pytest.fixture
def http(monkeypatch):
    """Cài một FakeHttp và tắt time.sleep để test retry không phải chờ thật."""

    def cai(*phan_hoi):
        fake = FakeHttp(*phan_hoi)
        monkeypatch.setattr(base.requests, "get", fake)
        return fake

    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    return cai


def dung_settings(monkeypatch, **thay_doi):
    monkeypatch.setattr(config, "settings", replace(config.settings, **thay_doi))


# --------------------------------------------------------------------------- #
# Parser từng nguồn
# --------------------------------------------------------------------------- #
def test_openalex_parse_abstract_id_doi_pmid_arxiv():
    ban_ghi = [openalex_source.parse_work(w, i) for i, w in enumerate(json.loads(doc("openalex_works.json"))["results"])]
    a, b = ban_ghi
    assert a.abstract == "Position encoding matters a matters lot"
    assert a.ids == {
        "openalex": "W3155807546",
        "doi": "10.1016/j.neucom.2023.127063",
        "pmid": "12345678",
        "arxiv": "2104.09864",
    }
    assert (a.venue, a.year, a.citations, a.found_in) == ("Neurocomputing", 2023, 1200, ["openalex"])
    assert a.authors[:2] == ["Jianlin Su", "Yu Lu"]
    # Bản ghi thiếu gần hết trường vẫn không làm parser vỡ.
    assert (b.abstract, b.venue, b.authors, b.ids) == (None, None, [], {"openalex": "W1234567890"})


def test_semantic_scholar_parse_external_ids():
    p = semantic_scholar_source.parse_paper(json.loads(doc("semantic_scholar_search.json"))["data"][0])
    assert p.ids["doi"] == "10.1016/j.neucom.2023.127063"
    assert (p.ids["arxiv"], p.ids["pmid"]) == ("2104.09864", "12345678")
    assert p.ids["s2"] == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
    assert p.published == "2021-04-20"


def test_pubmed_parse_abstract_nhieu_doan_va_medlinedate():
    import xml.etree.ElementTree as ET

    a, b = pubmed_source.parse_efetch(ET.fromstring(doc("pubmed_efetch.xml")))
    assert a.title == "CRISPR-Cas9 editing in sickle cell disease."  # thẻ <i> được giữ chữ
    assert a.abstract == "Sickle cell disease is a monogenic disorder. We edited BCL11A enhancers in patient cells."
    assert (a.year, a.venue, a.authors) == (2021, "New England Journal of Medicine", ["Frangoul H", "Locatelli F"])
    assert a.ids == {"pmid": "31000001", "doi": "10.1056/nejmoa2031054"}
    assert b.year == 2019  # MedlineDate "2019 Dec-2020 Jan" -> 4 số đầu
    assert b.abstract is None


def test_crossref_parse_date_parts_va_bo_the_jats():
    r = crossref_source.parse_message(json.loads(doc("crossref_work.json"))["message"])
    assert (r.year, r.published, r.venue) == (2024, "2024-01-28", "Neurocomputing")
    assert r.abstract == "Position encoding in transformer architecture."
    assert r.authors == ["Jianlin Su", "Yu Lu"]


def test_arxiv_published_la_ngay_nop_va_bo_bai_bi_rut():
    ket_qua = arxiv_source.parse_items(json.loads(doc("arxiv_items.json")))
    assert len(ket_qua) == 1  # bài withdrawn bị bỏ
    r = ket_qua[0]
    assert (r.published, r.year, r.ids) == ("2021-04-20", 2021, {"arxiv": "2104.09864v5"})
    assert r.title == "RoFormer: Enhanced Transformer with Rotary Position Embedding"
    assert r.primary_label() == "[http://arxiv.org/abs/2104.09864v5]"


def test_primary_label_uu_tien_arxiv_doi_pmid_openalex_s2():
    r = PaperRecord(title="x", ids={"s2": "b" * 40, "openalex": "W1234567", "pmid": "9", "doi": "10.1/a"})
    assert r.primary_label() == "[doi: 10.1/a]"
    del r.ids["doi"]
    assert r.primary_label() == "[pmid: 9]"
    del r.ids["pmid"]
    assert r.primary_label() == "[openalex: W1234567]"
    assert PaperRecord(title="x").primary_label() == ""


# --------------------------------------------------------------------------- #
# http_get
# --------------------------------------------------------------------------- #
def test_http_timeout_thanh_unavailable(http):
    http(requests.Timeout("boom https://x?api_key=SECRETKEY123"))
    with pytest.raises(SourceError) as e:
        base.http_get("openalex", "https://x")
    assert e.value.code == "OPENALEX_UNAVAILABLE"
    assert "SECRETKEY123" not in str(e.value)  # thông điệp lỗi không được chứa key


def test_http_429_thu_lai_mot_lan_roi_rate_limited(http):
    fake = http(FakeResp(429))
    with pytest.raises(SourceError) as e:
        base.http_get("semantic_scholar", "https://x")
    assert e.value.code == "SEMANTIC_SCHOLAR_RATE_LIMITED"
    assert len(fake.goi) == 2  # đúng một lần thử lại


def test_http_5xx_thu_lai_roi_thanh_cong(http):
    fake = http(FakeResp(503), FakeResp(200, '{"ok": 1}'))
    assert base.http_get("pubmed", "https://x") == {"ok": 1}
    assert len(fake.goi) == 2


def test_http_loi_khac_va_body_hong(http):
    http(FakeResp(404))
    with pytest.raises(SourceError) as e:
        base.http_get("crossref", "https://x")
    assert (e.value.code, e.value.status) == ("CROSSREF_HTTP_ERROR", 404)
    http(FakeResp(200, "<html>not json"))
    with pytest.raises(SourceError) as e:
        base.http_get("crossref", "https://x")
    assert e.value.code == "CROSSREF_BAD_RESPONSE"
    http(FakeResp(200, "not xml"))
    with pytest.raises(SourceError) as e:
        base.http_get("pubmed", "https://x", expect="xml")
    assert e.value.code == "PUBMED_BAD_RESPONSE"


def test_key_khong_bao_gio_xuat_hien_trong_log(http, monkeypatch, caplog):
    dung_settings(monkeypatch, openalex_api_key="SECRETKEY123")
    http(FakeResp(200, doc("openalex_works.json")))
    with caplog.at_level(logging.DEBUG):
        openalex_source.search("rope", 2)
    assert "SECRETKEY123" not in caplog.text
    assert "***" in caplog.text


# --------------------------------------------------------------------------- #
# Hành vi của từng nguồn qua HTTP giả
# --------------------------------------------------------------------------- #
def test_openalex_thieu_key_khong_goi_http(http, monkeypatch):
    dung_settings(monkeypatch, openalex_api_key="")
    fake = http(FakeResp(200, doc("openalex_works.json")))
    with pytest.raises(SourceError) as e:
        openalex_source.search("rope", 2)
    assert e.value.code == "OPENALEX_NOT_CONFIGURED"
    assert fake.goi == []


def test_openalex_co_key_gui_api_key_va_select(http, monkeypatch):
    dung_settings(monkeypatch, openalex_api_key="K")
    fake = http(FakeResp(200, doc("openalex_works.json")))
    ket_qua = openalex_source.search("rope", 2)
    assert len(ket_qua) == 2
    assert fake.goi[0]["params"]["api_key"] == "K" and "select" in fake.goi[0]["params"]


def test_semantic_scholar_chi_gui_header_khi_co_key(http, monkeypatch):
    fake = http(FakeResp(200, doc("semantic_scholar_search.json")))
    dung_settings(monkeypatch, semantic_scholar_api_key="")
    semantic_scholar_source.search("rope", 2)
    assert "x-api-key" not in fake.goi[0]["headers"]
    dung_settings(monkeypatch, semantic_scholar_api_key="S2KEY")
    semantic_scholar_source.search("rope", 2)
    assert fake.goi[1]["headers"]["x-api-key"] == "S2KEY"


def test_pubmed_hai_buoc_esearch_roi_efetch(http):
    fake = http(FakeResp(200, doc("pubmed_esearch.json")), FakeResp(200, doc("pubmed_efetch.xml")))
    ket_qua = pubmed_source.search("crispr sickle cell", 2)
    assert [r.ids["pmid"] for r in ket_qua] == ["31000001", "31000002"]
    assert "esearch" in fake.goi[0]["url"] and "efetch" in fake.goi[1]["url"]
    assert fake.goi[1]["params"]["id"] == "31000001,31000002"


def test_pubmed_khong_co_ket_qua_thi_khong_goi_efetch(http):
    fake = http(FakeResp(200, '{"esearchresult": {"idlist": []}}'))
    assert pubmed_source.search("zzzz", 2) == []
    assert len(fake.goi) == 1


def test_crossref_lookup_dung_va_404(http):
    http(FakeResp(200, doc("crossref_work.json")))
    assert crossref_source.lookup("10.1016/j.neucom.2023.127063").year == 2024
    http(FakeResp(404))
    with pytest.raises(SourceError) as e:
        crossref_source.lookup("10.9999/none")
    assert e.value.code == "DOI_NOT_FOUND"


# --------------------------------------------------------------------------- #
# Khử trùng + xếp hạng
# --------------------------------------------------------------------------- #
def _rec(nguon, title="RoFormer: Enhanced Transformer", year=2021, rank=0, **kw):
    return PaperRecord(title=title, year=year, found_in=[nguon], rank=rank, **kw)


def test_dedupe_gop_qua_doi():
    a = _rec("openalex", ids={"doi": "10.1/x", "openalex": "W1111111"}, citations=10)
    b = _rec("semantic_scholar", title="Completely different title", ids={"doi": "10.1/X"}, citations=99)
    (g,) = dedupe_records([a, b])
    assert g.found_in == ["openalex", "semantic_scholar"]
    assert g.citations == 99 and g.ids["openalex"] == "W1111111"


def test_dedupe_gop_qua_ma_arxiv_khac_version():
    a = _rec("arxiv", title="Title A", ids={"arxiv": "2104.09864v5"})
    b = _rec("semantic_scholar", title="Title B", ids={"arxiv": "2104.09864v1"})
    assert len(dedupe_records([a, b])) == 1


def test_dedupe_gop_qua_tieu_de_va_nam():
    a = _rec("openalex", title="Attention: Is All You Need!", year=2017)
    b = _rec("semantic_scholar", title="attention is all you need", year=2017)
    c = _rec("pubmed", title="Attention is all you need", year=None)  # thiếu năm vẫn gộp
    assert len(dedupe_records([a, b, c])) == 1


def test_dedupe_khong_gop_cung_tieu_de_khac_nam_xa():
    a = _rec("openalex", title="Survey of methods", year=2010)
    b = _rec("openalex", title="Survey of methods", year=2021)
    assert len(dedupe_records([a, b])) == 2


def test_dedupe_published_cua_arxiv_thang_va_abstract_dai_nhat():
    ax = _rec("arxiv", ids={"arxiv": "2104.09864v5", "doi": "10.1/x"}, published="2021-04-20", abstract="short")
    oa = _rec("openalex", ids={"doi": "10.1/x"}, published="2023-12-01", year=2023, abstract="a much longer abstract")
    (g,) = dedupe_records([oa, ax])
    assert (g.published, g.abstract) == ("2021-04-20", "a much longer abstract")
    assert set(g.found_in) == {"arxiv", "openalex"}


def test_rank_nhieu_nguon_truoc_roi_thu_hang():
    nhieu = PaperRecord(title="many", found_in=["arxiv", "openalex"], rank=5)
    som = PaperRecord(title="early", found_in=["arxiv"], rank=0)
    muon = PaperRecord(title="late", found_in=["arxiv"], rank=3)
    assert [r.title for r in rank_records([muon, som, nhieu], 2)] == ["many", "early"]
