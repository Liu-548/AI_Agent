"""economy_agent — chủ đề "số liệu kinh tế vĩ mô của quốc gia + tỷ giá ngoại tệ".

Tên thư mục = TOPIC_NAME = tên tool = name= của create_react_agent (giống CT-05).
Không tư vấn đầu tư: prompt chỉ cho đọc số liệu, không dự đoán hay khuyên mua bán.
"""

from __future__ import annotations

from typing import List, Optional

from app.agents.research_agent.topics.economy_agent.prompts import ECONOMY_AGENT_PROMPT

TOPIC_NAME = "economy_agent"
TOPIC_DESCRIPTION = (
    "Use for ECONOMIC STATISTICS and EXCHANGE RATES: a country's GDP, GDP growth, GDP per "
    "capita, inflation, unemployment, population, exports, debt; and today's currency "
    "exchange rates (e.g. USD to VND). Returns a short cited answer from the World Bank and "
    "open.er-api.com. Do NOT use for stock prices, investment advice or business news "
    "(news_agent)."
)


def build_economy_agent(model=None, tools: Optional[List] = None, prompt: Optional[str] = None):
    """model=None -> LLM vai trò "research_topic"; tools=None -> worldbank_indicator + exchange_rate."""
    from langgraph.prebuilt import create_react_agent

    if model is None:
        from app.core.llm import get_llm

        model = get_llm("research_topic")
    if tools is None:
        from app.agents.research_agent.profiles import get_profile
        from app.agents.research_agent.tools import SearchBudget
        from app.agents.research_agent.topics.economy_agent.tools import default_economy_tools

        profile = get_profile()
        tools = default_economy_tools(SearchBudget(max_calls=profile.max_searches_per_topic), profile)

    return create_react_agent(model=model, tools=tools, prompt=prompt or ECONOMY_AGENT_PROMPT, name=TOPIC_NAME)
