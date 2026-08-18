"""Test HỢP ĐỒNG — chạy `pytest` là biết mình có phá contract của nhóm không.

Đây là bản dịch sang code của bảng quy tắc thiết kế. Ai đổi tên agent, đổi tên tool,
bỏ tham số model=/tools= trong factory... sẽ thấy test đỏ ngay trên máy mình.
"""

from __future__ import annotations

import pytest

from app.agents import AGENT_SPECS, AGENT_SPECS_BY_NAME, agent_catalog
from app.core.contracts import validate_agent_layout, validate_registry, validate_tool
from app.agents.research_agent.tools import default_research_tools
from app.agents.vision_agent.tools import make_detect_and_count_tool, make_image_describer_tool
from tests.fakes import FakeStructuredModel, fake_detector_factory

EXPECTED_AGENTS = {"research_agent", "vision_agent"}
EXPECTED_TOOLS = {
    "research_agent": {"arxiv_search", "wikipedia_search"},
    "vision_agent": {"image_describer", "detect_and_count_objects"},
}


def test_registry_hop_le():
    validate_registry(AGENT_SPECS)


def test_du_cac_agent_bat_buoc():
    assert EXPECTED_AGENTS.issubset(set(AGENT_SPECS_BY_NAME))


@pytest.mark.parametrize("spec", AGENT_SPECS, ids=lambda s: s.name)
def test_moi_agent_la_mot_goi_tu_chua(spec):
    """CT-05: mỗi agent một thư mục, tên thư mục = AGENT_NAME, đủ agent.py + prompts.py."""
    validate_agent_layout(spec)


def test_khong_con_file_agent_roi_ngoai_goi():
    """Chặn kiểu cũ: app/agents/research_agent.py nằm lẫn với app/agents/research_agent/."""
    from pathlib import Path

    from app.core.config import ROOT_DIR

    agents_dir = Path(ROOT_DIR) / "app" / "agents"
    file_roi = [p.name for p in agents_dir.glob("*.py") if p.name != "__init__.py"]
    assert not file_roi, f"Các file này phải nằm trong gói agent tương ứng: {file_roi}"


def test_catalog_sinh_dung_cho_prompt_supervisor():
    catalog = agent_catalog()
    for name in EXPECTED_AGENTS:
        assert name in catalog


@pytest.mark.parametrize("tool", default_research_tools())
def test_research_tools_dung_hop_dong(tool):
    validate_tool(tool)


def _vision_tools():
    return [
        make_image_describer_tool(vision_llm=FakeStructuredModel(payload={"image_description": "x"})),
        make_detect_and_count_tool(detector=fake_detector_factory([])),
    ]


@pytest.mark.parametrize("tool", _vision_tools())
def test_vision_tools_dung_hop_dong(tool):
    validate_tool(tool)


def test_ten_tool_khong_doi_ngoai_y_muon():
    got = {t.name for t in default_research_tools()}
    assert got == EXPECTED_TOOLS["research_agent"]
    got = {t.name for t in _vision_tools()}
    assert got == EXPECTED_TOOLS["vision_agent"]


@pytest.mark.parametrize("ten_file", ["requirements.txt", ".env.example"])
def test_file_cau_hinh_chi_dung_ascii(ten_file):
    """DT-06: pip đọc requirements.txt bằng codec locale của Windows (cp1258 trên
    máy tiếng Việt) nên chữ có dấu làm hỏng cả lệnh cài đặt.
    """
    from pathlib import Path

    from app.core.config import ROOT_DIR

    data = (Path(ROOT_DIR) / ten_file).read_bytes()
    xau = [(i, b) for i, b in enumerate(data) if b > 127]
    assert not xau, (
        f"{ten_file} có {len(xau)} byte non-ASCII (byte đầu ở vị trí {xau[0][0]}). "
        "Chuyển chú thích tiếng Việt sang QUY_TAC_THIET_KE.md."
    )


def test_khong_hardcode_api_key_trong_source():
    """Quét thô source tìm chuỗi giống API key bị commit nhầm (OpenAI sk-…, Google AIza…)."""
    import re
    from pathlib import Path

    from app.core.config import ROOT_DIR

    # sk-… (OpenAI) · AIza… (Google, đời cũ) · AQ.… (Google Auth key, từ 06/2026)
    pattern = re.compile(r"sk-[A-Za-z0-9_\-]{20,}|AIza[A-Za-z0-9_\-]{30,}|AQ\.[A-Za-z0-9_\-]{20,}")
    offenders = []
    for path in Path(ROOT_DIR).rglob("*.py"):
        if ".venv" in path.parts:
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path))
    assert not offenders, f"Có API key bị hard-code trong: {offenders}"
