"""code_agent, travel_agent, culture_agent (Phase 3–5 SPEC §13). OFFLINE: dữ liệu API là dict mẫu, không gọi mạng/LLM."""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage

from app.agents.research_agent.profiles import PROFILES
from app.agents.research_agent.tools import SearchBudget
from app.agents.research_agent.topics import TOPIC_SPECS, make_topic_tool
from app.agents.research_agent.topics.code_agent import tools as code
from app.agents.research_agent.topics.culture_agent import gioi_han_trich_dan
from app.agents.research_agent.topics.culture_agent import tools as culture
from app.agents.research_agent.topics.travel_agent import tools as travel
from app.core.grounding import kiem_tra_grounding
from tests.fakes import FakeToolCallingModel, tool_call

PROFILE = PROFILES["standard"]
SPEC = {s.name: s for s in TOPIC_SPECS}

GITHUB = {"items": [{
    "full_name": "langchain-ai/langgraph", "description": "Build resilient language agents as graphs.",
    "language": "Python", "stargazers_count": 9000, "pushed_at": "2026-10-20T08:00:00Z",
    "archived": False, "html_url": "https://github.com/langchain-ai/langgraph",
}]}
STACKOVERFLOW = {"items": [
    {"item_type": "question", "question_id": 11, "title": "ModuleNotFoundError: No module named &#39;pydantic&#39;",
     "excerpt": "I installed it but import fails", "score": 5, "is_answered": True,
     "creation_date": 1700000000, "tags": ["python", "pip"]},
    {"item_type": "answer", "question_id": 11, "title": "ModuleNotFoundError: No module named &#39;pydantic&#39;",
     "excerpt": "You installed into another interpreter; activate the venv", "score": 20, "is_accepted": True,
     "creation_date": 1700000500, "tags": ["python", "pip"]},
]}
WV_TIM = {"query": {"pages": [
    {"title": "Central Highlands", "index": 2, "extract": "A region of Vietnam.", "fullurl": "https://en.wikivoyage.org/wiki/Central_Highlands"},
    {"title": "Da Lat", "index": 1, "extract": "Da Lat is a hill town.", "fullurl": "https://en.wikivoyage.org/wiki/Da_Lat"},
]}}
WV_DAY_DU = {"query": {"pages": [{"title": "Da Lat", "extract": "Da Lat is a hill town.\n\n== See ==\nXuan Huong Lake."}]}}
OSM = [{"osm_type": "way", "osm_id": 123456, "name": "Hồ Xuân Hương", "category": "natural", "type": "water",
        "display_name": "Hồ Xuân Hương, Đà Lạt, Lâm Đồng, Việt Nam", "lat": "11.94", "lon": "108.44",
        "extratags": {"wikipedia": "vi:Hồ Xuân Hương"}}]
OPENLIBRARY = {"docs": [{"key": "/works/OL45804W", "title": "Fantastic Mr Fox", "author_name": ["Roald Dahl"],
                         "first_publish_year": 1970, "subject": ["Foxes", "Fiction"], "edition_count": 120}]}
MUSICBRAINZ = {"recordings": [{
    "id": "b1a9c0e9-d987-4042-ae91-78d6a3267d69", "title": "Bohemian Rhapsody", "length": 354000,
    "first-release-date": "1975-10-31", "artist-credit": [{"name": "Queen", "joinphrase": ""}],
    "releases": [{"title": "A Night at the Opera"}, {"title": "A Night at the Opera"}],
}]}


# ------------------------------------------------------------------ định dạng
def test_github_va_stackoverflow_dinh_dang():
    gh = code.dinh_dang_github(GITHUB, limit=3, max_chars=300)[0]
    assert gh.startswith("Label: [github: langchain-ai/langgraph]") and "Stars: 9000" in gh
    so = code.dinh_dang_stackoverflow(STACKOVERFLOW, limit=3, max_chars=300)
    assert len(so) == 1  # câu trả lời được gộp vào khối câu hỏi cùng question_id
    assert "Label: [stackoverflow: 11]" in so[0] and "'pydantic'" in so[0] and "Accepted answer (score 20)" in so[0]


def test_wikivoyage_xep_theo_index_va_lay_toan_van_trang_dau():
    goi = []

    def get_gia(url, params):
        goi.append(params)
        return WV_TIM if "generator" in params else WV_DAY_DU

    khoi = travel.tim_wikivoyage(get_gia, "Da Lat", limit=3, max_chars=500)
    assert khoi[0].startswith("Label: [wikivoyage: Da Lat]") and "== See ==" in khoi[0]
    assert "[wikivoyage: Central Highlands]" in khoi[1]
    assert goi[1]["titles"] == "Da Lat"
    assert travel.tim_wikivoyage(lambda u, p: {"query": {}}, "x", 3, 500) == []


def test_osm_sach_va_nhac_dinh_dang():
    osm = travel.dinh_dang_osm(OSM, limit=3)[0]
    assert osm.startswith("Label: [osm: way/123456]") and "may be outdated" in osm
    sach = culture.dinh_dang_sach(OPENLIBRARY, limit=3)[0]
    assert sach.startswith("Label: [openlibrary: OL45804W]") and "Roald Dahl" in sach
    nhac = culture.dinh_dang_nhac(MUSICBRAINZ, limit=3)[0]
    assert nhac.startswith("Label: [musicbrainz: recording/b1a9c0e9]")
    assert "Length: 5:54" in nhac and nhac.count("A Night at the Opera") == 1


