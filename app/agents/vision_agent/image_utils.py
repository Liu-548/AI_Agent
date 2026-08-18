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
