"""Kiểm tra một câu trả lời có bám vào kết quả tool hay không (grounding).

Vì sao cần: model trả lời rất trôi chảy bằng trí nhớ của nó. Trong một lần chạy
thử, Research Agent viết "RoPE được dùng trong GPT-4, LLaMA-2" — LLaMA thì đúng,
còn GPT-4 thì OpenAI chưa từng công bố kiến trúc, và KHÔNG kết quả tool nào nhắc
tới cả hai. Với một agent tìm tài liệu khoa học thì đây là lỗi nặng: câu văn đúng
ngữ pháp, nghe hợp lý, và không ai soi ra khi chấm.

Cách chặn gồm hai nửa, cố tình tách rời:
- Nửa mềm (prompt): bắt model gắn TRÍCH DẪN vào cuối mỗi câu.
- Nửa cứng (file này): đối chiếu trích dẫn với văn bản tool đã trả về. Thuần
  Python, không gọi LLM, nên chạy được offline và không tốn hạn mức.

HAI ĐỊNH DẠNG TRÍCH DẪN đều được chấp nhận:

1. Dạng số (định dạng hiện tại của Research Agent) — thân bài chỉ mang số, danh
   sách nguồn đầy đủ dồn xuống cuối. Ngắn và dễ đọc:

       CHI TIẾT
       - Kết hợp vị trí tuyệt đối và tương đối trong một cơ chế [1]

       NGUỒN
       [1] RoFormer... (2021) - http://arxiv.org/abs/2104.09864v5

2. Dạng nhãn đầy đủ cuối mỗi câu (định dạng cũ), giữ lại để không làm đỏ những
   câu trả lời sinh ra trước khi đổi prompt:

       RoPE mã hoá vị trí bằng phép quay [http://arxiv.org/abs/2104.09864v5].

Nguồn OpenAlex (thêm sau, xem MA_OPENALEX_RE) đi theo ĐÚNG khuôn của arXiv:
mục NGUỒN chứa một "OpenAlex ID: https://openalex.org/W..." copy nguyên văn từ
tool, được nhận diện y hệt cách nhận diện Entry ID của arXiv.

Module này chỉ TỐ CÁO, không sửa câu trả lời. Sửa hộ model là che mất lỗi.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Pattern, Set, Tuple

# Nhãn nguồn dạng đầy đủ trong ngoặc vuông: [http://arxiv.org/abs/...] hoặc
# [wikipedia: Tên trang]. Tối thiểu 3 ký tự nên KHÔNG nuốt nhầm số trích dẫn [1].
NHAN_RE = re.compile(r"\[([^\[\]\n]{3,300})\]")

# Mọi thứ trong ngoặc vuông, KỂ CẢ [1]. Chỉ dùng để trả lời câu hỏi "câu này có
# gắn trích dẫn nào không", không quan tâm trích dẫn thuộc loại nào.
BAT_KY_NHAN_RE = re.compile(r"\[[^\[\]\n]{1,300}\]")

# Số trích dẫn trong thân bài: [1], [12]. Giới hạn 3 chữ số để không bắt nhầm
# một năm đặt trong ngoặc vuông ([2021]).
SO_TRICH_RE = re.compile(r"\[(\d{1,3})\]")

# Dòng tiêu đề mở đầu danh sách nguồn cuối bài.
TIEU_DE_NGUON_RE = re.compile(
    r"^\s*(?:\*\*)?\s*(?:NGUỒN(?:\s+THAM\s+KHẢO)?|NGUON|SOURCES?|REFERENCES?)"
    r"\s*(?:\*\*)?\s*:?\s*$",
    re.IGNORECASE,
)

# Một mục trong danh sách nguồn: "[1] RoFormer ... - http://arxiv.org/abs/..."
MUC_NGUON_RE = re.compile(r"^\s*\[(\d{1,3})\]\s*(.*)$")

# Mã bài báo arXiv dưới mọi dạng model hay viết.
MA_ARXIV_RE = re.compile(r"(?:arxiv\.org/abs/|arxiv:\s*)(\d{4}\.\d{4,5})", re.IGNORECASE)

# Mã Work ID của OpenAlex, dạng "https://openalex.org/W2741809807".
MA_OPENALEX_RE = re.compile(r"openalex\.org/(W\d+)", re.IGNORECASE)

# Dòng "Page: ..." trong kết quả wikipedia_search — nguồn hợp lệ duy nhất cho nhãn wikipedia.
TRANG_WIKI_RE = re.compile(r"^Page:\s*(.+)$", re.MULTILINE)

# Nhãn wikipedia, ở cả hai định dạng: "[wikipedia: X]" và mục "[2] wikipedia: X".
NHAN_WIKI_RE = re.compile(r"wikipedia\s*:\s*(.+)$", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# BẢNG LOẠI NHÃN — thêm một loại nguồn mới = thêm MỘT mục vào LOAI_NHAN_MOI
# --------------------------------------------------------------------------- #
# arXiv, OpenAlex-dạng-URL và Wikipedia vẫn dùng regex riêng ở trên (giữ nguyên
# hành vi cũ). Các loại nhãn thêm sau (DOI, PMID, OpenAlex dạng ngắn, Semantic
# Scholar) đi theo bảng này:
#   nhan_re : nhận diện NHÃN / mục NGUỒN, group(1) = mã. Ví dụ "[doi: 10.1/abc]".
#   trong_re: bắt mã TRẦN trong văn bản (cả bằng chứng lẫn câu trả lời).
#   chuan   : chuẩn hoá mã trước khi so, để "10.1/ABC." khớp "10.1/abc".
#   ma_tran : True = mã trần xuất hiện ở bất kỳ đâu trong câu trả lời cũng phải có
#             trong bằng chứng (MA_BIA). False = chỉ kiểm khi nằm trong nhãn.
@dataclass(frozen=True)
class LoaiNhan:
    ten: str
    nhan_re: Pattern
    trong_re: Pattern
    chuan: Callable[[str], str]
    ma_tran: bool = True


def _chuan_doi(ma: str) -> str:
    """Chữ thường, bỏ tiền tố https://doi.org/ và dấu câu dính ở cuối."""
    ma = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", ma.strip(), flags=re.IGNORECASE)
    return ma.lower().rstrip(".,;:!?'\"")


