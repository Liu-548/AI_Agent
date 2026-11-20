"""Khung chung cho tool lá gọi API web công khai (dùng cho code/travel/culture agent).

Sáu tool mới (GitHub, Stack Overflow, Wikivoyage, OpenStreetMap, Open Library,
MusicBrainz) đều lặp đúng một vòng: kiểm đầu vào rỗng -> xin lượt SearchBudget ->
gọi HTTP -> định dạng -> bắt lỗi thành chuỗi "ERROR: ..." (IF-05). Gom vòng đó vào
đây để mỗi chủ đề chỉ còn viết phần RIÊNG: gọi API nào và in kết quả ra sao.

Khuôn kết quả chung, mỗi mục một khối, bắt đầu bằng dòng "Label: [...]":
GROUNDING_RULES bảo model chép nguyên văn dòng này, và grounding đối chiếu nhãn
với văn bản tool nên KHÔNG phải sửa app/core/grounding.py cho nhãn mới.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from app.agents.research_agent.tools import SearchBudget
from app.core.contracts import tool_error


def get_json(url: str, params: Optional[Dict] = None, headers: Optional[Dict] = None):
    """GET -> JSON. User-Agent có liên hệ là BẮT BUỘC với Nominatim/MusicBrainz/Wikimedia."""
    import requests

    from app.core.config import settings

    r = requests.get(
        url, params=params, timeout=15,
        headers={"User-Agent": settings.wikipedia_user_agent, **(headers or {})},
    )
    r.raise_for_status()
    return r.json()


def cat(text, n: int) -> str:
    """Gọn một trường văn bản: gộp khoảng trắng, cắt ở n ký tự."""
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def make_web_tool(
    budget: Optional[SearchBudget],
    *,
    name: str,
    description: str,
    error_code: str,
    search: Callable[[str], List[str]],
):
    """search(text) -> list khối kết quả đã định dạng (rỗng = không có kết quả)."""
    from langchain_core.tools import StructuredTool

    def _run(text: str) -> str:
        if not text or not text.strip():
            return tool_error("EMPTY_QUERY", f"{name} cần một truy vấn.")
        text = text.strip()
        if budget is not None:
            tu_choi = budget.xin_luot(name, text)
            if tu_choi is not None:
                return tu_choi
        try:
            khoi = search(text)
        except Exception as exc:  # noqa: BLE001 - tool không raise (IF-05)
            return tool_error(error_code, f"{type(exc).__name__}: {str(exc)[:150]}")
        if not khoi:
            return f"No results from {name} for: {text}"  # LX-05: không trả chuỗi rỗng
        return "\n\n".join(khoi)

    return StructuredTool.from_function(
        func=_run, name=name, description=description, metadata={"search_budget": budget},
    )
