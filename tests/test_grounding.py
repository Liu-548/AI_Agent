"""Test bộ đối chiếu câu trả lời với kết quả tool.

Toàn bộ chạy offline, không gọi LLM, không tốn hạn mức — đây chính là lý do
phần kiểm tra được viết thành hàm thuần thay vì nhét vào prompt.
"""

from __future__ import annotations

from app.core.grounding import bao_cao, kiem_tra_grounding, ma_arxiv_trong, tach_cau

TOOL_ARXIV = """Entry ID: http://arxiv.org/abs/2104.09864v5
Published: 2021-04-20
Last updated: 2023-11-08
Title: RoFormer: Enhanced Transformer with Rotary Position Embedding
Authors: Jianlin Su, Yu Lu
Summary: We propose Rotary Position Embedding (RoPE) to encode position."""

TOOL_WIKI = """Page: Transformer (deep learning)
Summary: Transformers inject positional information through positional encodings."""


def test_cau_tra_loi_co_nhan_dung_thi_khong_vi_pham():
    tra_loi = (
        "RoPE encodes absolute position with a rotation matrix "
        "[http://arxiv.org/abs/2104.09864v5].\n"
        "Transformers inject positional information through positional encodings "
        "[wikipedia: Transformer (deep learning)]."
    )
    assert kiem_tra_grounding(tra_loi, [TOOL_ARXIV, TOOL_WIKI]) == []


def test_bat_duoc_ma_arxiv_bia():
    """Lỗi thật đã gặp: model ghi 2305.13052 trong khi RoFormer là 2104.09864."""
    tra_loi = "RoPE was introduced by RoFormer [arXiv:2305.13052]."
    vi_pham = kiem_tra_grounding(tra_loi, [TOOL_ARXIV])
    assert any(v.startswith("MA_BIA") and "2305.13052" in v for v in vi_pham)


def test_bat_duoc_cau_khong_co_nguon():
    """Lỗi thật đã gặp: 'RoPE has been adopted in GPT-4, LLaMA-2' — không tool nào nói thế."""
    tra_loi = (
        "RoPE encodes position with a rotation matrix "
        "[http://arxiv.org/abs/2104.09864v5].\n"
        "RoPE has been adopted in many large language models such as GPT-4 and LLaMA-2."
    )
    vi_pham = kiem_tra_grounding(tra_loi, [TOOL_ARXIV])
    assert any(v.startswith("THIEU_NGUON") and "GPT-4" in v for v in vi_pham)
    assert not any(v.startswith("MA_BIA") for v in vi_pham)


def test_bat_duoc_nhan_tro_toi_nguon_khong_ton_tai():
    tra_loi = "RoPE rotates queries and keys [wikipedia: Rotary position embedding]."
    vi_pham = kiem_tra_grounding(tra_loi, [TOOL_ARXIV, TOOL_WIKI])
    assert any(v.startswith("NHAN_BIA") for v in vi_pham)


def test_tu_choi_tra_loi_thi_khong_bi_bat_loi():
    """'Không đủ dữ liệu' là câu trả lời hợp lệ, không được phạt nó."""
    tra_loi = "KHONG DU DU LIEU: không có kết quả nào nói về ứng dụng của RoPE trong đồ thị."
    assert kiem_tra_grounding(tra_loi, [TOOL_ARXIV]) == []


def test_tieu_de_va_gach_dau_dong_ngan_khong_bi_bat():
    tra_loi = "## Rotary Position Embedding\n- RoPE\nMot cau rat dai can phai co nguon o day."
    vi_pham = kiem_tra_grounding(tra_loi, [TOOL_ARXIV])
    assert len(vi_pham) == 1 and vi_pham[0].startswith("THIEU_NGUON")


def test_ma_arxiv_nhan_moi_cach_viet():
    assert ma_arxiv_trong("xem http://arxiv.org/abs/2104.09864v5") == ["2104.09864"]
    assert ma_arxiv_trong("xem arXiv: 1706.03762") == ["1706.03762"]


def test_tach_cau_bo_ky_hieu_markdown():
    assert tach_cau("- Mot cau. Hai cau!\n\n# Tieu de") == ["Mot cau.", "Hai cau!", "Tieu de"]


def test_bao_cao_khi_sach_va_khi_ban():
    assert "OK" in bao_cao([])
    ra = bao_cao(["MA_BIA: arXiv 1234.5678 không có trong bất kỳ kết quả tool nào"])
    assert "1 chỗ chưa có nguồn" in ra and "MA_BIA" in ra


def test_nhan_dung_sau_dau_cham_van_tinh_la_co_nguon():
    """Hồi quy: regex tách câu từng cắt nhãn thành 'câu' riêng.

    Hậu quả là bộ kiểm tra báo THIEU_NGUON cho cả 4 câu trong một lần chạy thật,
    dù model đã gắn nhãn hoàn toàn đúng — kiểu báo động giả làm người dùng mất
    lòng tin vào chính bộ kiểm tra rồi tắt nó đi.
    """
    tra_loi = (
        "RoPE encodes relative positions and supports length extrapolation. "
        "[http://arxiv.org/abs/2104.09864v5]\n"
        "Transformers inject positional information through positional encodings. "
        "[wikipedia: Transformer (deep learning)]"
    )
    assert kiem_tra_grounding(tra_loi, [TOOL_ARXIV, TOOL_WIKI]) == []


def test_nhan_nam_tren_dong_rieng_van_tinh():
    tra_loi = (
        "RoPE encodes relative positions and supports length extrapolation.\n"
        "[http://arxiv.org/abs/2104.09864v5]"
    )
    assert kiem_tra_grounding(tra_loi, [TOOL_ARXIV]) == []


def test_bao_cao_khong_doa_ma_bia_khi_chi_thieu_nguon():
    ra = bao_cao(["THIEU_NGUON: mot cau nao do"])
    assert "MA_BIA" not in ra
    assert "nhãn" in ra.lower()