# ------------------------------------------------------------------ grounding với nhãn mới
@pytest.mark.parametrize("bang_chung,nhan_that,nhan_bia", [
    (code.dinh_dang_github(GITHUB, 3, 300), "github: langchain-ai/langgraph", "github: fake/repo"),
    (code.dinh_dang_stackoverflow(STACKOVERFLOW, 3, 300), "stackoverflow: 11", "stackoverflow: 999"),
    (travel.dinh_dang_osm(OSM, 3), "osm: way/123456", "osm: node/1"),
    (culture.dinh_dang_sach(OPENLIBRARY, 3), "openlibrary: OL45804W", "openlibrary: OL1W"),
    (culture.dinh_dang_nhac(MUSICBRAINZ, 3), "musicbrainz: recording/b1a9c0e9", "musicbrainz: recording/deadbeef"),
])
def test_nhan_moi_qua_grounding_con_nhan_bia_thi_khong(bang_chung, nhan_that, nhan_bia):
    ev = "\n\n".join(bang_chung)
    assert kiem_tra_grounding(f"This source supports the stated claim here [{nhan_that}].", [ev]) == []
    assert kiem_tra_grounding(f"This source supports the stated claim here [{nhan_bia}].", [ev])


# ------------------------------------------------------------------ tool không raise
@pytest.mark.parametrize("make,ma_loi", [
    (lambda b: code.make_github_tool(b), "GITHUB_UNAVAILABLE"),
    (lambda b: code.make_stackoverflow_tool(b), "STACKOVERFLOW_UNAVAILABLE"),
    (lambda b: travel.make_wikivoyage_tool(b), "WIKIVOYAGE_UNAVAILABLE"),
    (lambda b: travel.make_place_tool(b), "OSM_UNAVAILABLE"),
    (lambda b: culture.make_book_tool(b), "OPENLIBRARY_UNAVAILABLE"),
    (lambda b: culture.make_music_tool(b), "MUSICBRAINZ_UNAVAILABLE"),
])
def test_tool_web_tra_loi_khi_mat_mang_va_dau_vao_rong(monkeypatch, make, ma_loi):
    import requests

    def hong(*a, **k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", hong)
    tool = make(SearchBudget(max_calls=3))
    assert tool.invoke({"text": "anything"}).startswith(f"ERROR: {ma_loi}")
    assert tool.invoke({"text": "  "}).startswith("ERROR: EMPTY_QUERY")


def test_tool_web_khong_ket_qua_va_tu_choi_truy_van_trung(monkeypatch):
    import requests

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"items": []}

    monkeypatch.setattr(requests, "get", lambda *a, **k: R())
    tool = code.make_github_tool(SearchBudget(max_calls=3))
    assert tool.invoke({"text": "nothing"}) == "No results from github_search for: nothing"
    assert tool.invoke({"text": "nothing"}).startswith("DA TIM TRUY VAN NAY ROI")


def test_tool_la_cua_ba_chu_de_moi():
    ten = lambda n: [t.name for t in SPEC[n].default_tools(SearchBudget(max_calls=3), PROFILE)]  # noqa: E731
    assert ten("code_agent") == ["stackoverflow_search", "github_search"]
    assert ten("travel_agent") == ["wikivoyage_search", "place_lookup", "wikipedia_search"]
    assert ten("culture_agent") == ["book_search", "music_search", "wikipedia_search"]


# ------------------------------------------------------------------ bản quyền (culture)
def test_gioi_han_trich_dan_cat_trich_dan_dai_giu_ten_tac_pham():
    dai = '"' + " ".join(["word"] * 20) + '"'
    out = gioi_han_trich_dan(f'Queen released “Bohemian Rhapsody” in 1975; it begins {dai} [x].')
    assert "“Bohemian Rhapsody”" in out and "[long quote removed]" in out and "word word" not in out


def test_culture_agent_e2e_cat_loi_bai_hat_sau_grounding(monkeypatch):
    monkeypatch.setattr(culture, "get_json", lambda url, params: MUSICBRAINZ)
    loi = " ".join(["la"] * 15)
    model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[tool_call("music_search", {"text": "Bohemian Rhapsody"})]),
        AIMessage(content=(
            "Bohemian Rhapsody by Queen was first released on 1975-10-31 [musicbrainz: recording/b1a9c0e9].\n"
            f'Its opening lyric is "{loi}" [musicbrainz: recording/b1a9c0e9].'
        )),
    ])
    msg = make_topic_tool(SPEC["culture_agent"], profile=PROFILE, model=model).invoke(
        {"name": "culture_agent", "args": {"text": "who sang Bohemian Rhapsody"}, "id": "c1", "type": "tool_call"}
    )
    answer = json.loads(msg.content)["answer"]
    assert "1975-10-31" in answer and "[long quote removed]" in answer and loi not in answer
