"""Test nhãn nguồn mới (DOI, PMID, OpenAlex dạng ngắn, Semantic Scholar) trong core/grounding.py.

Chạy offline. Các test hồi quy ở cuối khẳng định hành vi cũ (arXiv, Wikipedia,
nhãn đứng sau dấu chấm) không đổi.
"""

from __future__ import annotations

import pytest

from app.core.grounding import kiem_tra_grounding, ma_moi_trong, tach_cau, LOAI_NHAN_MOI

S2_ID = "a" * 40

# Đúng định dạng paper_search trả về (xem SPEC §5.5).
BANG_CHUNG = f"""[1] Title: Attention Is All You Need
    Label: [http://arxiv.org/abs/1706.03762v7]
    Other IDs: doi:10.5555/3295222.3295349 | pmid:12345678 | openalex:W2963403868 | s2:{S2_ID}
    Published: 2017-06-12
"""


def _codes(vi_pham):
    return [v.split(":")[0] for v in vi_pham]


@pytest.mark.parametrize(
    "nhan",
    [
        "[doi: 10.5555/3295222.3295349]",
        "[doi: 10.5555/3295222.3295349].",
        "[doi: https://doi.org/10.5555/3295222.3295349]",
        "[doi: 10.5555/3295222.3295349]",
        "[pmid: 12345678]",
        "[openalex: W2963403868]",
        "[openalex: w2963403868]",
        f"[s2: {S2_ID}]",
        f"[s2: {S2_ID.upper()}]",
    ],
)
def test_nhan_hop_le_khong_vi_pham(nhan):
    cau = f"The Transformer architecture relies only on attention mechanisms {nhan}"
    assert kiem_tra_grounding(cau, [BANG_CHUNG]) == []


def test_doi_khac_hoa_thuong_va_dau_cham_cuoi_cau_van_khop():
    cau = "The paper is indexed under DOI 10.5555/3295222.3295349."
    vi_pham = kiem_tra_grounding(cau, [BANG_CHUNG.upper().replace("DOI:", "doi:")])
    assert not any(v.startswith(("MA_BIA", "NHAN_BIA")) for v in vi_pham), vi_pham
    cau = "It is at [doi: 10.5555/3295222.3295349]."
    assert kiem_tra_grounding(cau, [BANG_CHUNG]) == []


@pytest.mark.parametrize(
    "nhan",
    ["[doi: 10.9999/bia.dat]", "[pmid: 99999999]", "[openalex: W1111111111]", f"[s2: {'b' * 40}]"],
)
def test_nhan_bia_bi_bat(nhan):
    cau = f"The Transformer architecture relies only on attention mechanisms {nhan}"
    vi_pham = kiem_tra_grounding(cau, [BANG_CHUNG])
    assert "NHAN_BIA" in _codes(vi_pham), vi_pham


def test_ma_tran_bia_bi_bat_ngoai_nhan():
    doi = kiem_tra_grounding("See doi 10.9999/bia.dat for details on this method.", [BANG_CHUNG])
    assert "MA_BIA" in _codes(doi)
    pmid = kiem_tra_grounding("This is described in PMID 99999999 by the authors.", [BANG_CHUNG])
    assert "MA_BIA" in _codes(pmid)
    oa = kiem_tra_grounding("The work W1111111111 describes this in a lot of detail.", [BANG_CHUNG])
    assert "MA_BIA" in _codes(oa)


def test_pmid_khong_bat_nham_so_tran():
    cau = "The model has 99999999 parameters and was trained on 12345 examples [1]."
    assert not any(v.startswith("MA_BIA") for v in kiem_tra_grounding(cau, [BANG_CHUNG]))


def test_ma_openalex_dang_url_khop_bang_chung_dang_ngan():
    cau = "Attention alone suffices for translation [https://openalex.org/W2963403868]."
    assert kiem_tra_grounding(cau, [BANG_CHUNG]) == []


def test_muc_nguon_dung_va_bia():
    dung = "TÓM TẮT\nTransformer chỉ dùng attention để dịch máy [1].\n\nNGUỒN\n[1] doi: 10.5555/3295222.3295349\n"
    assert kiem_tra_grounding(dung, [BANG_CHUNG]) == []
    bia = dung.replace("10.5555/3295222.3295349", "10.9999/bia.dat")
    assert {"MA_BIA", "NGUON_BIA"} <= set(_codes(kiem_tra_grounding(bia, [BANG_CHUNG])))


def test_bang_dang_ky_du_bon_loai():
    assert [l.ten for l in LOAI_NHAN_MOI] == ["DOI", "PMID", "OpenAlex", "S2"]
    assert ma_moi_trong("10.1234/AbC.", LOAI_NHAN_MOI[0]) == ["10.1234/abc"]


# --- hồi quy: hành vi cũ không đổi ---
def test_nhan_sau_dau_cham_khong_bi_tach_thanh_cau_rieng():
    cau = tach_cau("RoPE encodes position with rotations. [doi: 10.5555/3295222.3295349]")
    assert len(cau) == 1


def test_arxiv_va_wikipedia_van_nhu_cu():
    wiki = "Page: Transformer (deep learning)\nSummary: text"
    ok = (
        "RoPE encodes position with a rotation matrix [http://arxiv.org/abs/1706.03762v7].\n"
        "Transformers inject positional information through encodings [wikipedia: Transformer (deep learning)]."
    )
    assert kiem_tra_grounding(ok, [BANG_CHUNG, wiki]) == []
    bia = "RoPE encodes position with a rotation matrix [http://arxiv.org/abs/2305.13052v1]."
    assert "MA_BIA" in _codes(kiem_tra_grounding(bia, [BANG_CHUNG]))
