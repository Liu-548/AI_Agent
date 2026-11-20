"""Tìm kiếm chuyên sâu: chạy cả graph bằng model giả + agent chủ đề giả, không gọi mạng/LLM thật."""

import json

from langchain_core.messages import AIMessage, ToolMessage

from app.agents.research_agent import deep_research as dr
from app.agents.research_agent.profiles import PROFILES
from tests.fakes import FakeToolCallingModel

BANG_CHUNG_TIN = (
    "Label: [news: gn-6a20df73]\nTitle: Former Nvidia employee alleges CEO affair\n"
    "Source: Reuters | Published: 2026-11-14\nURL: https://news.example/a"
)
BANG_CHUNG_BAI_BAO = "Label: [http://arxiv.org/abs/2104.09864v5]\nAbstract: RoPE rotates query and key vectors."


class _ChuDeGia:
    """Giả tool của make_topic_tool: invoke(tool_call) -> ToolMessage(content JSON, artifact)."""

    def __init__(self, name, tra_loi):
        self.name, self.description, self.tra_loi, self.cau_hoi = name, f"{name} test agent", tra_loi, []

    def invoke(self, call):
        cau = call["args"]["text"]
        self.cau_hoi.append(cau)
        answer, bang_chung = self.tra_loi(cau)
        status = "ok" if answer else "no_data"
        content = json.dumps({"topic": self.name, "status": status, "sub_question": cau,
                              "answer": answer or "KHONG DU DU LIEU: x", "labels": [],
                              "grounding": {"removed": 0, "missing_source": 0}})
        return ToolMessage(content=content, tool_call_id=call["id"], name=self.name,
                           artifact={"evidence_text": bang_chung, "usage": {"llm_calls": 2}})


def _model(*cau):
    return FakeToolCallingModel(responses=[AIMessage(content=c) for c in cau])


def _tin(cau):
    if "affair" in cau.lower():
        return ("A former employee alleged an affair by Jensen Huang, Reuters reported [news: gn-6a20df73].",
                BANG_CHUNG_TIN)
    return "", "No results"


def _bai_bao(cau):
    if "rotary" in cau.lower():
        return "RoPE rotates query and key vectors [http://arxiv.org/abs/2104.09864v5].", BANG_CHUNG_BAI_BAO
    return "", "No papers found."


def test_tach_ke_hoach_giu_agent_hop_le_va_mac_dinh():
    out = ("news_agent | What did Reuters report about the Nvidia CEO affair?\n"
           "1. scholar_agent | How does RoPE work?\n"
           "foo_agent | Unknown agent line\n"
           "Plain line without agent")
    kh = dr.tach_ke_hoach(out, ["news_agent", "scholar_agent"], "news_agent", 3)
    assert kh == [("news_agent", "What did Reuters report about the Nvidia CEO affair?"),
                  ("scholar_agent", "How does RoPE work?"),
                  ("news_agent", "Unknown agent line")]


def test_deep_research_moi_y_mot_agent_tim_bu_doi_agent_grounding_va_ghi_file(tmp_path):
    tin, bai = _ChuDeGia("news_agent", _tin), _ChuDeGia("scholar_agent", _bai_bao)
    model = _model(
        # plan: 2 ý của câu hỏi -> 2 câu hỏi con; câu 2 bị giao nhầm cho scholar
        "news_agent | What is known about the alleged affair of Nvidia CEO Jensen Huang?\n"
        "scholar_agent | Who is the new CEO of Nvidia?",
        # refine: câu 2 chuyển sang news_agent, đổi cách hỏi
        "2 | news_agent | Nvidia new CEO 2026",
        # write: trích bằng nhãn; câu 2 nhãn bịa -> grounding xoá; [gn-...] trần -> code thêm "news: "
        "## Tóm tắt\nReuters đưa tin một cựu nhân viên cáo buộc ông Jensen Huang ngoại tình [gn-6a20df73]. "
        "Nvidia đã bổ nhiệm CEO mới vào tuần trước [news: gn-deadbeef].\n\n"
        "## 1. Cáo buộc ngoại tình\n- Theo Reuters, một cựu nhân viên Nvidia đưa ra cáo buộc này【news: gn-6a20df73】.",
    )
    kq = dr.run_deep_research("bê bối của CEO Nvidia và ghế CEO mới", mode="standard", model=model,
                              tools=[tin, bai], out_dir=tmp_path)

    # Mỗi ý một câu hỏi con; câu 2 lần đầu đi scholar, tìm bù đi news với câu mới — không hơn
    assert tin.cau_hoi == ["What is known about the alleged affair of Nvidia CEO Jensen Huang?", "Nvidia new CEO 2026"]
    assert bai.cau_hoi == ["Who is the new CEO of Nvidia?"]
    assert [(t["topic"], t["status"]) for t in kq["trace"]] == [
        ("news_agent", "ok"), ("scholar_agent", "no_data"), ("news_agent", "no_data")]
    assert "gn-deadbeef" not in kq["report"] and "tuần trước" not in kq["report"]
    assert kq["grounding"]["removed"] == 1
    assert "gn-6a20df73" in kq["evidence"]
    md = (tmp_path / kq["filename"]).read_text(encoding="utf-8")
    assert md == kq["markdown"] and "sources: 1" in md
    assert "## Tài liệu tham khảo\n[1] news: gn-6a20df73" in md
    assert kq["report"].count("[1]") == 3  # 2 câu trích + dòng nguồn, cùng một số
    assert "2. `news_agent` Who is the new CEO of Nvidia? — *không đủ dữ liệu*" in md
    assert "Đã lược bỏ 1 câu" in md


