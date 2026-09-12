"""Test bộ kiểm tra tính xác thực của nguồn (retracted/withdrawn).

Toàn bộ chạy offline, không gọi LLM, không tốn hạn mức -- giống test_grounding.py.
"""

from __future__ import annotations

from app.core.authenticity import bao_cao_xac_thuc, kiem_tra_xac_thuc, nguon_da_rut

TOOL_ARXIV_BINH_THUONG = """Entry ID: http://arxiv.org/abs/2104.09864v5
Published: 2021-04-20
Last updated: 2023-11-08
Title: RoFormer: Enhanced Transformer with Rotary Position Embedding
Authors: Jianlin Su, Yu Lu
Summary: We propose Rotary Position Embedding (RoPE) to encode position."""

TOOL_ARXIV_DA_RUT = """Entry ID: http://arxiv.org/abs/9999.99999v1
Published: 2020-01-01
Last updated: 2020-02-01
Title: Bai bao bi rut
Authors: Ai Do
Summary: Mot phat hien gay tranh cai.
Withdrawn: CÓ — tác giả đã rút bài này trên arXiv, KHÔNG dùng làm căn cứ trả lời"""

TOOL_OPENALEX_DA_RUT = """OpenAlex ID: https://openalex.org/W1234567890
DOI: https://doi.org/10.0000/fake
Published: 2019
Title: Nghien cuu da bi rut
Authors: Ai Do Khac
Cited by: 5
Summary: Tom tat.
Retracted: CÓ — OpenAlex đánh dấu bài này đã bị RÚT, KHÔNG dùng làm căn cứ trả lời"""


def test_nguon_binh_thuong_khong_bi_gan_co():
    assert nguon_da_rut([TOOL_ARXIV_BINH_THUONG]) == {}


def test_nhan_dien_arxiv_bi_rut():
    co = nguon_da_rut([TOOL_ARXIV_DA_RUT])
    assert "9999.99999" in co


def test_nhan_dien_openalex_bi_rut():
    co = nguon_da_rut([TOOL_OPENALEX_DA_RUT])
    assert "W1234567890" in co


def test_khong_trich_dan_nguon_bi_rut_thi_khong_vi_pham():
    """Nguồn bị rút nằm trong kết quả tool nhưng model không dùng -> không phải lỗi."""
    tra_loi = "RoPE mã hoá vị trí bằng phép quay [http://arxiv.org/abs/2104.09864v5]."
    vi_pham = kiem_tra_xac_thuc(tra_loi, [TOOL_ARXIV_BINH_THUONG, TOOL_ARXIV_DA_RUT])
    assert vi_pham == []


def test_trich_dan_nguon_arxiv_bi_rut_thi_bi_bat():
    tra_loi = "Phát hiện này rất quan trọng [arXiv:9999.99999]."
    vi_pham = kiem_tra_xac_thuc(tra_loi, [TOOL_ARXIV_DA_RUT])
    assert any(v.startswith("NGUON_RUT") and "9999.99999" in v for v in vi_pham)


def test_trich_dan_nguon_openalex_bi_rut_thi_bi_bat():
    tra_loi = (
        "NGUỒN\n[1] Nghien cuu da bi rut (2019)\n    - https://openalex.org/W1234567890\n"
    )
    vi_pham = kiem_tra_xac_thuc(tra_loi, [TOOL_OPENALEX_DA_RUT])
    assert any(v.startswith("NGUON_RUT") and "W1234567890" in v for v in vi_pham)


def test_bao_cao_khi_sach_va_khi_ban():
    assert "OK" in bao_cao_xac_thuc([])
    ra = bao_cao_xac_thuc(["NGUON_RUT: 9999.99999 — tác giả đã rút bài (withdrawn) trên arXiv"])
    assert "1 nguồn" in ra and "NGUON_RUT" in ra
