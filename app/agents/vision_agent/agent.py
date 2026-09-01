"""Vision Agent — ReAct agent mô tả ảnh + phát hiện/đếm vật thể.

Hợp đồng bắt buộc (xem QUY_TAC_THIET_KE.md, Bảng 3):
    AGENT_NAME, AGENT_DESCRIPTION, build_vision_agent(model=None, tools=None, prompt=None)
"""

from __future__ import annotations

from typing import List, Optional

from app.agents.vision_agent.prompts import VISION_AGENT_PROMPT

# PHẢI trùng tên thư mục chứa file này (quy tắc CT-05).
AGENT_NAME = "vision_agent"
AGENT_DESCRIPTION = (
    "Use for visual tasks on an image given by path or URL: describing image content, "
    "colors and context, and detecting/counting objects. Cannot search the web."
)


def build_vision_agent(model=None, tools: Optional[List] = None, prompt: Optional[str] = None):
    """Trả về một CompiledStateGraph chạy vòng lặp ReAct.

    model=None -> LLM vai trò "vision" (LLM điều phối tool). Khác với model
                  "describe" nằm bên trong tool image_describer.
    tools=None -> image_describer + detect_and_count_objects.
    """
    from langgraph.prebuilt import create_react_agent

    if model is None:
        from app.core.llm import get_llm

        model = get_llm("vision")
    if tools is None:
        from app.agents.vision_agent.tools import default_vision_tools

        tools = default_vision_tools()

    return create_react_agent(
        model=model,
        tools=tools,
        prompt=prompt or VISION_AGENT_PROMPT,
        name=AGENT_NAME,
    )