def test_so_hoa_trich_dan_theo_thu_tu_xuat_hien_va_bo_nguon_cu():
    bai = ("## Tóm tắt\nA [news: gn-11111111]. B [http://arxiv.org/abs/1]. C [news: gn-11111111][wikipedia: X].\n"
           "NGUỒN\n[9] rác")
    assert dr.so_hoa_trich_dan(bai) == (
        "## Tóm tắt\nA [1]. B [2]. C [1][3].\n\nNGUỒN\n[1] news: gn-11111111\n"
        "[2] http://arxiv.org/abs/1\n[3] wikipedia: X")


def test_eco_khong_tim_bu_va_khong_goi_writer_khi_het_du_lieu(tmp_path):
    bai = _ChuDeGia("scholar_agent", _bai_bao)
    model = _model("scholar_agent | Q one\nscholar_agent | Q two\nscholar_agent | Q three\nscholar_agent | Q four",
                   "WRITER KHONG DUOC GOI")
    kq = dr.run_deep_research("q", mode="eco", model=model, tools=[bai], out_dir=tmp_path)
    assert PROFILES["eco"].deep_refine_rounds == 0
    assert bai.cau_hoi == ["Q one", "Q two", "Q three"]  # eco: tối đa 3 câu hỏi con, không tìm bù
    assert kq["report"].startswith("KHONG DU DU LIEU")


def test_het_han_muc_llm_thi_cho_thu_lai_mot_lan_roi_dung(tmp_path, monkeypatch):
    monkeypatch.setattr(dr, "CHO_HAN_MUC_GIAY", 0)
    class _LoiHanMuc(_ChuDeGia):
        def invoke(self, call):
            self.cau_hoi.append(call["args"]["text"])
            return ToolMessage(content="ERROR: LLM_RATE_LIMITED | role research_topic", tool_call_id="x",
                               name=self.name, artifact={"usage": {}})

    tin = _LoiHanMuc("news_agent", _tin)
    model = _model("news_agent | A\nnews_agent | B", "KHONG DUOC GOI")
    kq = dr.run_deep_research("q", mode="standard", model=model, tools=[tin], out_dir=tmp_path)
    assert tin.cau_hoi == ["A", "A"]  # thử lại đúng một lần, rồi không gọi câu B nữa
    assert kq["trace"][0]["status"] == "error" and "LLM_RATE_LIMITED" in kq["trace"][0]["error"]


def test_slug_bo_dau_tieng_viet():
    assert dr._slug("Đà Lạt có gì? RoPE/ALiBi") == "da-lat-co-gi-rope-alibi"


def test_api_deep_research(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api import app

    c = TestClient(app)
    assert c.post("/api/deep_research", data={"question": "q", "research_mode": "turbo"}).status_code == 400
    monkeypatch.setattr(dr, "run_deep_research", lambda q, mode: {
        "report": "R [1]\nNGUỒN\n[1] news: gn-6a20df73", "markdown": "M", "filename": "f.md",
        "sub_questions": ["a"], "mode": mode or "standard", "grounding": {}, "path": "x",
        "trace": [{"topic": "news_agent", "status": "ok", "sub_question": "a"}], "evidence": BANG_CHUNG_TIN})
    r = c.post("/api/deep_research", data={"question": "q", "research_mode": "eco"})
    assert r.status_code == 200
    j = r.json()
    assert j["filename"] == "f.md" and j["research_mode"] == "eco"
    assert j["research_trace"][0]["topic"] == "news_agent"
    assert j["link_map"]["gn-6a20df73"]["source"] == "Reuters"