LOAI_NHAN_MOI: Tuple[LoaiNhan, ...] = (
    LoaiNhan(
        "DOI",
        re.compile(r"\bdoi\s*:\s*(\S+)", re.IGNORECASE),
        re.compile(r"(10\.\d{4,9}/[^\s\]\)]+)"),
        _chuan_doi,
    ),
    # PMID chỉ tính khi đứng sau chữ PMID/pmid — không bắt số trần ngẫu nhiên.
    LoaiNhan(
        "PMID",
        re.compile(r"\bpmid\s*:\s*(\d+)", re.IGNORECASE),
        re.compile(r"\bpmid\s*:?\s*(\d{1,9})", re.IGNORECASE),
        lambda ma: ma.strip(),
    ),
    LoaiNhan(
        "OpenAlex",
        re.compile(r"\bopenalex\s*:\s*(W\d+)", re.IGNORECASE),
        re.compile(r"\b(W\d{6,})\b"),
        lambda ma: ma.strip().upper(),
    ),
    LoaiNhan(
        "S2",
        re.compile(r"\bs2\s*:\s*([0-9a-fA-F]{40})\b", re.IGNORECASE),
        re.compile(r"\bs2\s*:\s*([0-9a-fA-F]{40})\b", re.IGNORECASE),
        lambda ma: ma.strip().lower(),
        ma_tran=False,
    ),
)


def ma_moi_trong(text: str, loai: LoaiNhan) -> List[str]:
    """Mọi mã của một loại nhãn mới trong đoạn văn bản, đã chuẩn hoá, không trùng."""
    return list(dict.fromkeys(loai.chuan(m.group(1)) for m in loai.trong_re.finditer(text or "")))


def _ma_that_theo_loai(bang_chung: str) -> Dict[str, Set[str]]:
    """{tên loại: các mã có thật trong bằng chứng}."""
    return {loai.ten: set(ma_moi_trong(bang_chung, loai)) for loai in LOAI_NHAN_MOI}


# Câu ngắn hơn ngần này coi như tiêu đề/gạch đầu dòng cấu trúc, không bắt gắn nhãn.
SO_TU_TOI_THIEU = 6

