"""Bộ nhớ ảnh theo hội thoại — việc riêng của tầng web, nằm cạnh `app/store.py`.

Vấn đề cần giải: người dùng gửi ảnh 1, 2, 3, 4... rồi quay lại hỏi "con mèo cam
lúc nãy". Trước đây hệ thống chỉ nhớ đường dẫn ảnh của 6 lượt gần nhất, file ảnh
mất sau 24 giờ (hoặc khi server restart), và không có gì giúp phân biệt hai ảnh
cùng loại. File này thêm ba thứ:

1. HỒ SƠ ẢNH — mỗi ảnh có một hồ sơ ngắn có cấu trúc (chủ thể, số lượng, màu,
   bối cảnh, đặc điểm riêng). Đây là thứ để phân biệt "mèo cam trên sofa" với
   "hai con mèo đen ngoài sân".
2. DANH MỤC — mọi ảnh còn được nhớ của hội thoại được liệt kê cho supervisor ở
   MỖI lượt hỏi, không phụ thuộc HISTORY_MAX_TURNS.
3. BÍ DANH — supervisor gọi ảnh bằng mã ngắn `IMG3`, không phải chép lại một
   đường dẫn dài 100 ký tự. Mã được đổi thành file thật ngay trước khi vision
   agent chạy; file đã bị dọn thì dựng lại từ bản lưu trong database.

Không có logic agent nào ở đây (CT-03): file này chỉ chuẩn bị ngữ cảnh và giữ ảnh.
"""

from __future__ import annotations

import io
import json
import logging
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional

from app import store
from app.agents.vision_agent.topics import chu_de_hop_le

log = logging.getLogger(__name__)

# Bản ảnh lưu trong database: đủ lớn để đếm vật thể và đọc chi tiết, đủ nhỏ để
# 20 ảnh/hội thoại chỉ tốn vài MB (Neon free có 0.5GB).
CANH_DAI_LUU_PX = 1024
CHAT_LUONG_JPEG = 80

TIEN_TO_BI_DANH = "IMG"

# Trường của hồ sơ, theo đúng thứ tự in ra danh mục.
TRUONG_HO_SO = ("subject", "topic", "count", "colors", "scene", "distinctive")
DO_DAI_TRUONG = 90
SO_GHI_CHU = 3
DO_DAI_GHI_CHU = 220

HO_SO_PROMPT = """You are indexing an image so it can be told apart from other \
images later. Reply with ONE JSON object and nothing else, using exactly these keys:
- "subject": the main subject(s), most specific common name (e.g. "mèo", "chó Corgi", "biểu đồ cột")
- "count": how many main subjects are visible, as a number
- "colors": dominant colors of the main subject(s)
- "scene": where it is / the background, in a few words
- "distinctive": one detail that would distinguish this image from a similar one
- "topic": exactly one of "animal" (pets, wildlife, birds, fish...), "travel" \
(landmarks, tourist places, landscapes, cityscapes), "food" (dishes, drinks, \
ingredients), "document" (text-heavy: receipts, forms, slides, screenshots, signs), \
"general" (anything else)

Write every value in Vietnamese WITH full diacritics, at most 12 words each, EXCEPT \
"topic", which must be one of the five English words above.
Describe only what is visible. If something cannot be determined, use ""."""


def bi_danh(stt: int) -> str:
    """Mã ngắn của ảnh thứ `stt` trong hội thoại, ví dụ IMG3."""
    return f"{TIEN_TO_BI_DANH}{int(stt)}"


def nen_anh(path: Path | str) -> Optional[bytes]:
    """Thu nhỏ + nén ảnh để lưu database. None nếu không đọc được."""
    try:
        from PIL import Image, ImageOps

        with Image.open(path) as im:
            # Ảnh điện thoại ghi hướng xoay trong EXIF; bỏ qua là ảnh lưu bị nằm ngang.
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((CANH_DAI_LUU_PX, CANH_DAI_LUU_PX))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=CHAT_LUONG_JPEG, optimize=True)
        return buf.getvalue()
    except Exception:  # noqa: BLE001 - thiếu bản lưu không được làm hỏng câu trả lời
        log.warning("khong nen duoc anh de luu: %s", path)
        return None


