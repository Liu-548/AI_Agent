"""Supervisor Agent — điều phối các agent con dưới dạng TOOLS (Supervisor as Tool)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from app.agents import agent_catalog
from app.agents.supervisor.budget import CALL_BUDGET_CONFIG_KEY, CallBudget
from app.agents.supervisor.prompts import SUPERVISOR_PROMPT_TEMPLATE
from app.agents.supervisor.tools import SUPERVISOR_TOOLS, make_sub_agent_tool

SUPERVISOR_NAME = "supervisor"


def _wrap_agent_to_tool(agent):
    """Bọc một LangGraph CompiledGraph hoặc object agent thành một LangChain Tool hợp lệ."""
    if isinstance(agent, BaseTool):
        return agent

    agent_name = getattr(agent, "name", None) or getattr(agent, "__name__", "sub_agent")
    return make_sub_agent_tool(agent, tool_name=f"transfer_to_{agent_name}")


class _InvocationBudgetGraph:
    """Bổ sung ngân sách riêng cho mỗi lần chạy graph mà không đổi API graph."""

    def __init__(self, graph: Any):
        self._graph = graph

    @staticmethod
    def _config(config: dict | None) -> dict:
        run_config = dict(config or {})
        configurable = dict(run_config.get("configurable") or {})
        configurable[CALL_BUDGET_CONFIG_KEY] = CallBudget.from_settings()
        run_config["configurable"] = configurable
        return run_config

    def invoke(self, input: Any, config: dict | None = None, **kwargs: Any) -> Any:
        return self._graph.invoke(input, config=self._config(config), **kwargs)

    async def ainvoke(self, input: Any, config: dict | None = None, **kwargs: Any) -> Any:
        return await self._graph.ainvoke(input, config=self._config(config), **kwargs)

    def stream(
        self, input: Any, config: dict | None = None, **kwargs: Any
    ) -> Iterator[Any]:
        yield from self._graph.stream(input, config=self._config(config), **kwargs)

    async def astream(
        self, input: Any, config: dict | None = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        async for item in self._graph.astream(input, config=self._config(config), **kwargs):
            yield item

    def __getattr__(self, name: str) -> Any:
        return getattr(self._graph, name)


def build_supervisor(
    model=None,
    agents: list | None = None,   # Hỗ trợ alias cho các test contract cũ
    tools: list | None = None,
    prompt: str | None = None,
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

    graph = create_react_agent(
        model=model,
        tools=tools,
        prompt=prompt,
    )
    return _InvocationBudgetGraph(graph)