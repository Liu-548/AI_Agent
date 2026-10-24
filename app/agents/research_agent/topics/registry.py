"""Đăng ký các agent chủ đề — thêm một chủ đề = thêm MỘT dòng vào TOPIC_SPECS.

Lead đọc registry này để (1) dựng danh sách tool chủ đề và (2) sinh phần "các chủ
đề bạn có" trong prompt, nên không nơi nào khác hard-code tên chủ đề.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

from app.agents.research_agent.profiles import SearchProfile
from app.agents.research_agent.tools import SearchBudget
from app.agents.research_agent.topics import code_agent as code
from app.agents.research_agent.topics import culture_agent as culture
from app.agents.research_agent.topics import explainer_agent as explainer
from app.agents.research_agent.topics import news_agent as news
from app.agents.research_agent.topics import scholar_agent as scholar
from app.agents.research_agent.topics import travel_agent as travel
from app.agents.research_agent.topics.topic_tool import make_topic_tool


@dataclass(frozen=True)
class TopicSpec:
    name: str          # "scholar_agent": snake_case, hậu tố _agent, trùng tên thư mục và tên tool
    description: str   # tiếng Anh, >= 20 ký tự, nói KHI NÀO dùng và KHI NÀO KHÔNG (IF-08)
    build: Callable[..., Any]   # build_<name>(model=None, tools=None, prompt=None)
    default_tools: Callable[[SearchBudget, SearchProfile], list]   # tool lá của agent này
    # Bước hậu kiểm riêng của chủ đề, chạy SAU grounding (vd. culture cắt trích dẫn dài).
    postprocess: Optional[Callable[[str], str]] = None


# Thêm chủ đề mới: import gói của nó rồi thêm một TopicSpec vào đây.
TOPIC_SPECS: Tuple[TopicSpec, ...] = (
    TopicSpec(scholar.TOPIC_NAME, scholar.TOPIC_DESCRIPTION, scholar.build_scholar_agent, scholar.default_scholar_tools),
    TopicSpec(explainer.TOPIC_NAME, explainer.TOPIC_DESCRIPTION, explainer.build_explainer_agent, explainer.default_explainer_tools),
    TopicSpec(news.TOPIC_NAME, news.TOPIC_DESCRIPTION, news.build_news_agent, news.default_news_tools),
    TopicSpec(code.TOPIC_NAME, code.TOPIC_DESCRIPTION, code.build_code_agent, code.default_code_tools),
    TopicSpec(travel.TOPIC_NAME, travel.TOPIC_DESCRIPTION, travel.build_travel_agent, travel.default_travel_tools),
    TopicSpec(culture.TOPIC_NAME, culture.TOPIC_DESCRIPTION, culture.build_culture_agent,
              culture.default_culture_tools, postprocess=culture.gioi_han_trich_dan),
)


def build_topic_tools(
    profile: SearchProfile, model=None, specs: Optional[Tuple[TopicSpec, ...]] = None
) -> List:
    """Mỗi TopicSpec thành một tool cho lead. `model` (nếu có) dùng cho MỌI agent chủ đề."""
    specs = TOPIC_SPECS if specs is None else specs
    ten_chu_de = [s.name for s in specs]
    return [make_topic_tool(s, profile=profile, model=model, ten_chu_de=ten_chu_de) for s in specs]