# --------------------------------------------------------------------------- #
# Hồ sơ ảnh
# --------------------------------------------------------------------------- #
def _cat(text: object, toi_da: int) -> str:
    gon = " ".join(str(text or "").split())
    return gon if len(gon) <= toi_da else gon[: toi_da - 1].rstrip() + "…"


def _doc_json(text: str) -> dict:
    """Lấy object JSON đầu tiên trong câu trả lời của model (có thể kèm ```json)."""
    khop = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not khop:
        return {}
    try:
        gia_tri = json.loads(khop.group(0))
    except json.JSONDecodeError:
        return {}
    return gia_tri if isinstance(gia_tri, dict) else {}


def _goi_llm_ho_so(path: Path | str) -> dict:
    """MỘT lượt gọi model đa phương thức vai trò "utility" để lập hồ sơ ảnh.

    Dùng vai trò utility (không phải describe) để không ăn chung sổ hạn mức với
    tool image_describer. Lỗi gì cũng ném ra — `tao_ho_so` bắt và dùng đường lùi.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.agents.vision_agent.image_utils import encode_image
    from app.core.llm import get_llm
    from app.core.pretty import message_text

    b64, mime = encode_image(str(path), get_mime_type=True)
    if not b64 or not mime:
        raise ValueError("khong doc duoc anh")
    ket_qua = get_llm("utility").invoke(
        [
            SystemMessage(content=HO_SO_PROMPT),
            HumanMessage(
                content=[
                    {"type": "text", "text": "Index this image."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ]
            ),
        ]
    )
    return _doc_json(message_text(getattr(ket_qua, "content", "")))


def lam_sach_ho_so(tho: dict) -> dict:
    """Chỉ giữ các trường đã biết, ép về chuỗi ngắn. Model trả gì lạ thì bỏ."""
    sach: Dict[str, object] = {}
    for ten in TRUONG_HO_SO:
        gia_tri = _cat(tho.get(ten, ""), DO_DAI_TRUONG) if isinstance(tho, dict) else ""
        if ten == "topic":
            # Chỉ nhận id chủ đề có thật; model trả chữ lạ thì bỏ (-> chủ đề chung).
            gia_tri = chu_de_hop_le(gia_tri) or ""
        if gia_tri and gia_tri.lower() not in ("none", "null", "n/a"):
            sach[ten] = gia_tri
    return sach


def them_ghi_chu(ho_so: Optional[dict], ghi_chu: str) -> dict:
    """Thêm một điều đã biết về ảnh (trích câu trả lời của vision agent).

    Giữ SO_GHI_CHU ghi chú gần nhất. Nhờ các ghi chú này mà hỏi lại ảnh cũ về
    điều đã trả lời rồi thì không phải tốn thêm một lượt đọc ảnh.
    """
    moi = dict(ho_so or {})
    gon = _cat(ghi_chu, DO_DAI_GHI_CHU)
    if not gon or gon.startswith("ERROR:"):
        return moi
    ds = [g for g in moi.get("notes", []) if isinstance(g, str) and g != gon]
    moi["notes"] = (ds + [gon])[-SO_GHI_CHU:]
    return moi


def tao_ho_so(path: Path | str, ghi_chu: str = "") -> dict:
    """Hồ sơ của một ảnh vừa gửi.

    Bật IMAGE_PROFILE_LLM: thử lập hồ sơ có cấu trúc bằng một lượt gọi model.
    Tắt, hoặc lượt gọi đó hỏng (thiếu key, hết hạn mức, model không đọc được
    ảnh): hồ sơ chỉ còn ghi chú trích từ câu trả lời đầu tiên. Hàm KHÔNG raise.
    """
    from app.core import config

    ho_so: dict = {}
    if config.settings.image_profile_llm:
        try:
            ho_so = lam_sach_ho_so(_goi_llm_ho_so(path))
        except Exception as exc:  # noqa: BLE001
            log.info("khong lap duoc ho so anh bang LLM (%s) - dung ghi chu", type(exc).__name__)
    return them_ghi_chu(ho_so, ghi_chu)


# --------------------------------------------------------------------------- #
# Danh mục gửi cho supervisor
# --------------------------------------------------------------------------- #
def _dong_danh_muc(anh: dict) -> str:
    ho_so = anh.get("profile") or {}
    phan = [bi_danh(anh["stt"])]
    phan += [f"{ten}: {ho_so[ten]}" for ten in TRUONG_HO_SO if ho_so.get(ten)]
    ghi_chu = [g for g in ho_so.get("notes", []) if isinstance(g, str) and g]
    if ghi_chu:
        phan.append("known: " + " / ".join(ghi_chu))
    if len(phan) == 1:
        phan.append("(no description stored)")
    if not anh.get("con_anh") and not (anh.get("temp_path") and Path(anh["temp_path"]).exists()):
        phan.append("FILE GONE - answer only from what is written here")
    return " | ".join(phan)


def khoi_danh_muc(ds_anh: List[dict], so_moi: Optional[int] = None) -> str:
    """Khối chữ liệt kê các ảnh còn được nhớ. Rỗng nếu hội thoại chưa có ảnh nào.

    `so_moi`: số thứ tự của ảnh đính kèm NGAY lượt này (chưa có hồ sơ).
    """
    dong = [_dong_danh_muc(a) for a in ds_anh]
    if so_moi is not None:
        dong.append(f"{bi_danh(so_moi)} | attached to the CURRENT message, not analysed yet")
    if not dong:
        return ""
    return "\n".join(
        [
            "[IMAGE MEMORY] Images the user has sent in this conversation, oldest first:",
            *dong,
            "[END IMAGE MEMORY]",
        ]
    )


# --------------------------------------------------------------------------- #
# Đổi bí danh -> file thật
# --------------------------------------------------------------------------- #
class BoGiaiAnh:
    """Đổi số thứ tự ảnh thành đường dẫn file đọc được, cho MỘT lượt hỏi.

    Được đưa vào `config["configurable"]["image_resolver"]` của graph; tool
    vision của supervisor gọi nó khi gặp `IMG3`. Chỉ ảnh thật sự được gọi tới
    mới bị đọc từ database và ghi ra đĩa — không dựng lại cả 20 ảnh mỗi lượt.
    """

    def __init__(
        self,
        conversation_id: Optional[str],
        ds_anh: List[dict],
        thu_muc: Path,
        anh_moi: Optional[Dict[int, str]] = None,
        ho_so_moi: Optional[Dict[int, dict]] = None,
    ):
        self.conversation_id = conversation_id
        self.thu_muc = Path(thu_muc)
        self.da_biet: Dict[int, str] = {a["stt"]: a.get("temp_path", "") for a in ds_anh}
        self.anh_moi: Dict[int, str] = dict(anh_moi or {})
        # Hồ sơ đã lập sẵn cho ảnh gửi NGAY lượt này (chưa nằm trong database).
        self.ho_so: Dict[int, dict] = {a["stt"]: (a.get("profile") or {}) for a in ds_anh}
        self.ho_so.update(ho_so_moi or {})
        # Thứ tự các ảnh đã được gọi tới trong lượt này (để cập nhật ghi chú).
        self.da_dung: List[int] = []

    def __call__(self, stt: int) -> Optional[str]:
        duong_dan = self._tim(int(stt))
        if duong_dan and int(stt) not in self.da_dung:
            self.da_dung.append(int(stt))
        return duong_dan

    def chu_de(self, stt: int) -> Optional[str]:
        """Chủ đề ghi trong hồ sơ của ảnh `stt`, None nếu chưa có."""
        return chu_de_hop_le(self.ho_so.get(int(stt), {}).get("topic"))

    def _tim(self, stt: int) -> Optional[str]:
        if stt in self.anh_moi:
            return self.anh_moi[stt]
        if stt not in self.da_biet or not self.conversation_id:
            return None
        cu = self.da_biet[stt]
        if cu and Path(cu).exists():
            return cu
        du_lieu = store.lay_du_lieu_anh(self.conversation_id, stt)
        if not du_lieu:
            return None
        self.thu_muc.mkdir(parents=True, exist_ok=True)
        dich = self.thu_muc / f"mem_{self.conversation_id[:16]}_{stt}.jpg"
        dich.write_bytes(du_lieu)
        store.cap_nhat_anh(self.conversation_id, stt, temp_path=str(dich))
        self.da_biet[stt] = str(dich)
        return str(dich)


GiaiAnh = Callable[[int], Optional[str]]
