"""Test GỌI MẠNG THẬT cho các nguồn học thuật — chỉ API học thuật miễn phí, KHÔNG gọi LLM.

Đánh dấu @pytest.mark.network; chạy một lần cuối phase:
    python -m pytest -q -m network -k research_sources

Mất mạng, nguồn báo 429/5xx, hoặc thiếu key (OpenAlex) -> SKIP chứ không FAIL (TS-03).
Chỉ kiểm tra CẤU TRÚC kết quả, không kiểm tra nội dung cụ thể (nội dung thay đổi theo thời gian).
Lưu ý: conftest.py xoá biến môi trường của dự án, nên test OpenAlex chỉ chạy khi bạn tự đặt
key trong test (vd `$env:OPENALEX_API_KEY` không đủ) — xem hàm _can_key bên dưới.
"""

from __future__ import annotations

import os

import pytest

from app.agents.research_agent.sources import (
    arxiv_source,
    crossref_source,
    openalex_source,
    pubmed_source,
    semantic_scholar_source,
)
from app.agents.research_agent.sources.base import PaperRecord, SourceError

pytestmark = pytest.mark.network

# Các mã lỗi nghĩa là "môi trường không cho gọi" chứ không phải code sai.
MA_BO_QUA = ("_UNAVAILABLE", "_RATE_LIMITED", "_NOT_CONFIGURED")


def _goi(ham, *args):
    try:
        return ham(*args)
    except SourceError as exc:
        if exc.code.endswith(MA_BO_QUA):
            pytest.skip(f"{exc.code}: nguồn không khả dụng lúc này")
        raise


def _kiem_cau_truc(ket_qua):
    assert ket_qua, "nguồn khả dụng mà không trả về bài nào"
    for r in ket_qua:
        assert isinstance(r, PaperRecord) and r.title
        assert r.found_in and r.ids and r.primary_label().startswith("[")
        assert r.year is None or 1900 < r.year < 2100


def test_research_sources_arxiv_that():
    _kiem_cau_truc(_goi(arxiv_source.search, "rotary position embedding", 2))


def test_research_sources_openalex_that(monkeypatch):
    from app.core import config

    key = os.environ.get("OPENALEX_API_KEY_FOR_TESTS", "")  # conftest xoá OPENALEX_API_KEY
    if not key:
        pytest.skip("Đặt OPENALEX_API_KEY_FOR_TESTS để chạy test OpenAlex thật")
    from dataclasses import replace

    monkeypatch.setattr(config, "settings", replace(config.settings, openalex_api_key=key))
    _kiem_cau_truc(_goi(openalex_source.search, "rotary position embedding", 2))


def test_research_sources_semantic_scholar_that():
    _kiem_cau_truc(_goi(semantic_scholar_source.search, "rotary position embedding", 2))


def test_research_sources_pubmed_that():
    ket_qua = _goi(pubmed_source.search, "CRISPR sickle cell disease", 2)
    _kiem_cau_truc(ket_qua)
    assert all(r.ids.get("pmid") for r in ket_qua)


def test_research_sources_crossref_that():
    r = _goi(crossref_source.lookup, "10.1038/nature14539")  # LeCun, Bengio, Hinton - Deep learning
    assert r.title and r.year == 2015 and r.ids["doi"] == "10.1038/nature14539"
