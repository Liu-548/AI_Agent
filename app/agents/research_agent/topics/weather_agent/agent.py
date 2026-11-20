"""weather_agent — chủ đề "thời tiết hiện tại và dự báo vài ngày".

Tên thư mục = TOPIC_NAME = tên tool = name= của create_react_agent (giống CT-05).
"""

from __future__ import annotations

from typing import List, Optional

from app.agents.research_agent.topics.weather_agent.prompts import WEATHER_AGENT_PROMPT

TOPIC_NAME = "weather_agent"
TOPIC_DESCRIPTION = (
    "Use for WEATHER: current conditions and the forecast for the next few days in a named "
    "city or place (temperature, rain chance, wind, sky). Returns a short cited answer from "
    "Open-Meteo. Do NOT use for climate history, travel advice (travel_agent) or natural "
    "disaster news (news_agent)."
)


def build_weather_agent(model=None, tools: Optional[List] = None, prompt: Optional[str] = None):
    """model=None -> LLM vai trò "research_topic"; tools=None -> weather_forecast."""
    from langgraph.prebuilt import create_react_agent

    if model is None:
        from app.core.llm import get_llm

        model = get_llm("research_topic")
    if tools is None:
        from app.agents.research_agent.profiles import get_profile
        from app.agents.research_agent.tools import SearchBudget
        from app.agents.research_agent.topics.weather_agent.tools import default_weather_tools

        profile = get_profile()
        tools = default_weather_tools(SearchBudget(max_calls=profile.max_searches_per_topic), profile)

    return create_react_agent(model=model, tools=tools, prompt=prompt or WEATHER_AGENT_PROMPT, name=TOPIC_NAME)
