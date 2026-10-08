"""Chủ đề ảnh của Vision Agent: mỗi chủ đề là MỘT lời dặn riêng cho model nhìn ảnh.

Vì sao chỉ là lời dặn mà không phải agent riêng: mỗi agent ReAct tốn thêm vài lượt
gọi model, trong khi hạn mức Gemini miễn phí rất ít. Lời dặn thì không tốn lượt nào:
nó được ghép vào system prompt của chính lượt "nhìn ảnh" đang có sẵn
(`describe_image` trong tools.py).

Thêm chủ đề mới = thêm MỘT mục vào `CHU_DE` bên dưới (kèm test). Không sửa chỗ khác.

File này chỉ dùng thư viện chuẩn để import ở đâu cũng nhẹ (CT-03: không có logic agent).
"""

from __future__ import annotations

import re
import unicodedata
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator, Optional, Tuple

CHU_DE_CHUNG = "general"


@dataclass(frozen=True)
class ChuDe:
    id: str
    ten: str  # tên hiển thị tiếng Việt
    loi_dan: str  # ghép vào system prompt của lượt nhìn ảnh; rỗng = không thêm gì
    # Cụm từ trong CÂU HỎI báo hiệu chủ đề này, viết KHÔNG DẤU, chữ thường.
    tu_khoa: Tuple[str, ...] = ()


CHU_DE = {
    c.id: c
    for c in (
        ChuDe(
            "animal",
            "động vật",
            "TOPIC FOCUS - animals: name the species (and the breed only if you can tell "
            "it with reasonable confidence), say how many animals are visible, their "
            "colors and markings, what they are doing, and the setting. If the species "
            "is uncertain, give your best guess and say clearly that it is uncertain "
            "instead of stating it as fact.",
            ("loai gi", "con gi", "giong gi", "giong cho", "giong meo", "con vat", "dong vat"),
        ),
        ChuDe(
            "travel",
            "du lịch",
            "TOPIC FOCUS - places and travel: say what place or landmark this appears to "
            "be and where it is (city, country) ONLY from clear visual evidence such as "
            "distinctive architecture, signage or scenery. Also describe the notable "
            "features, the setting and the weather or time of day. If you cannot tell "
            "which place it is, say it is not certain and describe the setting; never "
            "invent a place name.",
            (
                "dia diem",
                "danh lam",
                "thang canh",
                "du lich",
                "di tich",
                "la o dau",
                "day la dau",
                "noi nay",
                "noi nao",
            ),
        ),
        ChuDe(
            "food",
            "món ăn",
            "TOPIC FOCUS - food: name the dish (and the cuisine if clear), list the main "
            "ingredients you can actually see, how it is served, and how many portions or "
            "items there are. If you are unsure which dish it is, say so and describe "
            "what is visible instead of guessing.",
            ("mon gi", "mon an", "nguyen lieu", "cach nau", "do an", "nau an"),
        ),
        ChuDe(
            "document",
            "tài liệu",
            "TOPIC FOCUS - documents and text: first say what kind of document it is "
            "(receipt, form, slide, screenshot, sign...). Then transcribe ALL legible "
            "text exactly as written, keeping the line order, numbers, dates and "
            "currency. Mark anything you cannot read as [unreadable]; never fill in "
            "text that is not there.",
            (
                "doc chu",
                "chu tren",
                "chu viet",
                "van ban",
                "hoa don",
                "bien lai",
                "ocr",
                "chep lai",
                "noi dung chu",
            ),
        ),
        ChuDe(CHU_DE_CHUNG, "chung", ""),
    )
}

# Lưu ý khi thêm từ khoá: so khớp là KHÔNG DẤU nên "chó này" và "chỗ này" đều thành
# "cho nay". Tránh các cụm dễ đụng nhau như vậy, và test sẽ bắt nếu lỡ thêm.

# Chủ đề mà bước lập hồ sơ ảnh được phép trả về, theo đúng thứ tự trong prompt.
CHU_DE_IDS = tuple(CHU_DE)


def khong_dau(text: str) -> str:
    """Chữ thường, bỏ dấu, đ -> d. Người dùng gõ có dấu hay không dấu đều khớp."""
    nfd = unicodedata.normalize("NFD", (text or "").lower().replace("đ", "d"))
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def chu_de_hop_le(gia_tri: object) -> Optional[str]:
    """Chuẩn hoá giá trị model trả về thành id chủ đề; None nếu không nhận ra."""
    gon = str(gia_tri or "").strip().lower()
    return gon if gon in CHU_DE else None


def chu_de_tu_cau_hoi(cau_hoi: str) -> Optional[str]:
    """Chủ đề mà CÂU HỎI chỉ thẳng tới, hoặc None nếu không có / mơ hồ.

    Khớp đúng MỘT chủ đề mới tính. Khớp hai chủ đề trở lên thì coi như mơ hồ và
    để chủ đề của ảnh quyết định.
    """
    chuan = khong_dau(cau_hoi)
    khop = [
        c.id
        for c in CHU_DE.values()
        if any(re.search(rf"\b{re.escape(tu)}\b", chuan) for tu in c.tu_khoa)
    ]
    return khop[0] if len(khop) == 1 else None


def chon_chu_de(cau_hoi: str, chu_de_cua_anh: Optional[str] = None) -> str:
    """Chủ đề dùng cho lượt này.

    Thứ tự ưu tiên: câu hỏi chỉ thẳng tới chủ đề nào (ảnh con chó nhưng hỏi
    "đọc chữ trên áo" -> tài liệu) > chủ đề ghi trong hồ sơ ảnh > chung.
    """
    return chu_de_tu_cau_hoi(cau_hoi) or chu_de_hop_le(chu_de_cua_anh) or CHU_DE_CHUNG


# --------------------------------------------------------------------------- #
# Chuyển chủ đề từ vision_tool xuống lượt nhìn ảnh
# --------------------------------------------------------------------------- #
# Các tool của Vision Agent chỉ nhận đúng một tham số `text` (hợp đồng ở
# QUY_TAC_THIET_KE.md) nên không có chỗ nhét chủ đề vào tham số. ContextVar đi theo
# lượt gọi hiện tại và tự trả về None khi ra khỏi `dung_chu_de`.
_CHU_DE_HIEN_TAI: ContextVar[Optional[str]] = ContextVar("vision_chu_de", default=None)


@contextmanager
def dung_chu_de(chu_de: Optional[str]) -> Iterator[None]:
    """Trong khối `with`, mọi lượt nhìn ảnh dùng lời dặn của `chu_de`."""
    token = _CHU_DE_HIEN_TAI.set(chu_de_hop_le(chu_de))
    try:
        yield
    finally:
        _CHU_DE_HIEN_TAI.reset(token)


def chu_de_hien_tai() -> Optional[str]:
    return _CHU_DE_HIEN_TAI.get()


def loi_dan_hien_tai() -> str:
    """Lời dặn của chủ đề đang dùng; chuỗi rỗng nếu không có (hành vi như cũ)."""
    chu_de = _CHU_DE_HIEN_TAI.get()
    return CHU_DE[chu_de].loi_dan if chu_de else ""
