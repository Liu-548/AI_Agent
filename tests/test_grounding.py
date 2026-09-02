"""Test bộ đối chiếu câu trả lời với kết quả tool.

Toàn bộ chạy offline, không gọi LLM, không tốn hạn mức — đây chính là lý do
phần kiểm tra được viết thành hàm thuần thay vì nhét vào prompt.
"""

from __future__ import annotations

from app.core.grounding import (
    bao_cao,
    kiem_tra_grounding,
    ma_arxiv_trong,
    ma_openalex_trong,
    tach_cau,
    tach_danh_sach_nguon,
)

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


# --------------------------------------------------------------------------- #
# Định dạng mới: tiếng Việt + trích dẫn số + danh sách NGUỒN cuối bài
# --------------------------------------------------------------------------- #
TRA_LOI_MOI = """TÓM TẮT
RoPE mã hoá vị trí bằng phép quay vector query và key [1].

CHI TIẾT
- Kết hợp vị trí tuyệt đối và tương đối trong cùng một cơ chế [1]
- Transformer đưa thông tin vị trí vào bằng positional encoding [2]

NGUỒN
[1] RoFormer: Enhanced Transformer with Rotary Position Embedding (2021)
    - http://arxiv.org/abs/2104.09864v5
[2] wikipedia: Transformer (deep learning)
"""


def test_dinh_dang_moi_khong_vi_pham():
    """Trích dẫn số + danh sách nguồn cuối bài phải được coi là hợp lệ.

    Đây là ca quan trọng nhất: đổi prompt sang định dạng số mà quên nâng cấp bộ
    kiểm tra thì nó báo động giả TOÀN BỘ, và người dùng sẽ tắt nó đi.
    """
    assert kiem_tra_grounding(TRA_LOI_MOI, [TOOL_ARXIV, TOOL_WIKI]) == []


def test_bat_duoc_trich_dan_khong_co_trong_muc_nguon():
    tra_loi = TRA_LOI_MOI.replace(
        "- Transformer đưa thông tin vị trí vào bằng positional encoding [2]",
        "- Transformer đưa thông tin vị trí vào bằng positional encoding [7]",
    )
    vi_pham = kiem_tra_grounding(tra_loi, [TOOL_ARXIV, TOOL_WIKI])
    assert any(v.startswith("NGUON_THIEU") and "[7]" in v for v in vi_pham)


def test_bat_duoc_ma_arxiv_bia_nam_trong_muc_nguon():
    """Mã bịa giờ nằm ở cuối bài chứ không còn cuối câu — vẫn phải bắt được."""
    tra_loi = TRA_LOI_MOI.replace("2104.09864v5", "2305.13052v1")
    vi_pham = kiem_tra_grounding(tra_loi, [TOOL_ARXIV, TOOL_WIKI])
    assert any(v.startswith("MA_BIA") and "2305.13052" in v for v in vi_pham)


def test_bat_duoc_trang_wikipedia_bia_trong_muc_nguon():
    tra_loi = TRA_LOI_MOI.replace(
        "[2] wikipedia: Transformer (deep learning)",
        "[2] wikipedia: Rotary position embedding",
    )
    vi_pham = kiem_tra_grounding(tra_loi, [TOOL_ARXIV, TOOL_WIKI])
    assert any(v.startswith("NGUON_BIA") and "[2]" in v for v in vi_pham)


def test_dong_thua_sau_muc_wikipedia_khong_lam_bao_dong_gia():
    """Lỗi thật đã gặp: model tự thêm dòng "- Page: X" thừa sau mục wikipedia
    (đặc tả chỉ có đúng 1 dòng). Dòng thừa bị nuốt chung vào nhãn làm
    NHAN_WIKI_RE bắt luôn phần rác, không khớp "Page:" thật -> báo NGUON_BIA giả.
    """
    tra_loi = TRA_LOI_MOI.replace(
        "[2] wikipedia: Transformer (deep learning)",
        "[2] wikipedia: Transformer (deep learning)\n    - Page: Transformer (deep learning)",
    )
    assert kiem_tra_grounding(tra_loi, [TOOL_ARXIV, TOOL_WIKI]) == []


def test_cau_tieng_viet_khong_gan_trich_dan_van_bi_bat():
    tra_loi = TRA_LOI_MOI.replace(
        "CHI TIẾT\n",
        "CHI TIẾT\n- RoPE hiện được dùng trong GPT-4 và nhiều mô hình ngôn ngữ lớn khác\n",
    )
    vi_pham = kiem_tra_grounding(tra_loi, [TOOL_ARXIV, TOOL_WIKI])
    assert any(v.startswith("THIEU_NGUON") and "GPT-4" in v for v in vi_pham)


def test_tieu_de_muc_khong_bi_coi_la_cau_thieu_nguon():
    """TÓM TẮT / CHI TIẾT / NGUỒN là tiêu đề mục, không phải câu khẳng định."""
    vi_pham = kiem_tra_grounding(TRA_LOI_MOI, [TOOL_ARXIV, TOOL_WIKI])
    assert not any("TÓM TẮT" in v or "CHI TIẾT" in v for v in vi_pham)


def test_tach_danh_sach_nguon():
    than, nguon = tach_danh_sach_nguon(TRA_LOI_MOI)
    assert "NGUỒN" not in than
    assert set(nguon) == {"1", "2"}
    # Dòng URL bị thụt lề phải được dán vào mục [1] phía trên, không thành mục riêng.
    assert "arxiv.org/abs/2104.09864v5" in nguon["1"]
    assert nguon["2"] == "wikipedia: Transformer (deep learning)"


def test_khong_co_muc_nguon_thi_giu_nguyen_dinh_dang_cu():
    than, nguon = tach_danh_sach_nguon("Mot cau [http://arxiv.org/abs/2104.09864v5].")
    assert nguon == {}
    assert than.startswith("Mot cau")


# --------------------------------------------------------------------------- #
# Nguồn OpenAlex — đi theo đúng khuôn arXiv (mục NGUỒN mang OpenAlex ID)
# --------------------------------------------------------------------------- #
TOOL_OPENALEX = """OpenAlex ID: https://openalex.org/W2741809807
DOI: https://doi.org/10.7717/peerj.4375
Published: 2018
Title: The state of OA: a large-scale analysis
Authors: Heather Piwowar, Jason Priem
Cited by: 1234
Summary: We estimate the number of articles that are freely available online."""

TRA_LOI_OPENALEX = """TÓM TẮT
Phần lớn bài báo học thuật hiện đã có bản truy cập mở [1].

CHI TIẾT
- Nghiên cứu này ước tính tỉ lệ bài báo truy cập mở trên diện rộng [1]

NGUỒN
[1] The state of OA: a large-scale analysis (2018)
    - https://openalex.org/W2741809807
"""


def test_ma_openalex_nhan_dung():
    assert ma_openalex_trong("xem https://openalex.org/W2741809807") == ["W2741809807"]


def test_nguon_openalex_hop_le_khong_vi_pham():
    assert kiem_tra_grounding(TRA_LOI_OPENALEX, [TOOL_OPENALEX]) == []


def test_bat_duoc_ma_openalex_bia():
    tra_loi = TRA_LOI_OPENALEX.replace("W2741809807", "W9999999999")
    vi_pham = kiem_tra_grounding(tra_loi, [TOOL_OPENALEX])
    assert any(v.startswith("MA_BIA") and "W9999999999" in v for v in vi_pham)