DAU_HIEU_TU_CHOI = ("KHONG DU DU LIEU", "KHÔNG ĐỦ DỮ LIỆU")


def _chuan_hoa(s: str) -> str:
    return " ".join((s or "").lower().split())


def _chuan_so(s: str) -> str:
    """'01' và '1' là cùng một nguồn."""
    return s.lstrip("0") or "0"


def _bo_nhan(cau: str) -> str:
    """Bỏ MỌI trích dẫn khỏi câu — kể cả [1] — để đếm số từ thật."""
    return BAT_KY_NHAN_RE.sub(" ", cau)


def tach_danh_sach_nguon(answer: str) -> Tuple[str, Dict[str, str]]:
    """Cắt câu trả lời thành (thân bài, {số: nội dung nguồn}).

    Danh sách nguồn là phần đứng sau dòng tiêu đề NGUỒN CUỐI CÙNG — lấy dòng cuối
    chứ không phải dòng đầu, phòng khi model nhắc chữ "nguồn" ở đâu đó phía trên.

    Không có mục NGUỒN thì trả về nguyên câu trả lời và một map rỗng: định dạng
    nhãn đầy đủ kiểu cũ vẫn chạy qua đường này mà không vi phạm gì.
    """
    dong = (answer or "").splitlines()
    vi_tri: Optional[int] = None
    for i, d in enumerate(dong):
        if TIEU_DE_NGUON_RE.match(d):
            vi_tri = i
    if vi_tri is None:
        return answer or "", {}

    than = "\n".join(dong[:vi_tri])
    nguon: Dict[str, str] = {}
    so_hien_tai: Optional[str] = None
    for d in dong[vi_tri + 1 :]:
        khop = MUC_NGUON_RE.match(d)
        if khop:
            so_hien_tai = _chuan_so(khop.group(1))
            nguon[so_hien_tai] = khop.group(2).strip()
        elif so_hien_tai is not None and d.strip():
            if "wikipedia:" in nguon[so_hien_tai].lower():
                # Mục wikipedia CHỈ có một dòng theo đặc tả prompt (khác arXiv/
                # OpenAlex có dòng URL xuống hàng riêng). Model thỉnh thoảng vẫn
                # thừa thêm một dòng kiểu "- Page: X" -- nuốt dòng đó vào nhãn sẽ
                # làm NHAN_WIKI_RE bắt luôn phần rác, so khớp sai với "Page:" thật
                # trong kết quả tool và báo NGUON_BIA giả. Bỏ qua, không nuốt.
                continue
            # Dòng xuống hàng của mục phía trên (model hay thụt lề phần URL).
            nguon[so_hien_tai] = (nguon[so_hien_tai] + " " + d.strip()).strip()
    return than, nguon


def tach_cau(answer: str) -> List[str]:
    """Tách câu trả lời thành từng câu. Cắt theo xuống dòng rồi tới dấu kết câu."""
    cau = []
    for dong in (answer or "").splitlines():
        dong = dong.strip()
        if not dong:
            continue
        # Bỏ ký hiệu markdown đầu dòng để đếm từ cho đúng.
        dong = re.sub(r"^\s*(?:[-*+]|\d+[.)]|#{1,6}|\|)\s*", "", dong)
        for phan in re.split(r"(?<=[.!?])\s+", dong):
            phan = phan.strip()
            if not phan:
                continue
            # Trích dẫn đứng SAU dấu chấm nên bị regex trên tách thành một "câu"
            # riêng, làm câu thật phía trước trông như không có nguồn. Dán nó trả
            # về câu trước. Đây là lỗi đã làm bộ kiểm tra báo sai toàn bộ 4 câu
            # trong một lần chạy thử, dù model gắn nhãn hoàn toàn đúng.
            if cau and not _bo_nhan(phan).strip():
                cau[-1] = cau[-1] + " " + phan
                continue
            cau.append(phan)
    return cau


def ma_arxiv_trong(text: str) -> List[str]:
    """Mọi mã arXiv xuất hiện trong một đoạn văn bản, đã bỏ hậu tố phiên bản."""
    return [m.group(1) for m in MA_ARXIV_RE.finditer(text or "")]


