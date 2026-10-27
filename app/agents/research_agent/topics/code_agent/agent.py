"""code_agent — chủ đề "lập trình, thư viện, lỗi phần mềm" (Phase 3 trong SPEC §13).

Tên thư mục = TOPIC_NAME = tên tool = name= của create_react_agent (giống CT-05).
"""

from __future__ import annotations

from typing import List, Optional

from app.agents.research_agent.topics.code_agent.prompts import CODE_AGENT_PROMPT

TOPIC_NAME = "code_agent"
TOPIC_DESCRIPTION = (
    "Use for PROGRAMMING and software questions: libraries, frameworks, open-source "
    "repositories, error messages, how to do something in a language or tool. Returns a "
    "short cited answer from GitHub repositories and Stack Overflow. Do NOT use for "
    "research papers (scholar_agent) or for explaining a general concept (explainer_agent)."
)


def build_code_agent(model=None, tools: Optional[List] = None, prompt: Optional[str] = None):
    """model=None -> LLM vai trò "research_topic"; tools=None -> stackoverflow_search + github_search."""
    from langgraph.prebuilt import create_react_agent

    if model is None:
        from app.core.llm import get_llm

        model = get_llm("research_topic")
    if tools is None:
        from app.agents.research_agent.profiles import get_profile
        from app.agents.research_agent.tools import SearchBudget
        from app.agents.research_agent.topics.code_agent.tools import default_code_tools

        profile = get_profile()
        tools = default_code_tools(SearchBudget(max_calls=profile.max_searches_per_topic), profile)

    return create_react_agent(model=model, tools=tools, prompt=prompt or CODE_AGENT_PROMPT, name=TOPIC_NAME)
