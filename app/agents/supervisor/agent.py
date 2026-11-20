"""Supervisor Agent — điều phối các agent con dưới dạng TOOLS (Supervisor as Tool)."""

from __future__ import annotations

from typing import Any, List, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import create_react_agent

from app.agents import agent_catalog
from app.agents.supervisor.budget import CALL_BUDGET_CONFIG_KEY, CallBudget
from app.agents.supervisor.prompts import SUPERVISOR_PROMPT_TEMPLATE
from app.agents.supervisor.tools import SUPERVISOR_TOOLS, _chay_agent_con

SUPERVISOR_NAME = "supervisor"


def _wrap_agent_to_tool(agent):
    """Bọc một LangGraph CompiledGraph hoặc object agent thành một LangChain Tool hợp lệ."""
    # Nếu đã là BaseTool hợp lệ thì giữ nguyên
    if isinstance(agent, BaseTool):
        return agent

    # Lấy tên agent
    agent_name = getattr(agent, "name", None) or getattr(agent, "__name__", "sub_agent")
    
    @tool(f"transfer_to_{agent_name}")
    def sub_agent_tool(query: str, config: RunnableConfig = None) -> str:
        """Chuyển giao công việc cho agent con xử lý."""
        # Cùng một đường với tool mặc định: ngân sách, config của lượt cha, retry, lỗi có cấu trúc.
        return _chay_agent_con(agent, query, config, agent_name=agent_name)[0]

    return sub_agent_tool


class _InvocationBudgetGraph:
    """Bọc graph supervisor: MỖI lượt invoke/stream nhận một CallBudget MỚI.

    Ngân sách nằm trong config["configurable"] của lượt đó (không phải biến module), nên
    hai yêu cầu chạy đồng thời không đếm chung. Config của người gọi được sao chép, không
    sửa tại chỗ. Mọi thuộc tính khác (get_graph, name, ...) chuyển thẳng cho graph gốc.
    """

    def __init__(self, graph: Any):
        self._graph = graph

    @staticmethod
    def _config(config: Optional[dict]) -> dict:
        moi = dict(config or {})
        configurable = dict(moi.get("configurable") or {})
        configurable[CALL_BUDGET_CONFIG_KEY] = CallBudget.from_settings()
        moi["configurable"] = configurable
        return moi

    def invoke(self, input: Any, config: Optional[dict] = None, **kwargs):
        return self._graph.invoke(input, self._config(config), **kwargs)

    async def ainvoke(self, input: Any, config: Optional[dict] = None, **kwargs):
        return await self._graph.ainvoke(input, self._config(config), **kwargs)

    def stream(self, input: Any, config: Optional[dict] = None, **kwargs):
        return self._graph.stream(input, self._config(config), **kwargs)

    def astream(self, input: Any, config: Optional[dict] = None, **kwargs):
        return self._graph.astream(input, self._config(config), **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._graph, name)


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

    return _InvocationBudgetGraph(
        create_react_agent(
            model=model,
            tools=tools,
            prompt=prompt,
        )
    )