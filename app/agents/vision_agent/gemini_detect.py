"""Hướng 4: đếm "mọi thứ" — YOLO cho 80 loại COCO, Gemini cho phần còn lại.

YOLO (yolo11n) chỉ biết 80 loại COCO: không đếm được "quả xoài", "chai Coca", hay
"người ĐỘI MŨ BẢO HIỂM" (biết người, không biết ai đội mũ). Gemini nhìn ảnh thì đếm
được vật bất kỳ mô tả bằng lời, nhưng tốn một lượt gọi (hạn mức miễn phí rất ít)
và không cho độ tin cậy.

Nên chia luồng theo CÂU HỎI, không tốn lượt nào để quyết định:
  - vật cần đếm nằm trọn trong 80 loại ("mấy con chó", "đếm số xe máy") -> YOLO
  - có từ nào ngoài tên loại COCO ("quả xoài", "người đội mũ", "con mèo màu đen",
    "chai Coca") -> Gemini
  - câu đếm chung chung ("đếm các vật thể") -> YOLO như cũ

File này chỉ chứa logic thuần + một lượt gọi model; tool `detect_and_count_objects`
(tools.py) và `vision_agent_tool` (supervisor/tools.py) gọi vào đây.
"""

from __future__ import annotations

import io
import json
import re
from typing import List, Optional, Tuple

from app.agents.vision_agent.labels import _RE_LOP, _RE_NHOM, lop_tu_cau_hoi
from app.agents.vision_agent.topics import khong_dau

# --------------------------------------------------------------------------- #
# 1. Câu hỏi -> "vật cần đếm"
# --------------------------------------------------------------------------- #
# Trên chuỗi KHÔNG DẤU. Bắt cụm đứng sau từ hỏi số lượng.
_TU_HOI_SO_LUONG = re.compile(
    r"\b(?:bao nhieu|may|dem so luong|dem so|dem|so luong|how many|count(?: the)?|number of)\s+"
)
_DAU_CUM = re.compile(
    r"(?:(?:lai|het|giup|ho|xem|thu|cho toi|cho minh|giup toi|giup minh|toi|minh|so luong|so|"
    r"tat ca|cac|nhung|xem co|xem la)\s+)*"
)
# Cắt cụm ở chỗ bắt đầu phần "ở đâu / trong ảnh". Chỉ dùng từ ít nghĩa khác: bỏ dấu
# thì "đỏ"/"đó" cùng thành "do", "lá"/"là" cùng thành "la" — không được cắt ở đó.
_DIEM_CAT = re.compile(
    r"[?.!,;:\n]|\b(?:trong|tren|o day|o trong|o anh|o buc|co trong|co mat|xuat hien|hien co|"
    r"are|is|there|in|on|at|this|that)\b"
)
# Từ đệm CUỐI câu ("... vậy bạn", "... không nhỉ"): chỉ bỏ khi đứng ở cuối cụm.
# So trên chuỗi CÓ dấu (chữ thường): "đó" là từ đệm, "đỏ" là màu; gõ không dấu thì chỉ bỏ
# các từ không thể nhầm.
_DEM_CUOI = re.compile(
    r"(?:\s+(?:vậy|thế|nhỉ|nhé|à|hả|không|chưa|bạn|ơi|giúp|với|này|kia|đó|đấy|đây|nào|"
    r"vay|nhi|nhe|khong|chua|oi|giup))+\s*$"
)
# Từ không mang nghĩa "loại vật": loại từ, lượng từ, liên từ.
_TU_PHU = {
    "con", "chu", "chiec", "cai", "qua", "trai", "bong", "to", "cuon", "quyen", "doi",
    "canh", "cac", "nhung", "moi", "tat", "ca", "va", "hoac", "voi", "so", "luong",
    "toan", "bo", "co", "the", "a", "an", "and", "or", "how", "many", "much", "bao", "nhieu",
}
# Câu đếm chung chung: không nêu vật cụ thể -> YOLO đếm tất cả như cũ.
_CHUNG_CHUNG = re.compile(
    r"^(?:(?:cac|nhung|tat ca|moi|toan bo)\s+)?(?:vat the|vat|do vat|doi tuong|thu|cai gi|gi|"
    r"objects?|things?|items?)?$"
)


