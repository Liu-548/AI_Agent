"""Supervisor Agent — điều phối các agent con qua cơ chế hand-off của LangGraph.

Lưu ý: supervisor KHÔNG nằm trong AGENT_SPECS. Nó là người điều phối, không phải
agent con được điều phối. Đưa nó vào registry sẽ tạo vòng lặp import và khiến
supervisor tự gọi chính mình.
"""

from __future__ import annotations

from typing import List, Optional

from app.agents import agent_catalog, build_all_agents
from app.agents.supervisor.prompts import SUPERVISOR_PROMPT_TEMPLATE

SUPERVISOR_NAME = "supervisor"


def build_supervisor(
    model=None,
    agents: Optional[List] = None,
    sub_agent_model=None,
    prompt: Optional[str] = None,
    output_mode: str = "full_history",
):
    """Trả về CompiledStateGraph của toàn hệ thống.

    model          : LLM của supervisor (cần tool-calling tốt để route).
    agents         : danh sách agent con đã compile; None -> lấy hết từ registry.
    sub_agent_model: LLM dùng cho agent con khi agents=None (tiện cho test).
    """
    from langgraph_supervisor import create_supervisor

    if model is None:
        from app.core.llm import get_llm

        model = get_llm("supervisor")
    if agents is None:
        agents = build_all_agents(model=sub_agent_model)

    if prompt is None:
        prompt = SUPERVISOR_PROMPT_TEMPLATE.format(agent_catalog=agent_catalog())

    return create_supervisor(
        model=model,
        agents=agents,
        prompt=prompt,
        # Log lại message transfer_back_to_supervisor -> nhìn được toàn bộ đường đi.
        add_handoff_back_messages=True,
        output_mode=output_mode,
    ).compile()
