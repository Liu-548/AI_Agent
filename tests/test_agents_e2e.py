"""Test end-to-end đồ thị agent bằng model giả — không cần OPENAI_API_KEY.

Đây là bộ test quan trọng nhất khi merge: nó chứng minh supervisor route đúng tên
agent và agent con gọi đúng tên tool.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agents.research_agent import AGENT_NAME as RESEARCH_AGENT_NAME, build_research_agent
from app.agents.supervisor import build_supervisor
from app.agents.vision_agent import AGENT_NAME as VISION_AGENT_NAME, build_vision_agent
from tests.fakes import FakeToolCallingModel, tool_call


class _Input(BaseModel):
    text: str = Field(description="query")


def _tool_gia(name: str, ket_qua: str):
    return StructuredTool.from_function(
        func=lambda text: ket_qua,
        name=name,
        description=f"Fake tool {name} used only in tests, returns a canned answer.",
        args_schema=_Input,
    )


def _noi_dung_cuoi(state) -> str:
    return state["messages"][-1].content


def _ten_tool_da_goi(state) -> set:
    ten = set()
    for m in state["messages"]:
        for tc in getattr(m, "tool_calls", None) or []:
            ten.add(tc["name"] if isinstance(tc, dict) else tc.name)
    return ten


# --------------------------- Research Agent -------------------------------- #
def test_research_agent_goi_tool_roi_tra_loi():
    model = FakeToolCallingModel(
        responses=[
            AIMessage(content="", tool_calls=[tool_call("arxiv_search", {"text": "RoPE"})]),
            AIMessage(content="Found 2 papers about RoPE."),
        ]
    )
    agent = build_research_agent(
        model=model, tools=[_tool_gia("arxiv_search", "Paper A; Paper B")]
    )
    out = agent.invoke({"messages": [{"role": "user", "content": "rotary positional encoding"}]})
    assert _noi_dung_cuoi(out) == "Found 2 papers about RoPE."
    assert any(getattr(m, "content", "") == "Paper A; Paper B" for m in out["messages"])


def test_research_agent_co_dung_ten_trong_graph():
    agent = build_research_agent(model=FakeToolCallingModel(responses=[AIMessage(content="ok")]), tools=[])
    assert agent.name == RESEARCH_AGENT_NAME == "research_agent"


# --------------------------- Vision Agent ---------------------------------- #
def test_vision_agent_goi_ca_hai_tool_trong_mot_luot():
    ket_qua_dem = json.dumps({"counting": {"dog": 5}, "detections": []})
    model = FakeToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    tool_call("detect_and_count_objects", {"text": "./dogs.jpg"}, "c1"),
                    tool_call("image_describer", {"text": "./dogs.jpg"}, "c2"),
                ],
            ),
            AIMessage(content="5 dogs, brindle-and-white coat."),
        ]
    )
    agent = build_vision_agent(
        model=model,
        tools=[
            _tool_gia("detect_and_count_objects", ket_qua_dem),
            _tool_gia("image_describer", "A brindle-and-white dog."),
        ],
    )
    out = agent.invoke({"messages": [{"role": "user", "content": "how many dogs? ./dogs.jpg"}]})
    assert _noi_dung_cuoi(out) == "5 dogs, brindle-and-white coat."


def test_vision_agent_co_dung_ten_trong_graph():
    agent = build_vision_agent(model=FakeToolCallingModel(responses=[AIMessage(content="ok")]), tools=[])
    assert agent.name == VISION_AGENT_NAME == "vision_agent"


# --------------------------- Supervisor ------------------------------------ #
def _supervisor_gia(kich_ban_supervisor, kich_ban_agent):
    """Dựng supervisor với model giả cho cả supervisor lẫn 2 agent con."""
    research = build_research_agent(
        model=FakeToolCallingModel(responses=kich_ban_agent),
        tools=[_tool_gia("arxiv_search", "Paper A")],
    )
    vision = build_vision_agent(
        model=FakeToolCallingModel(responses=kich_ban_agent),
        tools=[_tool_gia("image_describer", "A red square")],
    )
    return build_supervisor(
        model=FakeToolCallingModel(responses=kich_ban_supervisor),
        agents=[research, vision],
    )


def test_supervisor_route_sang_research_agent():
    graph = _supervisor_gia(
        kich_ban_supervisor=[
            AIMessage(content="", tool_calls=[tool_call("transfer_to_research_agent", {})]),
            AIMessage(content="Đây là các bài báo liên quan."),
        ],
        kich_ban_agent=[AIMessage(content="Paper A is relevant.")],
    )
    out = graph.invoke({"messages": [{"role": "user", "content": "tìm bài báo về RoPE"}]})
    assert _noi_dung_cuoi(out) == "Đây là các bài báo liên quan."
    assert "transfer_to_research_agent" in _ten_tool_da_goi(out)


def test_supervisor_route_lan_luot_hai_agent():
    graph = _supervisor_gia(
        kich_ban_supervisor=[
            AIMessage(content="", tool_calls=[tool_call("transfer_to_vision_agent", {}, "s1")]),
            AIMessage(content="", tool_calls=[tool_call("transfer_to_research_agent", {}, "s2")]),
            AIMessage(content="Chó lông vằn nâu-trắng, giống American Staffordshire Terrier."),
        ],
        kich_ban_agent=[AIMessage(content="ket qua agent con")],
    )
    out = graph.invoke(
        {"messages": [{"role": "user", "content": "chó trong ảnh ./dogs.jpg màu gì, giống gì?"}]}
    )
    assert "American Staffordshire Terrier" in _noi_dung_cuoi(out)


def test_ten_handoff_tool_khop_ten_agent():
    """transfer_to_<AGENT_NAME> là hợp đồng ngầm giữa supervisor và agent con."""
    model = FakeToolCallingModel(responses=[AIMessage(content="xong")])
    graph = build_supervisor(
        model=model,
        agents=[
            build_research_agent(model=FakeToolCallingModel(responses=[AIMessage(content="a")]), tools=[]),
            build_vision_agent(model=FakeToolCallingModel(responses=[AIMessage(content="b")]), tools=[]),
        ],
    )
    graph.invoke({"messages": [{"role": "user", "content": "hi"}]})
    assert {"transfer_to_research_agent", "transfer_to_vision_agent"}.issubset(
        set(model.bound_tool_names)
    )
