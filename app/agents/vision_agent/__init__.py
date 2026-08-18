"""Gói Vision Agent — TOÀN BỘ code của agent này nằm trong thư mục này.

    agent.py        định nghĩa agent + hợp đồng
    tools.py        image_describer, detect_and_count_objects
    prompts.py      prompt của agent và của tool mô tả ảnh
    image_utils.py  encode_image, extract_image_ref (chỉ Vision dùng)

Chủ sở hữu: người phụ trách Vision Agent.
"""

from app.agents.vision_agent.agent import (
    AGENT_DESCRIPTION,
    AGENT_NAME,
    build_vision_agent,
)
from app.agents.vision_agent.image_utils import encode_image, extract_image_ref
from app.agents.vision_agent.tools import (
    default_vision_tools,
    make_detect_and_count_tool,
    make_image_describer_tool,
)

__all__ = [
    "AGENT_NAME",
    "AGENT_DESCRIPTION",
    "build_vision_agent",
    "default_vision_tools",
    "make_image_describer_tool",
    "make_detect_and_count_tool",
    "encode_image",
    "extract_image_ref",
]