def ma_openalex_trong(text: str) -> List[str]:
    """Mọi mã Work ID của OpenAlex (dạng W123456789) xuất hiện trong một đoạn văn bản."""
    return [m.group(1) for m in MA_OPENALEX_RE.finditer(text or "")]


def _soi_nguon(
    noi_dung: str,
    kho_chuan: str,
    trang_wiki: Set[str],
    ma_that: Optional[Dict[str, Set[str]]] = None,
) -> Optional[str]:
    """Một chuỗi nguồn có truy được về kết quả tool không?

    None = hợp lệ. Chuỗi = mô tả vi phạm (chưa gắn tiền tố mã lỗi).

    Mục có mã arXiv được trả về None ở đây vì vòng MA_BIA đã soi toàn bộ câu trả
    lời rồi — tố cáo hai lần cho cùng một mã sai chỉ làm báo cáo dài thêm.
    """
    noi_dung = (noi_dung or "").strip()
    if not noi_dung:
        return "mục nguồn để trống"
    if ma_arxiv_trong(noi_dung):
        return None
    if ma_openalex_trong(noi_dung):
        return None
    ma_that = ma_that or {}
    for loai in LOAI_NHAN_MOI:
        khop = loai.nhan_re.search(noi_dung)
        if khop:
            ma = loai.chuan(khop.group(1))
            if ma in ma_that.get(loai.ten, set()):
                return None
            return f"{loai.ten} {ma} không có trong bất kỳ kết quả tool nào"
    # Mã trần không kèm tiền tố (vd. URL doi.org) đã được vòng MA_BIA soi rồi.
    if any(loai.ma_tran and loai.trong_re.search(noi_dung) for loai in LOAI_NHAN_MOI):
        return None
    khop_wiki = NHAN_WIKI_RE.search(noi_dung)
    if khop_wiki:
        # Nhãn wikipedia phải trỏ tới đúng một dòng "Page:" tool đã trả về.
        # Không đối chiếu kiểu "có xuất hiện đâu đó" được: tên trang bịa vẫn có
        # thể trùng một cụm trong tiêu đề bài báo.
        ten_trang = _chuan_hoa(khop_wiki.group(1))
        if not any(ten_trang == t or ten_trang in t for t in trang_wiki):
            return f"không có trang Wikipedia {khop_wiki.group(1).strip()!r} trong kết quả tool"
        return None
    if _chuan_hoa(noi_dung) not in kho_chuan:
        return f"nguồn {noi_dung!r} không xuất hiện trong kết quả tool"
    return None


