"""Test tool của Research Agent.

Các test gọi mạng thật được đánh dấu @pytest.mark.network. Khi mạng trường chập
chờn thì chạy: pytest -m "not network"
"""

from __future__ import annotations

import pytest

from app.core.contracts import ERROR_PREFIX
from app.agents.research_agent.tools import make_arxiv_tool, make_wikipedia_tool


def test_arxiv_truy_van_rong_tra_error_chuan():
    out = make_arxiv_tool().invoke({"text": "   "})
    assert out.startswith(ERROR_PREFIX) and "EMPTY_QUERY" in out


def test_wikipedia_truy_van_rong_tra_error_chuan():
    out = make_wikipedia_tool().invoke({"text": ""})
    assert out.startswith(ERROR_PREFIX) and "EMPTY_QUERY" in out


def _bo_qua_neu_mat_mang(out: str) -> str:
    """Mạng trường/proxy chặn thì SKIP, không FAIL — tránh test đỏ giả."""
    if out.startswith(ERROR_PREFIX) and "UNAVAILABLE" in out:
        pytest.skip(f"Không gọi được mạng ngoài: {out[:120]}")
    return out


@pytest.mark.network
def test_arxiv_tra_ve_bai_bao_that():
    out = _bo_qua_neu_mat_mang(
        make_arxiv_tool(top_k=1, max_chars=600).invoke({"text": "rotary positional embedding"})
    )
    assert "Title:" in out and "Published:" in out


@pytest.mark.network
def test_wikipedia_tra_ve_trang_that():
    out = _bo_qua_neu_mat_mang(
        make_wikipedia_tool(top_k=1, max_chars=800).invoke({"text": "machine learning"})
    )
    assert "Page:" in out and "Summary:" in out


@pytest.mark.network
def test_wikipedia_khong_dinh_loi_user_agent():
    """Wikimedia chặn User-Agent mặc định của requests -> body rỗng -> JSONDecodeError.

    Nếu quên set_user_agent, tool sẽ trả WIKIPEDIA_UNAVAILABLE kèm đúng thông báo
    'Expecting value: line 1 column 1 (char 0)'.
    """
    out = _bo_qua_neu_mat_mang(make_wikipedia_tool(top_k=1).invoke({"text": "transformer deep learning"}))
    assert "Expecting value: line 1 column 1" not in out


# --------------------------------------------------------------------------- #
# Dây phanh chống vòng lặp ReAct — chạy được offline, không tốn hạn mức
# --------------------------------------------------------------------------- #
from app.agents.research_agent.tools import SearchBudget


def test_budget_tu_choi_truy_van_lap_lai():
    b = SearchBudget(max_calls=10)
    assert b.xin_luot("arxiv_search", "rotary positional encoding") is None
    lan_hai = b.xin_luot("arxiv_search", "  Rotary   Positional Encoding ")
    assert lan_hai is not None and "DA TIM TRUY VAN NAY ROI" in lan_hai
    assert b.tong_luot == 1, "lời gọi bị từ chối không được tính vào sổ"


def test_budget_dung_chung_giua_hai_tool():
    """Hai tool chung MỘT sổ: tổng số lượt bị chặn, không phải mỗi tool một sổ."""
    b = SearchBudget(max_calls=2)
    assert b.xin_luot("arxiv_search", "a") is None
    assert b.xin_luot("wikipedia_search", "b") is None
    het = b.xin_luot("arxiv_search", "c")
    assert het is not None and "HET LUOT TIM KIEM" in het


def test_tool_het_luot_thi_khong_goi_mang():
    """Hết lượt phải trả lời ngay ở tầng tool, không đụng tới arXiv."""
    tool = make_arxiv_tool(budget=SearchBudget(max_calls=0))
    out = tool.invoke({"text": "rotary positional encoding"})
    assert "HET LUOT TIM KIEM" in out
    assert not out.startswith(ERROR_PREFIX)


def test_truy_van_rong_khong_tieu_luot():
    """Truy vấn rỗng là lỗi của model, không được trừ vào sổ lượt."""
    b = SearchBudget(max_calls=1)
    out = make_arxiv_tool(budget=b).invoke({"text": "   "})
    assert "EMPTY_QUERY" in out
    assert b.tong_luot == 0


# --------------------------------------------------------------------------- #
# Trích dẫn: kết quả arXiv phải mang mã bài báo thật và ĐÚNG ngày nộp
# --------------------------------------------------------------------------- #
from app.agents.research_agent.tools import format_arxiv_docs


def _hai_bai():
    return [
        {
            "entry_id": "http://arxiv.org/abs/2104.09864v5",
            "published": "2021-04-20",
            "updated": "2023-11-08",
            "title": "RoFormer: Enhanced Transformer with Rotary Position Embedding",
            "authors": "Jianlin Su, Yu Lu",
            "summary": "Tom tat bai mot. " * 40,
        },
        {
            "entry_id": "http://arxiv.org/abs/1706.03762v7",
            "published": "2017-06-12",
            "updated": "2023-08-02",
            "title": "Attention Is All You Need",
            "authors": "Ashish Vaswani",
            "summary": "Tom tat bai hai. " * 40,
        },
    ]


def test_ket_qua_arxiv_co_kem_entry_id():
    """Không có Entry ID trong kết quả thì model sẽ bịa mã bài báo."""
    out = format_arxiv_docs(_hai_bai(), max_chars=1000)
    assert "http://arxiv.org/abs/2104.09864v5" in out
    assert "http://arxiv.org/abs/1706.03762v7" in out


def test_published_la_ngay_nop_khong_phai_ngay_sua():
    """Bẫy của langchain: wrapper in result.updated dưới nhãn 'Published'.

    Hậu quả: RoFormer nộp 04/2021 bị trích dẫn thành 2023 — sai năm mà nhìn rất thật.
    """
    out = format_arxiv_docs(_hai_bai(), max_chars=1000)
    assert "Published: 2021-04-20" in out
    assert "Last updated: 2023-11-08" in out


def test_cat_bot_theo_tung_bai_khong_nuot_mat_bai_cuoi():
    """Cắt cả chuỗi sẽ làm bài cuối mất luôn Entry ID + Title — thứ đáng giữ nhất."""
    out = format_arxiv_docs(_hai_bai(), max_chars=600)
    assert out.count("Entry ID:") == 2
    assert "Attention Is All You Need" in out
