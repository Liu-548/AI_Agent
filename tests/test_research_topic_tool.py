"""Test khung agent chủ đề: registry, topic tool, TopicBudget, grounding tầng 1. OFFLINE.

Agent chủ đề trong test là một ReAct agent thật (langgraph) nhưng dùng model giả
được lập kịch bản, và các nguồn học thuật được thay bằng hàm giả.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from langgraph.prebuilt import create_react_agent

from app.agents.research_agent import paper_tools
from app.agents.research_agent.profiles import PROFILES
from app.agents.research_agent.topics.budget import check_topic_budget
from app.agents.research_agent.topics.registry import TopicSpec, build_topic_tools
from app.agents.research_agent.topics.topic_tool import make_topic_tool
from tests.fakes import FakeToolCallingModel, tool_call
from tests.test_research_paper_tools import ROFORMER_ARXIV, _gia_nguon

PROFILE = PROFILES["standard"]
CAU_DUNG = "RoPE rotates query and key vectors to encode position [http://arxiv.org/abs/2104.09864v5]."
# Key GIẢ dựng lúc chạy (không viết literal để không giống key thật trong source).
KEY_GIA = "gsk" + "_" + "X" * 16
CAU_BIA = "A later paper extends it to very long contexts [http://arxiv.org/abs/2305.13052v1]."


def demo_spec(name="demo_agent"):
    """Một chủ đề thử nghiệm: agent ReAct + ba tool lá của scholar."""

    def build_demo_agent(model=None, tools=None, prompt=None):
        return create_react_agent(model=model, tools=tools, prompt=prompt or "demo", name=name)

    return TopicSpec(
        name=name,
        description="Use for demos and tests only. Do NOT use in production code paths.",
        build=build_demo_agent,
        default_tools=lambda budget, profile: paper_tools.make_paper_tools(budget, profile),
    )


def kich_ban_tim_roi_tra_loi(*cau_tra_loi):
    """Model giả: gọi paper_search một lần rồi trả câu trả lời."""
    return FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[tool_call("paper_search", {"text": "rotary embedding"})]),
        AIMessage(content="\n".join(cau_tra_loi)),
    ])


def goi(tool, text="papers on rotary embedding", call_id="c1"):
    """Gọi tool bằng ToolCall để nhận về ToolMessage (có artifact)."""
    return tool.invoke({"name": tool.name, "args": {"text": text}, "id": call_id, "type": "tool_call"})


@pytest.fixture
def nguon_gia(monkeypatch):
    _gia_nguon(monkeypatch, arxiv=[ROFORMER_ARXIV], openalex=[], semantic_scholar=[])


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def test_build_topic_tools_moi_spec_mot_tool():
    tools = build_topic_tools(PROFILE, specs=(demo_spec("a_agent"), demo_spec("b_agent")))
    assert [t.name for t in tools] == ["a_agent", "b_agent"]
    assert all(t.return_direct is False for t in tools)


def test_topic_tool_llm_chi_thay_tham_so_text():
    (tool,) = build_topic_tools(PROFILE, specs=(demo_spec(),))
    # state và tool_call_id được tiêm, phải bị ẩn khỏi schema mà LLM thấy.
    assert set(tool.tool_call_schema.model_json_schema()["properties"]) == {"text"}


# --------------------------------------------------------------------------- #
# Topic tool: ca đúng + grounding tầng 1
# --------------------------------------------------------------------------- #
def test_topic_tool_ok_tra_content_json_gon_va_artifact_day_du(nguon_gia):
    tool = make_topic_tool(demo_spec(), profile=PROFILE, model=kich_ban_tim_roi_tra_loi(CAU_DUNG))
    msg = goi(tool)
    assert isinstance(msg, ToolMessage) and isinstance(msg.content, str)
    content = json.loads(msg.content)
    assert content["status"] == "ok" and content["topic"] == "demo_agent"
    assert content["labels"] == ["[http://arxiv.org/abs/2104.09864v5]"]
    assert "evidence_text" not in content  # bằng chứng ở artifact, KHÔNG vào context của lead
    art = msg.artifact
    assert "Label: [http://arxiv.org/abs/2104.09864v5]" in art["evidence_text"]
    assert [s["kind"] for s in art["trace"]] == ["tool_call", "tool_result", "final"]
    assert art["trace"][0]["tool"] == "paper_search" and art["trace"][1]["error_code"] is None
    assert art["usage"]["llm_calls"] == 2 and art["usage"]["tool_calls"] == 1


def test_grounding_tang_1_xoa_cau_ma_arxiv_bia(nguon_gia):
    tool = make_topic_tool(demo_spec(), profile=PROFILE, model=kich_ban_tim_roi_tra_loi(CAU_DUNG, CAU_BIA))
    msg = goi(tool)
    content = json.loads(msg.content)
    assert content["answer"] == CAU_DUNG and content["grounding"]["removed"] == 1
    assert CAU_BIA in msg.artifact["answer_raw"] and CAU_BIA not in msg.artifact["answer_final"]
    assert msg.artifact["grounding_report"]["violations"][0]["code"] == "MA_BIA"


def test_grounding_tang_1_cau_khong_nhan_duoc_giu_va_dem(nguon_gia):
    khong_nhan = "This technique is widely adopted in modern language models today."
    tool = make_topic_tool(demo_spec(), profile=PROFILE, model=kich_ban_tim_roi_tra_loi(CAU_DUNG, khong_nhan))
    content = json.loads(goi(tool).content)
    assert khong_nhan in content["answer"]
    assert content["grounding"] == {"removed": 0, "missing_source": 1}


def test_grounding_tang_1_moi_cau_deu_bia_thi_no_data(nguon_gia):
    tool = make_topic_tool(demo_spec(), profile=PROFILE, model=kich_ban_tim_roi_tra_loi(CAU_BIA))
    content = json.loads(goi(tool).content)
    assert content["status"] == "no_data" and content["answer"].startswith("KHONG DU DU LIEU:")


def test_agent_tra_khong_du_du_lieu_la_no_data(nguon_gia):
    tool = make_topic_tool(demo_spec(), profile=PROFILE, model=kich_ban_tim_roi_tra_loi("KHONG DU DU LIEU: no relevant paper"))
    assert json.loads(goi(tool).content)["status"] == "no_data"


# --------------------------------------------------------------------------- #
# Lỗi: tool không bao giờ raise
# --------------------------------------------------------------------------- #
def test_text_rong_la_empty_query():
    (tool,) = build_topic_tools(PROFILE, model=FakeToolCallingModel(), specs=(demo_spec(),))
    assert goi(tool, text="  ").content.startswith("ERROR: EMPTY_QUERY")


class _Nem(FakeToolCallingModel):
    """Model giả ném exception thay vì trả lời."""

    loi: Exception = RuntimeError("boom")

    def _generate(self, *a, **kw):
        raise self.loi


@pytest.mark.parametrize(
    "loi,ma",
    [
        (RuntimeError(f"boom with key {KEY_GIA}"), "TOPIC_AGENT_FAILED"),
        (GraphRecursionError("too deep"), "TOPIC_RECURSION_LIMIT"),
        (RuntimeError("Error code: 429 - rate limit reached"), "LLM_RATE_LIMITED"),
    ],
)
def test_loi_ben_trong_thanh_chuoi_error(loi, ma):
    tool = make_topic_tool(demo_spec(), profile=PROFILE, model=_Nem(loi=loi))
    msg = goi(tool)
    assert msg.content.startswith(f"ERROR: {ma} |")
    assert KEY_GIA not in msg.content  # key không lọt ra ngoài
    assert msg.artifact["status"] == "error"


def test_thieu_model_role_research_topic_bao_loi_khong_raise():
    # model=None -> agent tự lấy get_llm("research_topic"), mà MODEL_RESEARCH_TOPIC đang trống.
    from app.agents.research_agent.topics import registry  # noqa: F401
    from app.core.llm import get_llm

    get_llm.cache_clear()

    def build(model=None, tools=None, prompt=None):
        from app.core.llm import get_llm as lay

        return create_react_agent(model=lay("research_topic"), tools=tools, prompt="x", name="demo_agent")

    spec = replace(demo_spec(), build=build)
    msg = goi(make_topic_tool(spec, profile=PROFILE))
    assert msg.content.startswith("ERROR: TOPIC_AGENT_FAILED |")


# --------------------------------------------------------------------------- #
# TopicBudget
# --------------------------------------------------------------------------- #
def _lich_su(*cuoc_goi, moi_nguoi_dung=True):
    """Dựng lịch sử của lead: mỗi cuộc gọi (tên, text, đã_trả_lời_bằng) -> AIMessage + ToolMessage."""
    msgs = [HumanMessage(content="q")] if moi_nguoi_dung else []
    for i, (ten, text, tra_loi) in enumerate(cuoc_goi):
        msgs.append(AIMessage(content="", tool_calls=[tool_call(ten, {"text": text}, f"id{i}")]))
        if tra_loi is not None:
            msgs.append(ToolMessage(content=tra_loi, tool_call_id=f"id{i}", name=ten))
    return msgs


def test_topic_budget_lan_thu_ba_bi_tu_choi():
    ds = ["a_agent", "b_agent"]
    lich_su = _lich_su(("a_agent", "one", "{}"), ("b_agent", "two", "{}"))
    loi = check_topic_budget(lich_su, ds, "a_agent", "three", PROFILE.max_topic_calls)
    assert loi.startswith("ERROR: TOPIC_BUDGET_EXCEEDED")
    assert check_topic_budget(lich_su[:2], ds, "a_agent", "three", PROFILE.max_topic_calls) is None


def test_topic_budget_goi_trung_bi_tu_choi_va_khong_an_luot():
    ds = ["a_agent", "b_agent"]
    lich_su = _lich_su(("a_agent", "One  Thing", "{}"))
    assert check_topic_budget(lich_su, ds, "a_agent", "one thing", 2).startswith("ERROR: TOPIC_DUPLICATE_CALL")
    # Lần gọi trùng đã bị từ chối không được tính vào ngân sách của lần sau.
    lich_su += _lich_su(("a_agent", "one thing", "ERROR: TOPIC_DUPLICATE_CALL | x"), moi_nguoi_dung=False)
    assert check_topic_budget(lich_su, ds, "b_agent", "other", 2) is None


def test_topic_budget_dem_lai_khi_co_human_message_moi():
    ds = ["a_agent"]
    lich_su = _lich_su(("a_agent", "one", "{}"), ("a_agent", "two", "{}"))
    assert check_topic_budget(lich_su, ds, "a_agent", "three", 2) is not None
    lich_su.append(HumanMessage(content="cau hoi moi"))
    assert check_topic_budget(lich_su, ds, "a_agent", "three", 2) is None


def test_topic_budget_hai_lan_goi_cung_mot_luot_chay_song_song():
    """ToolNode chạy các tool_call của cùng một AIMessage song song: lần gọi thứ N chỉ thấy N-1 lần trước."""
    ds = ["a_agent", "b_agent"]
    ai = AIMessage(content="", tool_calls=[
        tool_call("a_agent", {"text": "x"}, "p1"), tool_call("a_agent", {"text": "y"}, "p2"),
        tool_call("b_agent", {"text": "z"}, "p3"),
    ])
    lich_su = [HumanMessage(content="q"), ai]
    assert check_topic_budget(lich_su, ds, "a_agent", "x", 2, tool_call_id="p1") is None
    assert check_topic_budget(lich_su, ds, "a_agent", "y", 2, tool_call_id="p2") is None
    assert check_topic_budget(lich_su, ds, "b_agent", "z", 2, tool_call_id="p3").startswith("ERROR: TOPIC_BUDGET_EXCEEDED")


def test_topic_budget_qua_lead_that_lan_thu_ba_bi_tu_choi(nguon_gia):
    """Đường đầy đủ: lead ReAct gọi 3 lần, state được tiêm vào tool qua InjectedState."""
    tools = build_topic_tools(
        PROFILE, model=kich_ban_tim_roi_tra_loi(CAU_DUNG), specs=(demo_spec("a_agent"), demo_spec("b_agent"))
    )
    lead_model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[tool_call("a_agent", {"text": "first"}, "l1")]),
        AIMessage(content="", tool_calls=[tool_call("a_agent", {"text": "first"}, "l2")]),   # trùng
        AIMessage(content="", tool_calls=[tool_call("b_agent", {"text": "second"}, "l3")]),
        AIMessage(content="", tool_calls=[tool_call("b_agent", {"text": "third"}, "l4")]),   # quá trần 2
        AIMessage(content="done"),
    ])
    lead = create_react_agent(model=lead_model, tools=tools, prompt="lead", name="research_agent")
    ket_qua = lead.invoke({"messages": [HumanMessage(content="q")]}, config={"recursion_limit": 30})
    theo_id = {m.tool_call_id: m for m in ket_qua["messages"] if isinstance(m, ToolMessage)}
    assert json.loads(theo_id["l1"].content)["status"] in ("ok", "no_data")
    assert theo_id["l2"].content.startswith("ERROR: TOPIC_DUPLICATE_CALL")
    assert not theo_id["l3"].content.startswith("ERROR")
    assert theo_id["l4"].content.startswith("ERROR: TOPIC_BUDGET_EXCEEDED")
    assert re.search(r"TOPIC_BUDGET_EXCEEDED", theo_id["l4"].content)