def kiem_tra_grounding(answer: str, tool_texts: Iterable[str]) -> List[str]:
    """Trả về danh sách vi phạm. Rỗng = mọi khẳng định đều truy được về kết quả tool.

    Năm loại vi phạm, xếp theo mức nguy hiểm giảm dần:
      1. MA_BIA      — mã arXiv không có trong bất kỳ kết quả tool nào.
      2. NGUON_BIA   — một mục trong danh sách NGUỒN trỏ tới thứ tool chưa trả về.
      3. NHAN_BIA    — nhãn đầy đủ viết thẳng trong thân bài, trỏ tới nguồn lạ.
      4. NGUON_THIEU — thân bài trích dẫn [n] mà mục NGUỒN không có dòng [n].
      5. THIEU_NGUON — câu khẳng định không gắn trích dẫn nào.
    """
    kho = "\n".join(t or "" for t in tool_texts)
    kho_chuan = _chuan_hoa(kho)
    ma_that = set(ma_arxiv_trong(kho))
    ma_moi_that = _ma_that_theo_loai(kho)
    # Nhãn OpenAlex có hai dạng (URL và "openalex: W..."), bằng chứng có thể chỉ có một.
    ma_openalex_that = set(ma_openalex_trong(kho)) | ma_moi_that["OpenAlex"]
    trang_wiki = {_chuan_hoa(t) for t in TRANG_WIKI_RE.findall(kho)}

    vi_pham: List[str] = []

    if any(d in (answer or "") for d in DAU_HIEU_TU_CHOI):
        return vi_pham  # model đã tự khai là không đủ dữ liệu, không bắt lỗi thêm

    than, nguon = tach_danh_sach_nguon(answer)

    # 1. Mã arXiv / OpenAlex bịa — soi TOÀN BỘ câu trả lời, kể cả phần danh sách nguồn.
    for ma in dict.fromkeys(ma_arxiv_trong(answer)):
        if ma not in ma_that:
            vi_pham.append(f"MA_BIA: arXiv {ma} không có trong bất kỳ kết quả tool nào")
    for ma in dict.fromkeys(ma_openalex_trong(answer)):
        if ma not in ma_openalex_that:
            vi_pham.append(f"MA_BIA: OpenAlex {ma} không có trong bất kỳ kết quả tool nào")
    # Các loại mã trần thêm sau (DOI, PMID, OpenAlex dạng ngắn...).
    for loai in LOAI_NHAN_MOI:
        if not loai.ma_tran:
            continue
        for ma in ma_moi_trong(answer, loai):
            loi = f"MA_BIA: {loai.ten} {ma} không có trong bất kỳ kết quả tool nào"
            if ma not in ma_moi_that[loai.ten] and loi not in vi_pham:
                vi_pham.append(loi)

    # 2. Mỗi mục trong NGUỒN phải trỏ tới thứ tool thật sự đã trả về.
    for so in sorted(nguon, key=lambda x: int(x)):
        loi = _soi_nguon(nguon[so], kho_chuan, trang_wiki, ma_moi_that)
        if loi:
            vi_pham.append(f"NGUON_BIA: [{so}] {loi}")

    # 3. Nhãn đầy đủ viết thẳng trong thân bài (định dạng cũ).
    for nhan in dict.fromkeys(m.group(1).strip() for m in NHAN_RE.finditer(than)):
        if nhan.isdigit():
            continue  # số trích dẫn, đã xét ở bước 4
        loi = _soi_nguon(nhan, kho_chuan, trang_wiki, ma_moi_that)
        if loi:
            vi_pham.append(f"NHAN_BIA: {loi}")

    # 4. Số trích dẫn trong thân bài phải có dòng tương ứng trong NGUỒN.
    for so in dict.fromkeys(_chuan_so(m.group(1)) for m in SO_TRICH_RE.finditer(than)):
        if so not in nguon:
            vi_pham.append(
                f"NGUON_THIEU: trích dẫn [{so}] không có dòng nào tương ứng trong mục NGUỒN"
            )

    # 5. Câu khẳng định không gắn trích dẫn nào.
    for cau in tach_cau(than):
        if BAT_KY_NHAN_RE.search(cau):
            continue
        if len(_bo_nhan(cau).split()) < SO_TU_TOI_THIEU:
            continue
        vi_pham.append(f"THIEU_NGUON: {cau[:110]}")

    return vi_pham


def bao_cao(vi_pham: List[str]) -> str:
    """Khối văn bản in ra sau câu trả lời."""
    if not vi_pham:
        return "=== KIEM TRA NGUON ===\nOK — mọi khẳng định đều truy được về kết quả tool."
    dong = ["=== KIEM TRA NGUON ===", f"{len(vi_pham)} chỗ chưa có nguồn kiểm chứng được:"]
    dong += [f"  - {v}" for v in vi_pham]
    dong.append("")
    if any(v.startswith("MA_BIA") for v in vi_pham):
        dong.append("MA_BIA là lỗi nặng nhất: mã đó không tồn tại trong dữ liệu đã tra.")
    if any(v.startswith("NGUON_BIA") for v in vi_pham):
        dong.append("NGUON_BIA: một dòng trong mục NGUỒN trỏ tới thứ không tool nào trả về.")
    if any(v.startswith("NGUON_THIEU") for v in vi_pham):
        dong.append("NGUON_THIEU: thân bài trích dẫn một số không có dòng nào trong mục NGUỒN.")
    if any(v.startswith("THIEU_NGUON") for v in vi_pham):
        dong.append("THIEU_NGUON: câu không gắn nhãn nguồn nào. Trích dẫn phải nằm CUỐI câu, dạng")
        dong.append("  [1] (kèm dòng [1] trong mục NGUỒN) hoặc [http://arxiv.org/abs/...].")
    dong.append("Lưu ý: bộ này chỉ kiểm tra nguồn CÓ TỒN TẠI trong kết quả tool,")
    dong.append("không kiểm tra được nguồn đó có thật sự nói điều đang trích hay không.")
    return "\n".join(dong)
