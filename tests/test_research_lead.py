"""Test research lead, grounding tầng 2 và công tắc RESEARCH_ARCH. OFFLINE (model giả, nguồn giả)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool

from app.agents.research_agent.agent import AGENT_NAME, build_research_agent
from app.agents.research_agent.lead import (
    GHI_CHU_DA_LUOC_BO,
    GHI_CHU_KHONG_NGUON,
    build_research_lead,
    render_lead_prompt,
)
from app.agents.research_agent.profiles import PROFILES
from app.agents.research_agent.prompts import RESEARCH_AGENT_PROMPT
from app.agents.research_agent.tools import SearchInput
from app.agents.research_agent.topics import TOPIC_SPECS, build_topic_tools
from app.core import config
from tests.fakes import FakeToolCallingModel, tool_call
from tests.test_research_paper_tools import ROFORMER_ARXIV, _gia_nguon

PROFILE = PROFILES["standard"]
SPEC = {s.name: s for s in TOPIC_SPECS}

# sha256 của RESEARCH_AGENT_PROMPT chụp lúc B0 (trước khi làm chế độ topics): prompt của chế độ
# "single" phải GIỮ NGUYÊN TỪNG BYTE.
PROMPT_SINGLE_SHA256 = "5cadb066c18983ca8171a5a34a6d0912555d57c8e1ade021cb3263ecb08d8c41"

WIKI_TEXT = "Page: Self-attention\nSummary: Self-attention relates positions of a sequence to each other."
CAU_WIKI = "Self-attention relates the positions of a sequence to each other [wikipedia: Self-attention]."
CAU_ARXIV = "RoFormer introduces rotary position embeddings [http://arxiv.org/abs/2104.09864v5]."

TRA_LOI_LEAD_DUNG = """TÓM TẮT
Self-attention liên hệ các vị trí của chuỗi với nhau [1]. RoFormer giới thiệu rotary position embeddings [2].

CHI TIẾT
- Self-attention cho phép mỗi vị trí nhìn toàn bộ chuỗi [1].
- RoFormer mã hoá vị trí bằng phép quay [2].

NGUỒN
[1] wikipedia: Self-attention
[2] http://arxiv.org/abs/2104.09864v5"""


def _cac_chu_de_gia():
    """explainer + scholar thật, chỉ thay tool lá bằng bản giả (không mạng)."""
    wiki = StructuredTool.from_function(
        func=lambda text: WIKI_TEXT, name="wikipedia_search",
        description="Fake wikipedia used only by tests.", args_schema=SearchInput,
    )
    return (
        SPEC["scholar_agent"],
        replace(SPEC["explainer_agent"], default_tools=lambda budget, profile: [wiki]),
    )


def _dung_lead(monkeypatch, tra_loi_cuoi, cac_lan_goi=("explainer_agent", "scholar_agent")):
    """Lead giả gọi tuần tự các chủ đề đã cho rồi trả `tra_loi_cuoi`."""
    _gia_nguon(monkeypatch, arxiv=[ROFORMER_ARXIV], openalex=[], semantic_scholar=[])
    kich_ban_chu_de = {
        "explainer_agent": [
            AIMessage(content="", tool_calls=[tool_call("wikipedia_search", {"text": "self-attention"})]),
            AIMessage(content=CAU_WIKI),
        ],
        "scholar_agent": [
            AIMessage(content="", tool_calls=[tool_call("paper_search", {"text": "rotary embedding"})]),
            AIMessage(content=CAU_ARXIV),
        ],
    }
    model_chu_de = FakeToolCallingModel(
        responses=[m for ten in cac_lan_goi for m in kich_ban_chu_de[ten]]
    )
    tools = build_topic_tools(PROFILE, model=model_chu_de, specs=_cac_chu_de_gia())
    lead_model = FakeToolCallingModel(responses=[
        *[AIMessage(content="", tool_calls=[tool_call(ten, {"text": f"sub question {i}"}, f"L{i}")])
          for i, ten in enumerate(cac_lan_goi)],
        AIMessage(content=tra_loi_cuoi),
    ])
    return build_research_lead(model=lead_model, tools=tools, profile=PROFILE)


def chay(lead, cau_hoi="Transformer là gì, và có bài báo nào gần đây?"):
    return lead.invoke({"messages": [HumanMessage(content=cau_hoi)]}, config={"recursion_limit": 40})


def cau_tra_loi_cuoi(ket_qua):
    ai = [m for m in ket_qua["messages"] if isinstance(m, AIMessage)]
    return ai[-1]


# --------------------------------------------------------------------------- #
# Lead e2e
# --------------------------------------------------------------------------- #
def test_lead_hai_chu_de_tuan_tu_va_cau_tra_loi_qua_hook(monkeypatch):
    ket_qua = chay(_dung_lead(monkeypatch, TRA_LOI_LEAD_DUNG))
    tool_msgs = [m for m in ket_qua["messages"] if isinstance(m, ToolMessage)]
    assert [m.name for m in tool_msgs] == ["explainer_agent", "scholar_agent"]  # tuần tự, đúng thứ tự
    assert all(json.loads(m.content)["status"] == "ok" for m in tool_msgs)
    cuoi = cau_tra_loi_cuoi(ket_qua)
    assert cuoi.content == TRA_LOI_LEAD_DUNG  # không có gì bị xoá
    assert cuoi.response_metadata["grounding"]["removed"] == 0  # báo cáo nằm ở response_metadata
    assert "grounding" not in cuoi.additional_kwargs


