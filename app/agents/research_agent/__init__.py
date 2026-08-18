"""Gói Research Agent — TOÀN BỘ code của agent này nằm trong thư mục này.

    agent.py    định nghĩa agent + hợp đồng (AGENT_NAME, AGENT_DESCRIPTION, factory)
    tools.py    arxiv_search, wikipedia_search
    prompts.py  prompt của agent

Chủ sở hữu: người phụ trách Research Agent.
"""

from app.agents.research_agent.agent import (
    AGENT_DESCRIPTION,
    AGENT_NAME,
    build_research_agent,
)
from app.agents.research_agent.tools import (
    default_research_tools,
    make_arxiv_tool,
    make_wikipedia_tool,
)

__all__ = [
    "AGENT_NAME",
    "AGENT_DESCRIPTION",
    "build_research_agent",
    "default_research_tools",
    "make_arxiv_tool",
    "make_wikipedia_tool",
]
