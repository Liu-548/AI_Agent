"""Điểm khởi tạo LLM duy nhất của hệ thống.

Quy tắc: KHÔNG gọi ChatOpenAI(...)/ChatGoogleGenerativeAI(...) trực tiếp trong
agent hay tool. Luôn dùng get_llm(role).

Mỗi vai trò có model riêng, và model đó có thể nằm ở nhà cung cấp riêng nhờ cú
pháp `provider:model` trong .env (xem app/core/config.py). Nhờ vậy hệ thống chạy
LAI được: phần suy luận + gọi tool trên Groq (hạn mức miễn phí lớn), phần đọc ảnh
trên Gemini (model đa phương thức). Agent và tool không biết điều này.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from app.core.config import PROVIDER_GOOGLE, PROVIDERS, settings

# Năm vai trò = năm sổ hạn mức riêng. Xem config.py.
#   supervisor : bộ điều phối
#   research   : vòng ReAct của Research Agent
#   vision     : vòng ReAct của Vision Agent
#   describe   : model đa phương thức bên trong tool image_describer
#   utility    : tác vụ phụ (trích đường dẫn ảnh khi regex trượt)
Role = Literal["supervisor", "research", "vision", "describe", "utility"]

_MODEL_SPEC_BY_ROLE = {
    "supervisor": lambda: settings.model_supervisor,
    "research": lambda: settings.model_research,
    "vision": lambda: settings.model_vision,
    "describe": lambda: settings.model_describe,
    "utility": lambda: settings.model_utility,
}


@lru_cache(maxsize=None)
def get_llm(role: Role):
    # Không có giá trị mặc định: bắt buộc gọi kèm vai trò, để không ai vô tình
    # dồn hai thành phần vào chung một model và đốt chung một sổ hạn mức.
    if role not in _MODEL_SPEC_BY_ROLE:
        raise ValueError(
            f"role không hợp lệ: {role!r}. Chọn trong {list(_MODEL_SPEC_BY_ROLE)}"
        )

    provider, model = settings.split_model(_MODEL_SPEC_BY_ROLE[role]())
    if provider not in PROVIDERS:
        raise ValueError(
            f"Nhà cung cấp {provider!r} (vai trò {role!r}) không hợp lệ. Chọn trong {list(PROVIDERS)}."
        )
    if not model:
        raise ValueError(f"Chưa khai báo tên model cho vai trò {role!r} trong .env.")

    api_key = settings.api_key_for(provider)

    if provider == PROVIDER_GOOGLE:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            temperature=settings.temperature,
            google_api_key=api_key,
        )

    # groq và openai đều nói giao thức OpenAI -> cùng một client.
    from langchain_openai import ChatOpenAI

    kwargs = {"model": model, "temperature": settings.temperature, "api_key": api_key}
    base_url = settings.base_url_for(provider)
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


# --------------------------------------------------------------------------- #
# Liệt kê model — để không phải đoán tên model mỗi lần nhà cung cấp đổi
# --------------------------------------------------------------------------- #
def list_models(provider: str) -> list[str]:
    """Hỏi thẳng nhà cung cấp xem key của bạn dùng được những model nào.

    Tài liệu của nhà cung cấp hay lạc hậu hơn thực tế (Groq khai tử
    llama-3.3-70b-versatile cho free tier ngày 16/08/2026 mà trang models vẫn
    còn liệt kê). Endpoint này là nguồn đáng tin duy nhất.
    """
    import requests

    from app.core.config import PROVIDER_GOOGLE, PROVIDER_GROQ, PROVIDER_OPENAI

    key = settings.api_key_for(provider)

    if provider == PROVIDER_GOOGLE:
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        resp = requests.get(url, headers={"x-goog-api-key": key}, timeout=20)
        resp.raise_for_status()
        ten = []
        for m in resp.json().get("models", []):
            if "generateContent" in (m.get("supportedGenerationMethods") or []):
                ten.append(m.get("name", "").removeprefix("models/"))
        return sorted(t for t in ten if t)

    if provider == PROVIDER_GROQ:
        base = settings.base_url_for(PROVIDER_GROQ)
    else:
        base = settings.base_url_for(PROVIDER_OPENAI) or "https://api.openai.com/v1"
    resp = requests.get(
        base.rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {key}"},
        timeout=20,
    )
    resp.raise_for_status()
    return sorted(m.get("id", "") for m in resp.json().get("data", []) if m.get("id"))
