"""news_agent — chủ đề "tin tức, phỏng vấn, sự kiện gần đây" (thứ không có trong bài báo khoa học).

Tên thư mục = TOPIC_NAME = tên tool = name= của create_react_agent (giống CT-05).
"""

from __future__ import annotations

from typing import List, Optional

from app.agents.research_agent.topics.news_agent.prompts import NEWS_AGENT_PROMPT

TOPIC_NAME = "news_agent"
TOPIC_DESCRIPTION = (
    "Use for NEWS and current events: interviews, statements of public figures, company or "
    "product announcements, recent happenings, anything time-sensitive or not covered by "
    "scholarly papers. Returns a short cited summary of news reports. Do NOT use to find "
    "research papers (scholar_agent) or to explain a concept (explainer_agent)."
)


def build_news_agent(model=None, tools: Optional[List] = None, prompt: Optional[str] = None):
    """model=None -> LLM vai trò "research_topic"; tools=None -> news_search + wikipedia_search."""
    from langgraph.prebuilt import create_react_agent

    if model is None:
        from app.core.llm import get_llm

        model = get_llm("research_topic")
    if tools is None:
        from app.agents.research_agent.profiles import get_profile
        from app.agents.research_agent.tools import SearchBudget
        from app.agents.research_agent.topics.news_agent.tools import default_news_tools

        profile = get_profile()
        tools = default_news_tools(SearchBudget(max_calls=profile.max_searches_per_topic), profile)

    return create_react_agent(model=model, tools=tools, prompt=prompt or NEWS_AGENT_PROMPT, name=TOPIC_NAME)