def test_lead_chen_nhan_bia_thi_cau_bi_xoa_va_co_dong_da_luoc_bo(monkeypatch):
    bia = TRA_LOI_LEAD_DUNG.replace(
        "- RoFormer mã hoá vị trí bằng phép quay [2].",
        "- Một công trình sau đó mở rộng ý tưởng này lên ngữ cảnh rất dài [3].",
    ) + "\n[3] http://arxiv.org/abs/2305.13052v1"
    ket_qua = chay(_dung_lead(monkeypatch, bia))
    cuoi = cau_tra_loi_cuoi(ket_qua)
    assert "2305.13052" not in cuoi.content and "ngữ cảnh rất dài" not in cuoi.content
    assert "Self-attention liên hệ" in cuoi.content and "[2] http://arxiv.org/abs/2104.09864v5" in cuoi.content
    assert cuoi.content.rstrip().endswith(GHI_CHU_DA_LUOC_BO.format(n=1))
    assert cuoi.response_metadata["grounding"]["removed"] == 1
    # Thay thế chứ không nối thêm: chỉ còn MỘT câu trả lời cuối (cùng id).
    assert sum(1 for m in ket_qua["messages"] if isinstance(m, AIMessage) and not m.tool_calls) == 1


def test_lead_tra_loi_khong_qua_tool_thi_co_dong_khong_dua_tren_nguon():
    lead = build_research_lead(
        model=FakeToolCallingModel(responses=[AIMessage(content="TÓM TẮT\nMột câu trả lời từ trí nhớ của mô hình lớn.")]),
        tools=[], profile=PROFILE,
    )
    cuoi = cau_tra_loi_cuoi(chay(lead))
    assert cuoi.content.rstrip().endswith(GHI_CHU_KHONG_NGUON)


@pytest.mark.parametrize("dong", [
    "CAN_LAM_RO: Bạn muốn tìm về Mercury nào — hành tinh, nguyên tố thuỷ ngân, hay ca sĩ?",
    "KHONG DU DU LIEU: không tìm thấy bài báo nào về chủ đề này",
])
def test_dong_dac_biet_di_qua_nguyen_ven(dong):
    lead = build_research_lead(model=FakeToolCallingModel(responses=[AIMessage(content=dong)]), tools=[], profile=PROFILE)
    ket_qua = chay(lead, "Tìm tài liệu về Mercury")
    assert cau_tra_loi_cuoi(ket_qua).content == dong
    assert not any(isinstance(m, ToolMessage) for m in ket_qua["messages"])  # CAN_LAM_RO: không gọi tool


def test_lead_dung_ten_research_agent_va_co_hook():
    lead = build_research_lead(model=FakeToolCallingModel(), tools=[], profile=PROFILE)
    assert lead.name == AGENT_NAME == "research_agent"
    assert "post_model_hook" in lead.nodes


def test_prompt_lead_sinh_tu_registry_khong_hard_code_ten_chu_de():
    p = render_lead_prompt(TOPIC_SPECS, PROFILES["eco"])
    for s in TOPIC_SPECS:
        assert f"- {s.name}: {s.description}" in p
    assert "AT MOST 1 topic call" in p
    assert "CAN_LAM_RO:" in p and "KHONG DU DU LIEU:" in p and "TÓM TẮT" in p
    assert render_lead_prompt((), PROFILES["full"]).count("_agent") == 0  # rỗng registry -> không có tên nào
    assert "AT MOST 3 topic call" in render_lead_prompt((), PROFILES["full"])


# --------------------------------------------------------------------------- #
# Công tắc RESEARCH_ARCH
# --------------------------------------------------------------------------- #
def _ten_tool(agent):
    return set(agent.nodes["tools"].bound.tools_by_name)


def test_mac_dinh_la_agent_cu_voi_tool_cu():
    agent = build_research_agent(model=FakeToolCallingModel())
    assert agent.name == "research_agent"
    assert _ten_tool(agent) == {"arxiv_search", "openalex_search", "wikipedia_search"}
    assert "post_model_hook" not in agent.nodes


def test_research_arch_topics_dung_lead(monkeypatch):
    monkeypatch.setattr(config, "settings", replace(config.settings, research_arch="topics"))
    agent = build_research_agent(model=FakeToolCallingModel())
    assert agent.name == "research_agent"
    assert _ten_tool(agent) == {"scholar_agent", "explainer_agent"}
    assert "post_model_hook" in agent.nodes


def test_research_arch_gia_tri_la_bao_loi_ro(monkeypatch):
    monkeypatch.setattr(config, "settings", replace(config.settings, research_arch="mesh"))
    with pytest.raises(RuntimeError, match="RESEARCH_ARCH"):
        build_research_agent(model=FakeToolCallingModel())


def test_research_agent_prompt_giu_nguyen_tung_byte():
    assert hashlib.sha256(RESEARCH_AGENT_PROMPT.encode("utf-8")).hexdigest() == PROMPT_SINGLE_SHA256