def _bo_dau_giu_vi_tri(text: str) -> str:
    """Bỏ dấu nhưng giữ đúng số ký tự, để cắt lại được trên chuỗi CÓ dấu."""
    return "".join((khong_dau(ch)[:1] or ch) for ch in text)


def muc_tieu_dem(cau_hoi: str) -> Optional[str]:
    """Cụm vật cần đếm, giữ nguyên dấu: "Có mấy quả xoài?" -> "quả xoài".

    None nếu câu không hỏi số lượng hoặc chỉ hỏi chung chung ("đếm các vật thể").
    """
    goc = re.sub(r"https?://\S+|\S*[\\/]\S*|\bIMG\s?\d+\b", " ", cau_hoi or "", flags=re.I)
    goc = re.sub(r"\s+", " ", goc).strip()
    chuan = _bo_dau_giu_vi_tri(goc).lower()
    khop = _TU_HOI_SO_LUONG.search(chuan)
    if not khop:
        return None
    dau = khop.end()
    # "đếm LẠI số chó", "đếm GIÚP TÔI các con mèo": bỏ trạng từ / lời nhờ đứng đầu cụm.
    dau += _DAU_CUM.match(chuan, dau).end() - dau
    cat = _DIEM_CAT.search(chuan, dau)
    cuoi = cat.start() if cat else len(chuan)
    dem = _DEM_CUOI.search(goc.lower()[:cuoi], dau)
    if dem:
        cuoi = dem.start()
    cum = goc[dau:cuoi].strip(" -–\"'")
    cum_chuan = chuan[dau:cuoi].strip(" -–\"'")
    if not cum or _CHUNG_CHUNG.match(cum_chuan):
        return None
    if all(t in _TU_PHU for t in cum_chuan.split()):
        return None
    return cum


def phan_tu_ngoai_coco(cum: str) -> List[str]:
    """Các từ trong cụm KHÔNG thuộc tên loại COCO (sau khi bỏ loại từ, liên từ).

    "người đội mũ bảo hiểm" -> ["doi", "mu", "bao", "hiem"]; "xe máy" -> [].
    """
    # Thử thêm loại từ đứng trước: cụm đã bị tách khỏi câu nên "chó" đứng trơ trọi, mà
    # luật tên loại cần "con chó" (để không nhầm với "cho"); "táo" cần "quả táo".
    tot_nhat = None
    for dau in ("", "con ", "cai ", "qua "):
        chuan = khong_dau(dau + cum)
        for mau in list(_RE_LOP.values()) + [m for m, _ in _RE_NHOM]:
            chuan = mau.sub(" ", chuan)
        con_lai = [t for t in re.findall(r"[a-z0-9]+", chuan) if t not in _TU_PHU]
        if tot_nhat is None or len(con_lai) < len(tot_nhat):
            tot_nhat = con_lai
    return tot_nhat or []


def can_dung_gemini(cau_hoi: str) -> Optional[str]:
    """Trả "vật cần đếm" nếu câu hỏi phải nhờ Gemini; None nếu YOLO làm được.

    Không gọi model nào: chỉ đọc câu hỏi.
    """
    cum = muc_tieu_dem(cau_hoi)
    if not cum:
        return None
    return cum if phan_tu_ngoai_coco(cum) else None


# --------------------------------------------------------------------------- #
# 2. Một lượt Gemini: phát hiện + khung
# --------------------------------------------------------------------------- #
SO_KHUNG_TOI_DA = 60

GEMINI_DETECT_PROMPT = """Detect every visible instance of: "{muc_tieu}".
Return ONLY a JSON array, no other text. One item per instance:
{{"box_2d": [ymin, xmin, ymax, xmax], "label": "<short Vietnamese label>"}}
Coordinates are integers normalized to 0-1000 relative to the image.
- Count only instances that really match the description (e.g. if asked for people \
wearing helmets, do NOT include people without helmets).
- Partially visible instances count. Do not draw two boxes on the same instance.
- If there are none, return [].
- At most {toi_da} items."""


def _doc_mang_json(text: str) -> Optional[list]:
    """Mảng JSON đầu tiên trong câu trả lời (model hay bọc ```json ... ```)."""
    khop = re.search(r"\[.*\]", text or "", re.DOTALL)
    if not khop:
        return None
    try:
        gia_tri = json.loads(khop.group(0))
    except json.JSONDecodeError:
        return None
    return gia_tri if isinstance(gia_tri, list) else None


