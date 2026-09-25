"""Test hai agent chủ đề thật (scholar_agent, explainer_agent) và registry TOPIC_SPECS. OFFLINE."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from app.agents.research_agent.prompts import GROUNDING_RULES
from app.agents.research_agent.profiles import PROFILES
from app.agents.research_agent.tools import SearchBudget, SearchInput
from app.agents.research_agent.topics import TOPIC_SPECS, make_topic_tool
from app.agents.research_agent.topics.explainer_agent.prompts import EXPLAINER_AGENT_PROMPT
from app.agents.research_agent.topics.scholar_agent.prompts import SCHOLAR_AGENT_PROMPT
from tests.fakes import FakeToolCallingModel, tool_call
from tests.test_research_paper_tools import ROFORMER_ARXIV, _gia_nguon

TOPICS_DIR = Path(__file__).resolve().parent.parent / "app" / "agents" / "research_agent" / "topics"
PROFILE = PROFILES["standard"]
SPEC = {s.name: s for s in TOPIC_SPECS}


def goi(tool, text):
    return tool.invoke({"name": tool.name, "args": {"text": text}, "id": "c1", "type": "tool_call"})


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def test_registry_co_dung_hai_chu_de():
    assert [s.name for s in TOPIC_SPECS] == ["scholar_agent", "explainer_agent"]


@pytest.mark.parametrize("spec", TOPIC_SPECS, ids=lambda s: s.name)
def test_topic_spec_hop_le(spec):
    assert re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)*_agent", spec.name)  # snake_case + hậu tố _agent
    assert (TOPICS_DIR / spec.name).is_dir()                                # tên thư mục = tên chủ đề
    assert spec.description.isascii() and len(spec.description) >= 20
    assert "Do NOT" in spec.description                                     # nói rõ KHI NÀO KHÔNG dùng
    assert spec.build.__name__ == f"build_{spec.name}"


def test_ten_chu_de_khong_trung_nhau():
    ten = [s.name for s in TOPIC_SPECS]
    assert len(ten) == len(set(ten))


@pytest.mark.parametrize("spec", TOPIC_SPECS, ids=lambda s: s.name)
def test_moi_spec_dung_duoc_voi_model_gia(spec):
    tools = spec.default_tools(SearchBudget(max_calls=3), PROFILE)
    agent = spec.build(model=FakeToolCallingModel(), tools=tools)
    assert agent.name == spec.name  # name= của create_react_agent = TOPIC_NAME


def test_tool_la_cua_tung_chu_de():
    ten = lambda name: [t.name for t in SPEC[name].default_tools(SearchBudget(max_calls=3), PROFILE)]  # noqa: E731
    assert ten("scholar_agent") == ["paper_search", "pubmed_search", "doi_lookup"]
    # explainer TÁI DÙNG tool cũ, cùng tên.
    assert ten("explainer_agent") == ["wikipedia_search", "arxiv_search"]


def test_tool_la_dung_chung_mot_so_luot():
    tools = SPEC["explainer_agent"].default_tools(SearchBudget(max_calls=3), PROFILE)
    assert tools[0].metadata["search_budget"] is tools[1].metadata["search_budget"]


def test_prompt_chua_khoi_grounding_va_quy_tac_chinh():
    for p in (SCHOLAR_AGENT_PROMPT, EXPLAINER_AGENT_PROMPT):
        assert GROUNDING_RULES in p and p.isascii()
        assert "200 words" in p and "KHONG DU DU LIEU" in p
    assert "paper_search" in SCHOLAR_AGENT_PROMPT and "pubmed_search" in SCHOLAR_AGENT_PROMPT
    assert "Last updated" in SCHOLAR_AGENT_PROMPT and "Published" in SCHOLAR_AGENT_PROMPT
    assert "wikipedia_search" in EXPLAINER_AGENT_PROMPT and "arxiv_search" in EXPLAINER_AGENT_PROMPT


# --------------------------------------------------------------------------- #
# Chạy thử từng agent với model giả
# --------------------------------------------------------------------------- #
def test_scholar_agent_e2e_voi_nguon_gia(monkeypatch):
    _gia_nguon(monkeypatch, arxiv=[ROFORMER_ARXIV], openalex=[], semantic_scholar=[])
    model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[tool_call("paper_search", {"text": "rotary position embedding"})]),
        AIMessage(content="RoFormer (2021) introduces rotary embeddings [http://arxiv.org/abs/2104.09864v5]."),
    ])
    msg = goi(make_topic_tool(SPEC["scholar_agent"], profile=PROFILE, model=model), "recent papers on rotary embedding")
    content = json.loads(msg.content)
    assert content["status"] == "ok" and content["topic"] == "scholar_agent"
    assert msg.artifact["trace"][0]["tool"] == "paper_search"


def test_explainer_agent_e2e_nhan_wikipedia_qua_grounding():
    wiki = StructuredTool.from_function(
        func=lambda text: "Page: Self-attention\nSummary: Self-attention relates positions of a sequence.",
        name="wikipedia_search", description="Fake wikipedia used only by this test.", args_schema=SearchInput,
    )
    spec = replace(SPEC["explainer_agent"], default_tools=lambda budget, profile: [wiki])
    model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[tool_call("wikipedia_search", {"text": "self-attention"})]),
        AIMessage(content=(
            "Self-attention relates the positions of a sequence to each other [wikipedia: Self-attention].\n"
            "It was invented in 1850 by a famous physicist [wikipedia: Made Up Page]."
        )),
    ])
    content = json.loads(goi(make_topic_tool(spec, profile=PROFILE, model=model), "how does self-attention work").content)
    assert content["status"] == "ok" and content["labels"] == ["[wikipedia: Self-attention]"]
    assert content["grounding"]["removed"] == 1  # nhãn wikipedia bịa bị xoá câu
