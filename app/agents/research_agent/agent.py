"""Research Agent — ReAct agent tra cứu arXiv + Wikipedia.

Hợp đồng bắt buộc (xem QUY_TAC_THIET_KE.md, Bảng 3):
    AGENT_NAME, AGENT_DESCRIPTION, build_research_agent(model=None, tools=None, prompt=None)
"""

from __future__ import annotations

from typing import List, Optional

from app.agents.research_agent.prompts import RESEARCH_AGENT_PROMPT

# PHẢI trùng tên thư mục chứa file này (quy tắc CT-05).
AGENT_NAME = "research_agent"
AGENT_DESCRIPTION = (
    "Use for research-related tasks: finding scientific papers on arXiv and looking up "
    "concepts/definitions on Wikipedia. Cannot see images."
)


def build_research_agent(model=None, tools: Optional[List] = None, prompt: Optional[str] = None):
    """Trả về một CompiledStateGraph chạy vòng lặp ReAct.

    model=None  -> LLM của vai trò "research" (cần LLM_API_KEY).
    tools=None  -> arxiv_search + wikipedia_search.
    """
    from langgraph.prebuilt import create_react_agent

    if model is None:
        from app.core.llm import get_llm

        model = get_llm("research")
    if tools is None:
        from app.agents.research_agent.tools import default_research_tools

        tools = default_research_tools()

    return create_react_agent(
        model=model,
        tools=tools,
        prompt=prompt or RESEARCH_AGENT_PROMPT,
        name=AGENT_NAME,
    )
