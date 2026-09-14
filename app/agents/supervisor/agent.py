"""Supervisor Agent — điều phối các agent con dưới dạng TOOLS (Supervisor as Tool)."""

from __future__ import annotations

from typing import List, Optional
from langchain_core.tools import tool, BaseTool
from langgraph.prebuilt import create_react_agent

from app.agents import agent_catalog
from app.agents.supervisor.prompts import SUPERVISOR_PROMPT_TEMPLATE
from app.agents.supervisor.tools import SUPERVISOR_TOOLS

SUPERVISOR_NAME = "supervisor"


def _wrap_agent_to_tool(agent):
    """Bọc một LangGraph CompiledGraph hoặc object agent thành một LangChain Tool hợp lệ."""
    # Nếu đã là BaseTool hợp lệ thì giữ nguyên
    if isinstance(agent, BaseTool):
        return agent

    # Lấy tên agent
    agent_name = getattr(agent, "name", None) or getattr(agent, "__name__", "sub_agent")
    
    @tool(f"transfer_to_{agent_name}")
    def sub_agent_tool(query: str) -> str:
        """Chuyển giao công việc cho agent con xử lý."""
        if hasattr(agent, "invoke"):
            res = agent.invoke({"messages": [("user", query)]})
            if isinstance(res, dict) and "messages" in res:
                return res["messages"][-1].content
            return str(res)
        return f"Agent {agent_name} executed."

    return sub_agent_tool


def build_supervisor(
    model=None,
    agents: Optional[List] = None,   # Hỗ trợ alias cho các test contract cũ
    tools: Optional[List] = None,
    prompt: Optional[str] = None,
    sub_agent_model=None,           # Giữ tham số cho mock model trong pytest
    output_mode: str = "full_history",
):
    """Trả về CompiledStateGraph của Supervisor chạy theo mô hình Tool-calling (ReAct)."""
    if model is None:
        from app.core.llm import get_llm
        model = get_llm("supervisor")

    # Xử lý danh sách tools/agents truyền vào
    if tools is None:
        if agents is not None:
            tools = [_wrap_agent_to_tool(a) for a in agents]
        else:
            tools = SUPERVISOR_TOOLS
    else:
        # Đảm bảo tất cả phần tử trong tools đều là Tool chuẩn
        tools = [_wrap_agent_to_tool(t) for t in tools]

    if prompt is None:
        prompt = SUPERVISOR_PROMPT_TEMPLATE.format(agent_catalog=agent_catalog())

    return create_react_agent(
        model=model,
        tools=tools,
        prompt=prompt,
    )