"""Hướng 5: chủ đề "biểu đồ / sơ đồ khoa học" và nối sang Research Agent.

Lời hứa:
  - Câu hỏi về biểu đồ -> chủ đề "chart": lượt nhìn ảnh nhận lời dặn đọc biểu đồ thành
    bảng số liệu, không bịa số, và kết thúc bằng dòng "KHÁI NIỆM: ..." để Research tra.
  - Từ khoá không đụng các từ trùng âm khi bỏ dấu (đô thị/đồ thị, số đo/sơ đồ/sổ đỏ).
  - Hồ sơ ảnh nhận chủ đề "chart"; prompt supervisor có luật nối Vision -> Research.
  - Supervisor THẬT (LangGraph) chạy được chuỗi vision -> research và cả hai kết quả
    về tới câu trả lời. (Model giả: không đo được model thật có tự nối hay không.)
"""

from __future__ import annotations

import importlib

import pytest
from langchain_core.messages import AIMessage
from PIL import Image

from app.agents.vision_agent import topics


@pytest.mark.parametrize(
    "cau_hoi, mong_doi",
    [
        ("Đọc số liệu trong biểu đồ này", "chart"),
        ("Biểu đồ này nói lên điều gì?", "chart"),
        ("bieu do nay the hien gi", "chart"),
        ("Trục tung là đại lượng gì?", "chart"),
        ("Chuyển bảng số liệu trong ảnh thành bảng", "chart"),
        ("Giải thích sơ đồ khoa học này", "chart"),
        ("What does this chart show?", "chart"),
        # trùng âm khi bỏ dấu -> KHÔNG được thành biểu đồ
        ("Đây là khu đô thị nào?", None),
        ("Số đo các cạnh là bao nhiêu?", None),
        ("Sổ đỏ này của ai?", None),
        # biểu đồ + đọc chữ: hai chủ đề -> mơ hồ -> để hồ sơ ảnh quyết định
        ("Đọc chữ trong biểu đồ", None),
    ],
)
def test_chu_de_bieu_do_tu_cau_hoi(cau_hoi, mong_doi):
    assert topics.chu_de_tu_cau_hoi(cau_hoi) == mong_doi


def test_loi_dan_bieu_do_doi_bang_so_lieu_va_khai_niem():
    loi_dan = topics.CHU_DE["chart"].loi_dan
    assert "Markdown table" in loi_dan and "never invent numbers" in loi_dan
    assert "KHÁI NIỆM:" in loi_dan
    assert topics.CHU_DE_IDS[-1] == topics.CHU_DE_CHUNG  # "chung" vẫn là dự phòng cuối


def test_ho_so_anh_nhan_chu_de_chart():
    from app.image_memory import HO_SO_PROMPT, lam_sach_ho_so

    assert '"chart"' in HO_SO_PROMPT
    assert lam_sach_ho_so({"subject": "biểu đồ cột", "topic": "chart"})["topic"] == "chart"


def test_prompt_supervisor_co_luat_noi_vision_sang_research():
    from app.agents.supervisor.prompts import SUPERVISOR_PROMPT_TEMPLATE as p

    assert "CHART -> RESEARCH" in p and "KHÁI NIỆM:" in p
    assert "Số liệu từ biểu đồ" in p and "Nghiên cứu liên quan" in p
    assert p.format(agent_catalog="x")


def test_cau_hoi_bieu_do_qua_vision_tool_nhan_loi_dan_bieu_do(monkeypatch, tmp_path):
    monkeypatch.delenv("VISION_DIRECT", raising=False)
    import app.core.config as cfg

    importlib.reload(cfg)
    import app.agents.supervisor.tools as sup

    goi = []

    class _Llm:
        def invoke(self, messages):
            goi.append(messages)
            return AIMessage(content="| Năm | Giá trị |\n|---|---|\n| 2020 | ~12 |\nKHÁI NIỆM: hiệu ứng nhà kính (greenhouse effect)")

    monkeypatch.setattr("app.core.llm.get_llm", lambda role, *a, **k: _Llm() if role == "describe" else None)
    anh = tmp_path / "chart.png"
    Image.new("RGB", (40, 30), "white").save(anh)
    tin = sup.vision_tool.invoke({"query": "Đọc số liệu trong biểu đồ này", "image_path": str(anh)})
    assert "KHÁI NIỆM" in tin
    assert "TOPIC FOCUS - charts" in goi[0][0].content


def test_supervisor_that_chay_chuoi_vision_roi_research(monkeypatch, tmp_path):
    """Đi qua create_react_agent thật: vision -> research -> câu trả lời gộp."""
    from langchain_core.tools import tool

    from app.agents.supervisor.agent import build_supervisor
    from tests.fakes import FakeToolCallingModel, tool_call

    nhan = {}

    @tool("vision_agent_tool")
    def vision_gia(query: str, image_path: str = "") -> str:
        """vision"""
        nhan["vision"] = query
        return "| Năm | CO2 (ppm) |\n|---|---|\n| 2000 | ~370 |\n| 2020 | ~412 |\nKHÁI NIỆM: nồng độ CO2 khí quyển (atmospheric CO2 concentration)"

    @tool("research_agent_tool")
    def research_gia(query: str) -> str:
        """research"""
        nhan["research"] = query
        return "- CO2 tăng do đốt nhiên liệu hóa thạch [1]\nNGUON:\n[1] https://example.org/paper"

    model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[tool_call("vision_agent_tool", {"query": "Đọc biểu đồ", "image_path": "IMG1"}, "c1")]),
        AIMessage(content="", tool_calls=[tool_call("research_agent_tool", {"query": "atmospheric CO2 concentration rise causes"}, "c2")]),
        AIMessage(content="**Số liệu từ biểu đồ** ... **Nghiên cứu liên quan** ... [1]"),
    ])
    sup = build_supervisor(model=model, tools=[vision_gia, research_gia])
    kq = sup.invoke({"messages": [("user", "Giải thích biểu đồ này và tìm nghiên cứu liên quan")]})
    assert "CO2" in nhan["research"]
    ten_tool = [m.name for m in kq["messages"] if getattr(m, "type", "") == "tool"]
    assert ten_tool == ["vision_agent_tool", "research_agent_tool"]
    assert "Nghiên cứu liên quan" in kq["messages"][-1].content
