"""Supervisor Agent — điều phối các agent con dưới dạng TOOLS (Supervisor as Tool)."""

from __future__ import annotations

from typing import List, Optional
from langgraph.prebuilt import create_react_agent

from app.agents.supervisor.prompts import SUPERVISOR_PROMPT_TEMPLATE
from app.agents.supervisor.tools import SUPERVISOR_TOOLS

SUPERVISOR_NAME = "supervisor"


def build_supervisor(
    model=None,
    tools: Optional[List] = None,
    prompt: Optional[str] = None,
    sub_agent_model=None,
    output_mode: str = "full_history",
):
    """Trả về Supervisor ReAct Agent."""
    if model is None:
        from app.core.llm import get_llm
        model = get_llm("supervisor")

    if tools is None:
        tools = SUPERVISOR_TOOLS

    if prompt is None:
        catalog_desc = (
            "- research_tool: Useful for searching scientific papers, arXiv, Wikipedia.\n"
            "- vision_tool: Useful for image description and object counting."
        )
        prompt = SUPERVISOR_PROMPT_TEMPLATE.format(agent_catalog=catalog_desc)

    return create_react_agent(
        model=model,
        tools=tools,
        prompt=prompt,
    )