"""Đăng ký các agent chủ đề — thêm một chủ đề = thêm MỘT dòng vào TOPIC_SPECS.

Lead đọc registry này để (1) dựng danh sách tool chủ đề và (2) sinh phần "các chủ
đề bạn có" trong prompt, nên không nơi nào khác hard-code tên chủ đề.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

from app.agents.research_agent.profiles import SearchProfile
from app.agents.research_agent.tools import SearchBudget
from app.agents.research_agent.topics.topic_tool import make_topic_tool


@dataclass(frozen=True)
class TopicSpec:
    name: str          # "scholar_agent": snake_case, hậu tố _agent, trùng tên thư mục và tên tool
    description: str   # tiếng Anh, >= 20 ký tự, nói KHI NÀO dùng và KHI NÀO KHÔNG (IF-08)
    build: Callable[..., Any]   # build_<name>(model=None, tools=None, prompt=None)
    default_tools: Callable[[SearchBudget, SearchProfile], list]   # tool lá của agent này


# Thêm chủ đề mới: import gói của nó rồi thêm một TopicSpec vào đây.
TOPIC_SPECS: Tuple[TopicSpec, ...] = ()


def build_topic_tools(
    profile: SearchProfile, model=None, specs: Optional[Tuple[TopicSpec, ...]] = None
) -> List:
    """Mỗi TopicSpec thành một tool cho lead. `model` (nếu có) dùng cho MỌI agent chủ đề."""
    specs = TOPIC_SPECS if specs is None else specs
    ten_chu_de = [s.name for s in specs]
    return [make_topic_tool(s, profile=profile, model=model, ten_chu_de=ten_chu_de) for s in specs]
