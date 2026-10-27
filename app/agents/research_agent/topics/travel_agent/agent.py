"""travel_agent — chủ đề "du lịch và địa điểm" (Phase 4 trong SPEC §13).

Tên thư mục = TOPIC_NAME = tên tool = name= của create_react_agent (giống CT-05).
"""

from __future__ import annotations

from typing import List, Optional

from app.agents.research_agent.topics.travel_agent.prompts import TRAVEL_AGENT_PROMPT

TOPIC_NAME = "travel_agent"
TOPIC_DESCRIPTION = (
    "Use for TRAVEL and PLACES: destinations, what to see or do, food, getting there and "
    "around, where a landmark or venue is. Returns a short cited answer from Wikivoyage and "
    "OpenStreetMap. Has NO live prices, bookings, weather or verified opening hours. Do NOT "
    "use for news or recent events in a place (news_agent)."
)


def build_travel_agent(model=None, tools: Optional[List] = None, prompt: Optional[str] = None):
    """model=None -> LLM vai trò "research_topic"; tools=None -> wikivoyage + place_lookup + wikipedia."""
    from langgraph.prebuilt import create_react_agent

    if model is None:
        from app.core.llm import get_llm

        model = get_llm("research_topic")
    if tools is None:
        from app.agents.research_agent.profiles import get_profile
        from app.agents.research_agent.tools import SearchBudget
        from app.agents.research_agent.topics.travel_agent.tools import default_travel_tools

        profile = get_profile()
        tools = default_travel_tools(SearchBudget(max_calls=profile.max_searches_per_topic), profile)

    return create_react_agent(model=model, tools=tools, prompt=prompt or TRAVEL_AGENT_PROMPT, name=TOPIC_NAME)
