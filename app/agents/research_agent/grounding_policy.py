"""Chính sách xử lý khi grounding phát hiện câu có nguồn bịa.

app/core/grounding.py chỉ TỐ CÁO (trả danh sách vi phạm), không sửa câu trả lời.
Với chế độ "topics" thì cần một bước nữa: bỏ những câu chắc chắn sai, để chúng
không đi tiếp lên lead / supervisor / người dùng. Bước đó nằm ở đây.

Quy tắc (quyết định D4 trong SPEC):
- MA_BIA / NHAN_BIA -> XOÁ câu. Bịa mã hay bịa nhãn là lỗi nặng và được so khớp
  chính xác nên gần như không báo động giả.
- THIEU_NGUON       -> chỉ ĐẾM, giữ câu. Loại này dễ báo động giả, xoá nhầm câu
  đúng còn hại hơn.
- Câu trích dẫn số [n] mà mục [n] trong NGUỒN là nguồn bịa -> xoá luôn câu đó, và
  bỏ dòng nguồn bịa khỏi danh sách NGUỒN.

Cách làm: chấm TỪNG câu một bằng chính kiem_tra_grounding() của core, nên không
có logic đối chiếu nào bị viết lại ở đây.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from app.core.grounding import (
    BAT_KY_NHAN_RE,
    SO_TRICH_RE,
    SO_TU_TOI_THIEU,
    TIEU_DE_NGUON_RE,
    MUC_NGUON_RE,
    kiem_tra_grounding,
    tach_cau,
    tach_danh_sach_nguon,
)

# Hai dòng đặc biệt mà agent được phép trả về: đi qua nguyên vẹn, không chấm.
DONG_DAC_BIET = ("KHONG DU DU LIEU:", "CAN_LAM_RO:")
THONG_BAO_HET_CAU = "KHONG DU DU LIEU: sources could not support a cited answer"

# Loại vi phạm nặng -> xoá câu.
MA_NANG = ("MA_BIA", "NHAN_BIA")

_DAU_DONG_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)]|#{1,6})\s+")


def _ma_loi(vi_pham: str) -> str:
    return vi_pham.split(":", 1)[0]


def _nguon_bia(nguon: Dict[str, str], bang_chung: str) -> Dict[str, str]:
    """{số: lý do} của các mục NGUỒN trỏ tới thứ tool chưa hề trả về."""
    bia: Dict[str, str] = {}
    for so, noi_dung in nguon.items():
        loi = [v for v in kiem_tra_grounding(f"NGUỒN\n[{so}] {noi_dung}", [bang_chung])
               if _ma_loi(v) in ("MA_BIA", "NGUON_BIA")]
        if loi:
            bia[so] = loi[0]
    return bia


def apply_grounding_policy(answer: str, evidence: str) -> Tuple[str, dict]:
    """Trả (câu_trả_lời_đã_làm_sạch, report).

    report = {"removed": int, "missing_source": int,
              "violations": [{"code", "sentence", "detail"}]}
    Không có gì bị xoá thì trả lại đúng nguyên chuỗi đầu vào.
    """
    report = {"removed": 0, "missing_source": 0, "violations": []}
    if not (answer or "").strip() or (answer or "").strip().startswith(DONG_DAC_BIET):
        return answer, report

    dong = answer.splitlines()
    vi_tri_nguon = None
    for i, d in enumerate(dong):
        if TIEU_DE_NGUON_RE.match(d):
            vi_tri_nguon = i  # lấy dòng CUỐI, giống tach_danh_sach_nguon()
    than_dong = dong if vi_tri_nguon is None else dong[:vi_tri_nguon]
    nguon_dong = [] if vi_tri_nguon is None else dong[vi_tri_nguon:]

    _, nguon = tach_danh_sach_nguon(answer)
    bia = _nguon_bia(nguon, evidence)

    moi: List[str] = []
    con_cau_co_noi_dung = False
    for d in than_dong:
        khop = _DAU_DONG_RE.match(d)
        tien_to = khop.group(0) if khop else ""
        cac_cau = tach_cau(d[len(tien_to):])
        if not cac_cau:
            moi.append(d)  # dòng trống
            continue
        giu: List[str] = []
        for cau in cac_cau:
            vi_pham = kiem_tra_grounding(cau, [evidence])
            ma = {_ma_loi(v) for v in vi_pham}
            so_dan = {s.lstrip("0") or "0" for s in SO_TRICH_RE.findall(cau)}
            nguon_hong = sorted(so_dan & set(bia))
            if ma & set(MA_NANG) or nguon_hong:
                chi_tiet = next((v for v in vi_pham if _ma_loi(v) in MA_NANG), None)
                report["removed"] += 1
                report["violations"].append({
                    "code": _ma_loi(chi_tiet) if chi_tiet else "NGUON_BIA",
                    "sentence": cau,
                    "detail": chi_tiet or bia[nguon_hong[0]],
                })
                continue
            if "THIEU_NGUON" in ma:
                report["missing_source"] += 1
            giu.append(cau)
            if len(BAT_KY_NHAN_RE.sub(" ", cau).split()) >= SO_TU_TOI_THIEU:
                con_cau_co_noi_dung = True
        if giu:
            moi.append(tien_to + " ".join(giu))

    # Danh sách NGUỒN: bỏ mục bịa (kèm các dòng xuống hàng của nó), giữ phần còn lại.
    nguon_moi: List[str] = nguon_dong[:1]
    dang_bo = False
    for d in nguon_dong[1:]:
        khop = MUC_NGUON_RE.match(d)
        if khop:
            dang_bo = (khop.group(1).lstrip("0") or "0") in bia
        if not dang_bo:
            nguon_moi.append(d)
    for so, ly_do in bia.items():
        report["violations"].append(
            {"code": "NGUON_BIA", "sentence": f"[{so}] {nguon[so]}", "detail": ly_do}
        )

    if report["removed"] == 0 and not bia:
        return answer, report
    if report["removed"] and not con_cau_co_noi_dung:
        return THONG_BAO_HET_CAU, report
    return "\n".join(moi + nguon_moi), report