def doi_khung(ds: list, rong: int, cao: int) -> List[List[int]]:
    """box_2d [ymin,xmin,ymax,xmax] (0-1000) -> [x1,y1,x2,y2] pixel. Bỏ khung hỏng."""
    ra = []
    for muc in ds[:SO_KHUNG_TOI_DA]:
        box = muc.get("box_2d") if isinstance(muc, dict) else None
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            continue
        try:
            y1, x1, y2, x2 = (min(1000.0, max(0.0, float(v))) for v in box)
        except (TypeError, ValueError):
            continue
        if x2 <= x1 or y2 <= y1:
            continue
        ra.append([round(x1 / 1000 * rong), round(y1 / 1000 * cao), round(x2 / 1000 * rong), round(y2 / 1000 * cao)])
    return ra


def _kich_thuoc(image_ref: str) -> Tuple[int, int]:
    from app.agents.vision_agent.image_utils import mo_anh_dung_huong

    if image_ref.lower().startswith("http"):
        import requests

        r = requests.get(image_ref, timeout=15)
        r.raise_for_status()
        return mo_anh_dung_huong(io.BytesIO(r.content)).size
    return mo_anh_dung_huong(image_ref).size


def dem_bang_gemini(image_ref: str, muc_tieu: str, llm=None) -> dict:
    """MỘT lượt Gemini: đếm + khoanh `muc_tieu`. Trả payload cùng dạng YOLO:

        {"counting": {muc_tieu: n}, "detections": [{"class", "confidence": None, "bbox"}],
         "source": "gemini", "target": muc_tieu, ...}

    Lỗi (thiếu key, hết hạn mức, model trả rác) -> {"error": "..."}; không raise.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.agents.vision_agent.image_utils import encode_image
    from app.core.pretty import message_text

    b64, mime = encode_image(image_ref, get_mime_type=True)
    if not b64 or not mime:
        return {"error": f"Không đọc được ảnh {image_ref!r}."}
    try:
        rong, cao = _kich_thuoc(image_ref)
        model = llm
        if model is None:
            from app.core.llm import get_llm

            model = get_llm("vision")
        tra_loi = model.invoke(
            [
                SystemMessage(content=GEMINI_DETECT_PROMPT.format(muc_tieu=muc_tieu, toi_da=SO_KHUNG_TOI_DA)),
                HumanMessage(
                    content=[
                        {"type": "text", "text": f"Find: {muc_tieu}"},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ]
                ),
            ]
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Gemini lỗi: {exc}"}

    ds = _doc_mang_json(message_text(getattr(tra_loi, "content", tra_loi)))
    if ds is None:
        return {"error": "Gemini không trả về danh sách khung đọc được."}
    khung = doi_khung(ds, rong, cao)
    payload = {
        "counting": {muc_tieu: len(khung)} if khung else {},
        "detections": [{"class": muc_tieu, "confidence": None, "bbox": b} for b in khung],
        "source": "gemini",
        "target": muc_tieu,
        "labels_vi": {muc_tieu: muc_tieu},
        "note": (
            f"Counted by Gemini because '{muc_tieu}' is not one of the detector's 80 classes. "
            "Gemini gives no confidence scores and can miss or double-count in crowded scenes: "
            "say the count comes from Gemini."
            if khung
            else f"Gemini found no '{muc_tieu}' in the image: the answer is 0."
        ),
    }
    if len(ds) > SO_KHUNG_TOI_DA:
        payload["note"] += f" Only the first {SO_KHUNG_TOI_DA} instances were kept."
    return payload


def tra_loi_tu_payload(payload: dict) -> str:
    """Câu ngắn cho supervisor diễn đạt lại (đường tắt không qua agent ReAct)."""
    muc_tieu = payload.get("target", "vật")
    n = sum((payload.get("counting") or {}).values())
    if not n:
        return f"Gemini không tìm thấy {muc_tieu} nào trong ảnh (0)."
    return (
        f"Gemini đếm được {n} {muc_tieu} trong ảnh. Đây là vật ngoài 80 loại YOLO biết nên "
        "dùng Gemini; Gemini không cho độ tin cậy, ảnh đông có thể sót hoặc trùng."
    )
