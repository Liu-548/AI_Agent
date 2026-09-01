"""Tiện ích ảnh dùng chung cho Vision Agent.

Khác tài liệu gốc ở một điểm: KHÔNG dùng python-magic.
python-magic cần thư viện hệ thống libmagic1 (Linux) / python-magic-bin (Windows),
ba máy khác hệ điều hành sẽ hỏng ở đúng chỗ này. Ở đây dùng Pillow + mimetypes,
chạy giống nhau trên Windows/macOS/Linux.
"""

from __future__ import annotations

import base64
import io
import mimetypes
import os
import re
from typing import Optional, Tuple, Union

import requests

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")

# Bắt URL ảnh hoặc đường dẫn file ảnh trong câu tiếng Việt/tiếng Anh tự do.
_URL_RE = re.compile(r"https?://[^\s'\"<>)\]]+", re.IGNORECASE)
# Tách câu thành token; giữ nguyên dấu ':' để không phá đường dẫn Windows "C:/..."
_TOKEN_SPLIT_RE = re.compile(r"[\s,;\"'()<>\[\]]+")
# Nhãn kiểu "image:", "Ảnh:" đứng trước đường dẫn (>=2 chữ cái nên "C:" không dính).
_LABEL_PREFIX_RE = re.compile(r"^[^\W\d_]{2,}\s*:", re.UNICODE)

REQUEST_TIMEOUT = 15


def _sniff_mime(data: bytes, fallback_name: str = "") -> Optional[str]:
    """Đoán MIME type từ NỘI DUNG bytes, không tin vào đuôi file.

    File tên .png nhưng ruột là text vẫn phải bị từ chối — nếu không, ảnh hỏng sẽ
    đi thẳng vào payload gửi cho vision model và lỗi ở tận trên đó, rất khó lần.
    """
    try:
        from PIL import Image  # Pillow: cross-platform, thay cho python-magic
    except ImportError:  # pragma: no cover - chỉ khi thiếu Pillow
        guessed, _ = mimetypes.guess_type(fallback_name) if fallback_name else (None, None)
        return guessed if guessed and guessed.startswith("image/") else None

    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = (im.format or "").lower()
    except Exception:
        return None
    if not fmt:
        return None
    return f"image/{'jpeg' if fmt == 'jpeg' else fmt}"


