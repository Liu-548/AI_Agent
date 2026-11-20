"""geo_agent — chủ đề "quốc gia và địa lý": thủ đô, dân số, diện tích, ngôn ngữ, tiền tệ...

Tên thư mục = TOPIC_NAME = tên tool = name= của create_react_agent (giống CT-05).
"""

from __future__ import annotations

from typing import List, Optional

from app.agents.research_agent.topics.geo_agent.prompts import GEO_AGENT_PROMPT

TOPIC_NAME = "geo_agent"
TOPIC_DESCRIPTION = (
    "Use for COUNTRIES and GEOGRAPHY facts: capital, population, area, region, income level, "
    "official languages, currency, plus background on rivers, mountains and regions. Returns "
    "a short cited answer from the World Bank country data and Wikipedia. Do NOT use for "
    "travel tips (travel_agent), economic statistics (economy_agent) or weather "
    "(weather_agent)."
)


def build_geo_agent(model=None, tools: Optional[List] = None, prompt: Optional[str] = None):
    """model=None -> LLM vai trò "research_topic"; tools=None -> country_lookup + wikipedia."""
    from langgraph.prebuilt import create_react_agent

    if model is None:
        from app.core.llm import get_llm

        model = get_llm("research_topic")
    if tools is None:
        from app.agents.research_agent.profiles import get_profile
        from app.agents.research_agent.tools import SearchBudget
        from app.agents.research_agent.topics.geo_agent.tools import default_geo_tools

        profile = get_profile()
        tools = default_geo_tools(SearchBudget(max_calls=profile.max_searches_per_topic), profile)

    return create_react_agent(model=model, tools=tools, prompt=prompt or GEO_AGENT_PROMPT, name=TOPIC_NAME)
