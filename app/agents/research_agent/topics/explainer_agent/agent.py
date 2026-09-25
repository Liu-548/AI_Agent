"""explainer_agent — chủ đề "giải thích khái niệm khoa học phổ thông", nguồn chính là Wikipedia.

Tên thư mục = TOPIC_NAME = tên tool = name= của create_react_agent (giống CT-05).
"""

from __future__ import annotations

from typing import List, Optional

from app.agents.research_agent.topics.explainer_agent.prompts import EXPLAINER_AGENT_PROMPT

TOPIC_NAME = "explainer_agent"
TOPIC_DESCRIPTION = (
    "Use to EXPLAIN a scientific or technical concept, definition, mechanism or background "
    "(what is X, how does X work, why does X happen). Returns a short cited explanation "
    "based mainly on Wikipedia. Do NOT use to find or list research papers; use "
    "scholar_agent for that."
)


def build_explainer_agent(model=None, tools: Optional[List] = None, prompt: Optional[str] = None):
    """Trả về một CompiledStateGraph ReAct.

    model=None -> LLM của vai trò "research_topic".
    tools=None -> wikipedia_search + arxiv_search với profile hiện hành.
    """
    from langgraph.prebuilt import create_react_agent

    if model is None:
        from app.core.llm import get_llm

        model = get_llm("research_topic")
    if tools is None:
        from app.agents.research_agent.profiles import get_profile
        from app.agents.research_agent.tools import SearchBudget
        from app.agents.research_agent.topics.explainer_agent.tools import default_explainer_tools

        profile = get_profile()
        tools = default_explainer_tools(SearchBudget(max_calls=profile.max_searches_per_topic), profile)

    return create_react_agent(
        model=model,
        tools=tools,
        prompt=prompt or EXPLAINER_AGENT_PROMPT,
        name=TOPIC_NAME,
    )