def encode_image(
    image_path_or_url: str, get_mime_type: bool = False
) -> Union[None, str, Tuple[Optional[str], Optional[str]]]:
    """Đọc ảnh từ URL hoặc file local -> chuỗi base64.

    Trả về b64, hoặc (b64, mime) nếu get_mime_type=True.
    Lỗi -> None (hoặc (None, None)). Hàm này KHÔNG raise.
    """

    def _fail():
        return (None, None) if get_mime_type else None

    if not image_path_or_url:
        return _fail()

    if image_path_or_url.lower().startswith("http"):
        try:
            resp = requests.get(image_path_or_url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.content
        except requests.exceptions.RequestException:
            return _fail()
        mime = _sniff_mime(data, image_path_or_url) or resp.headers.get("content-type")
    else:
        if not os.path.exists(image_path_or_url):
            return _fail()
        with open(image_path_or_url, "rb") as f:
            data = f.read()
        mime = _sniff_mime(data, image_path_or_url)

    if not mime or not str(mime).startswith("image/"):
        return _fail()

    b64 = base64.b64encode(data).decode("utf-8")
    return (b64, mime) if get_mime_type else b64


def draw_detections(image_ref: str, detections: list, output_path: Optional[str] = None) -> Optional[str]:
    """Vẽ khung + nhãn (class, confidence) lên ảnh gốc từ kết quả detect_and_count_objects.

    image_ref    : path hoặc URL ảnh gốc (giống tham số truyền cho encode_image).
    detections   : list các dict {"class": ..., "confidence": ..., "bbox": [x1,y1,x2,y2]}
                   -- đúng định dạng trả về của parse_yolo_results()["detections"].
    output_path  : nơi lưu ảnh mới. None -> tự đặt tên "<ten_goc>_detected.jpg" cạnh ảnh gốc
                   (chỉ áp dụng khi image_ref là file local; ảnh tải từ URL bắt buộc phải
                   truyền output_path).

    Trả về đường dẫn file đã lưu, hoặc None nếu không đọc/vẽ được (không raise).
    """
    from PIL import Image, ImageDraw, ImageFont

    if not detections:
        return None

    try:
        if image_ref.lower().startswith("http"):
            resp = requests.get(image_ref, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            if output_path is None:
                return None  # không có tên file gốc để tự đặt tên ra -> bắt buộc phải truyền
        else:
            if not os.path.exists(image_ref):
                return None
            img = Image.open(image_ref).convert("RGB")
            if output_path is None:
                root, _ext = os.path.splitext(image_ref)
                output_path = f"{root}_detected.jpg"
    except Exception:
        return None

    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default()
    except Exception:  # pragma: no cover - luôn có sẵn trên hầu hết máy
        font = None

    # Một màu cố định cho mỗi tên class, để cùng loại vật thể luôn cùng màu khung.
    palette = ["#FF3B30", "#34C759", "#007AFF", "#FF9500", "#AF52DE", "#00C7BE"]
    color_by_class: dict = {}

    for det in detections:
        cls = str(det.get("class", "?"))
        conf = det.get("confidence", 0)
        bbox = det.get("bbox") or [0, 0, 0, 0]
        x1, y1, x2, y2 = bbox
        color = color_by_class.setdefault(cls, palette[len(color_by_class) % len(palette)])

        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        label = f"{cls} {conf:.0%}" if isinstance(conf, (int, float)) else cls
        text_bbox = draw.textbbox((x1, y1), label, font=font)
        text_h = text_bbox[3] - text_bbox[1]
        draw.rectangle([x1, y1 - text_h - 4, text_bbox[2] + 4, y1], fill=color)
        draw.text((x1 + 2, y1 - text_h - 2), label, fill="white", font=font)

    try:
        img.save(output_path, "JPEG", quality=90)
    except Exception:
        return None
    return output_path


def extract_image_ref(text: str, llm=None) -> Optional[str]:
    """Tách đường dẫn/URL ảnh ra khỏi câu hỏi tự do.

    Chiến lược 2 tầng:
      1) regex — nhanh, miễn phí, đúng với >95% trường hợp thực tế;
      2) nếu regex trượt và có `llm` thì mới nhờ LLM trích xuất (như tài liệu gốc).
    Nhờ tầng 1 mà mỗi lần gọi tool không tốn thêm một lượt LLM, và test chạy được
    khi không có API key.
    """
    if not text:
        return None

    # 1a. URL có đuôi ảnh rõ ràng
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;:")
        if url.lower().split("?")[0].endswith(IMAGE_EXTS):
            return url

    # 1a-bis. Đường dẫn local có DẤU CÁCH trong tên thư mục
    # (vd Windows "C:\Users\Dell Latitude 7410\Downloads\test.jpg").
    # Token-split ở bước 1b bên dưới cắt theo khoảng trắng nên sẽ làm gãy path kiểu
    # này (mất phần trước dấu cách). Ở đây bắt path trực tiếp bằng regex cho phép
    # dấu cách BÊN TRONG mỗi thành phần thư mục, nhưng không cho phép các ký tự
    # không hợp lệ trong path ('/', '\', ':', '*', '?', '"', '<', '>', '|').
    _EXT_ALT = "|".join(e.lstrip(".") for e in IMAGE_EXTS)
    _WIN_PATH_RE = re.compile(
        r"[A-Za-z]:[\\/](?:[^\r\n\\/:*?\"<>|]+[\\/])*[^\r\n\\/:*?\"<>|]+\.(?:%s)" % _EXT_ALT,
        re.IGNORECASE,
    )
    _UNIX_PATH_RE = re.compile(
        r"/(?:[^\r\n/:*?\"<>|]+/)*[^\r\n/:*?\"<>|]+\.(?:%s)" % _EXT_ALT,
        re.IGNORECASE,
    )
    for pattern in (_WIN_PATH_RE, _UNIX_PATH_RE):
        m = pattern.search(text)
        if m:
            cand = m.group(0).strip().rstrip(".,;:!?")
            if os.path.exists(cand):
                return cand

    # 1b. Đường dẫn file local
    for raw in _TOKEN_SPLIT_RE.split(text):
        token = _LABEL_PREFIX_RE.sub("", raw).strip().rstrip(".,;:!?")
        if not token or token.lower().startswith("http"):
            continue
        if token.lower().endswith(IMAGE_EXTS):
            return token

    # 1c. URL không có đuôi ảnh (link CDN) — vẫn thử vì server có thể trả image/*
    m = _URL_RE.search(text)
    if m:
        return m.group(0).rstrip(".,;:")

    if llm is None:
        return None
    return _extract_with_llm(text, llm)


def _extract_with_llm(text: str, llm) -> Optional[str]:
    # Lấy từ langchain_core (không phải gói `langchain`): gói `langchain` 1.x đã bỏ
    # namespace langchain.output_parsers.
    from langchain_core.output_parsers import PydanticOutputParser
    from langchain_core.prompts import PromptTemplate
    from pydantic import BaseModel, Field

    from app.agents.vision_agent.prompts import IMAGE_REF_EXTRACTOR_PROMPT

    class ImageInput(BaseModel):
        image_path_or_url: str = Field(description="Image path or URL")

    parser = PydanticOutputParser(pydantic_object=ImageInput)
    prompt = PromptTemplate.from_template(IMAGE_REF_EXTRACTOR_PROMPT).partial(
        format_instructions=parser.get_format_instructions()
    )
    try:
        parsed = (prompt | llm | parser).invoke({"input": text})
        return parsed.image_path_or_url or None
    except Exception:
        return None