"""Tìm kiếm chuyên sâu: chạy cả graph bằng model giả + tool giả, không gọi mạng."""

from langchain_core.messages import AIMessage

from app.agents.research_agent import deep_research as dr
from app.agents.research_agent.profiles import PROFILES
from tests.fakes import FakeToolCallingModel

BANG_CHUNG = (
    "[1] Title: RoFormer: Enhanced Transformer with Rotary Position Embedding\n"
    "    Label: [http://arxiv.org/abs/2104.09864v5]\n"
    "    Abstract: RoPE encodes position by rotating query and key vectors."
)


class _ToolGia:
    name = "paper_search"

    def __init__(self):
        self.truy_van = []

    def invoke(self, q):
        self.truy_van.append(q)
        return BANG_CHUNG if "rotary" in q.lower() else "No papers found."


def _model(*cau):
    return FakeToolCallingModel(responses=[AIMessage(content=c) for c in cau])


def test_deep_research_tim_bu_grounding_va_ghi_file(tmp_path):
    tool = _ToolGia()
    model = _model(
        "1. How does rotary position embedding work?\n2. Who uses quantum RoPE?",
        "- RoPE rotates query and key vectors by position [http://arxiv.org/abs/2104.09864v5]",
        "TIM_THEM: quantum positional encoding",   # câu 2 thiếu -> xin tìm bù
        "KHONG DU DU LIEU",                        # tìm bù vẫn không có
        "## Tóm tắt\n"
        "RoPE mã hoá vị trí bằng cách quay vector truy vấn và vector khoá [1]. "
        "Một nghiên cứu khác khẳng định RoPE luôn tốt hơn mọi phương pháp khác [2].\n\n"
        "## 1. Cơ chế RoPE\n- RoPE quay vector query và key theo đúng vị trí của token [1].\n\n"
        "NGUỒN\n[1] http://arxiv.org/abs/2104.09864v5\n[2] http://arxiv.org/abs/9999.99999",
    )
    kq = dr.run_deep_research("rope la gi", mode="standard", model=model, tools=[tool], out_dir=tmp_path)

    # câu 1 tìm 1 lần; câu 2 tìm 2 lần (truy vấn gốc + truy vấn tìm bù), không hơn
    assert tool.truy_van == ["How does rotary position embedding work?", "Who uses quantum RoPE?",
                             "quantum positional encoding"]
    # grounding xoá câu trích nguồn bịa [2] và dòng nguồn của nó
    assert "9999.99999" not in kq["report"] and "luôn tốt hơn" not in kq["report"]
    assert kq["grounding"]["removed"] == 1
    md = (tmp_path / kq["filename"]).read_text(encoding="utf-8")
    assert md == kq["markdown"] and md.startswith("---\nquery: \"rope la gi\"\n")
    assert "mode: standard" in md and "sources: 1" in md
    assert "## Tài liệu tham khảo\n[1] http://arxiv.org/abs/2104.09864v5" in md
    assert "2. Who uses quantum RoPE? — *không đủ dữ liệu*" in md
    assert "## Kiểm tra nguồn" in md and "Đã lược bỏ 1 câu" in md


def test_eco_khong_tim_bu_va_khong_goi_writer_khi_het_du_lieu(tmp_path):
    tool = _ToolGia()
    model = _model("Q one\nQ two\nQ three\nQ four", "TIM_THEM: x", "KHONG DU DU LIEU", "KHONG DU DU LIEU",
                   "WRITER KHONG DUOC GOI")
    kq = dr.run_deep_research("q", mode="eco", model=model, tools=[tool], out_dir=tmp_path)
    assert PROFILES["eco"].deep_refine_rounds == 0
    assert tool.truy_van == ["Q one", "Q two", "Q three"]  # eco: tối đa 3 câu hỏi con, không tìm bù
    assert kq["report"].startswith("KHONG DU DU LIEU")


def test_slug_bo_dau_tieng_viet():
    assert dr._slug("Đà Lạt có gì? RoPE/ALiBi") == "da-lat-co-gi-rope-alibi"


def test_api_deep_research(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api import app

    c = TestClient(app)
    assert c.post("/api/deep_research", data={"question": "q", "research_mode": "turbo"}).status_code == 400
    monkeypatch.setattr(dr, "run_deep_research", lambda q, mode: {
        "report": "R", "markdown": "M", "filename": "f.md", "sub_questions": ["a"], "mode": mode or "standard",
        "grounding": {}, "path": "x"})
    r = c.post("/api/deep_research", data={"question": "q", "research_mode": "eco"})
    assert r.status_code == 200
    assert r.json()["answer"] == "R" and r.json()["filename"] == "f.md" and r.json()["research_mode"] == "eco"
