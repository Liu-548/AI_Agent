"""news_agent (Google News RSS) + lớp đưa kết quả agent con lên web UI. OFFLINE, không gọi LLM."""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.research_agent.tools import SearchBudget
from app.agents.research_agent.topics.news_agent import tools as news
from app.core.grounding import kiem_tra_grounding

XML = (Path(__file__).parent / "fixtures" / "research" / "google_news.xml").read_bytes()


def test_doc_rss_bo_hau_to_ten_bao_va_bo_bai_thieu_link():
    bai = news.doc_rss(XML, limit=10)
    assert [b["source"] for b in bai] == ["Reuters", "economist.com"]
    assert bai[0]["title"] == "Musk proposes peer review for frontier AI models in Economist interview"
    assert bai[0]["date"] == "2026-07-23"
    assert bai[0]["id"] == news.ma_tin(bai[0]["url"]) and bai[0]["id"].startswith("gn-")
    assert len(news.doc_rss(XML, limit=1)) == 1


def test_nhan_tin_tuc_qua_duoc_grounding_con_nhan_bia_thi_khong():
    bai = news.doc_rss(XML, limit=10)
    bang_chung = news.dinh_dang(bai)
    that = f"Musk proposed peer review for frontier AI models [news: {bai[0]['id']}]."
    bia = "Musk announced a new phone in an interview with Reuters [news: gn-deadbeef]."
    assert kiem_tra_grounding(that, [bang_chung]) == []
    assert kiem_tra_grounding(bia, [bang_chung])


def test_news_search_khong_raise_khi_mat_mang(monkeypatch):
    import requests

    def hong(*a, **k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", hong)
    tool = news.make_news_tool(SearchBudget(max_calls=3))
    assert tool.invoke({"text": "Elon Musk interview"}).startswith("ERROR: NEWS_UNAVAILABLE")
    assert tool.invoke({"text": "  "}).startswith("ERROR: EMPTY_QUERY")


def test_phien_ban_theo_ngon_ngu():
    assert news._phien_ban("Elon Musk interview")["gl"] == "US"
    assert news._phien_ban("bão số 5 miền Trung")["gl"] == "VN"


def test_api_doc_trace_supervisor_as_tool_va_link_tin():
    from app import api

    bai = news.doc_rss(XML, limit=10)
    ma = bai[0]["id"]
    tra_loi = f"Musk đề xuất bình duyệt mô hình AI [1].\n\nNGUỒN\n[1] news: {ma}"
    artifact = {
        "tool_outputs": {"news_search": news.dinh_dang(bai)},
        "topics": [{"topic": "news_agent", "status": "ok", "sub_question": "Elon Musk interview 2026",
                    "usage": {"llm_calls": 2}, "removed": 0}],
        "evidence": news.dinh_dang(bai),
    }
    result = {"messages": [
        HumanMessage(content="phong van Elon Musk 2026"),
        AIMessage(content="", tool_calls=[{"name": "research_agent_tool", "args": {"query": "x"}, "id": "c1"}]),
        ToolMessage(content=tra_loi, name="research_agent_tool", tool_call_id="c1", artifact=artifact),
        AIMessage(content=tra_loi),
    ]}
    used, answers = api._extract_agent_trace(result)
    assert used == ["research_agent"] and answers["research_agent"] == tra_loi
    assert "news_search" in api._collect_tool_outputs(result)

    response: dict = {}
    api._research_extras(result, tra_loi, response)
    assert response["research_trace"][0]["topic"] == "news_agent"
    assert set(response["link_map"]) == {ma}  # chỉ mã được trích
    assert response["link_map"][ma]["source"] == "Reuters"


def test_research_tool_tra_artifact_cho_ui(monkeypatch):
    from app.agents.supervisor import tools as sup

    class _AgentGia:
        @staticmethod
        def invoke(state):
            return {"messages": [
                HumanMessage(content="q"),
                ToolMessage(content="{}", name="news_agent", tool_call_id="t1",
                            artifact={"topic": "news_agent", "status": "ok", "evidence_text": "EV"}),
                AIMessage(content="final"),
            ]}

    monkeypatch.setattr(sup, "get_research_agent", lambda: _AgentGia)
    msg = sup.research_tool.invoke({"type": "tool_call", "name": "research_agent_tool",
                                    "args": {"query": "q"}, "id": "c9"})
    assert msg.content == "final"
    assert msg.artifact["topics"][0]["topic"] == "news_agent"
    assert msg.artifact["evidence"] == "EV"
