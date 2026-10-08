"""Test đường nhìn ảnh nhanh (VISION_DIRECT): MỘT lượt model nhìn ảnh và trả lời luôn.

Lời hứa của tính năng:
  - Câu hỏi không cần đếm: vision_tool trả lời bằng đúng MỘT lượt gọi model, KHÔNG
    chạy vision agent (chuỗi ReAct nhiều lượt).
  - Câu hỏi đếm / phát hiện vật thể vẫn đi qua vision agent (YOLO).
  - Đường nhanh lỗi (hết hạn mức, ảnh hỏng, model trả rỗng) thì quay về vision agent,
    người dùng vẫn có câu trả lời.
  - Lời dặn chủ đề ảnh nằm trong system prompt của lượt nhanh; VISION_DIRECT=false
    thì luôn đi chuỗi cũ.

Không gọi mạng. Không test được ở đây: model thật trả lời đúng/tốt đến đâu.
"""

from __future__ import annotations

import importlib

import pytest
from langchain_core.messages import AIMessage
from PIL import Image

from app.agents.vision_agent import tools as vtools
from app.agents.vision_agent import topics
from app.agents.vision_agent.prompts import DIRECT_ANSWER_SYSTEM_PROMPT


class _LlmGia:
    """Đứng thay model "describe": ghi lại mọi lần gọi, trả lời theo kịch bản."""

    def __init__(self, tra_loi="Đây là con mèo cam.", loi=None):
        self.tra_loi, self.loi = tra_loi, loi
        self.lan_goi = []

    def invoke(self, messages):
        self.lan_goi.append(messages)
        if self.loi:
            raise self.loi
        return AIMessage(content=self.tra_loi)


class _AgentGia:
    def __init__(self):
        self.cau_hoi = []

    def invoke(self, state, config=None):
        self.cau_hoi.append(state["messages"][0][1])
        return {"messages": [AIMessage(content="tra loi tu agent cu")]}


@pytest.fixture()
def anh(tmp_path):
    duong_dan = tmp_path / "meo.png"
    Image.new("RGB", (40, 30), (240, 140, 20)).save(duong_dan)
    return str(duong_dan)


@pytest.fixture()
def he(monkeypatch):
    """vision_tool thật với LLM "describe" giả và vision agent giả."""
    monkeypatch.delenv("VISION_DIRECT", raising=False)
    import app.core.config as cfg

    importlib.reload(cfg)
    import app.agents.supervisor.tools as sup

    llm, agent = _LlmGia(), _AgentGia()
    monkeypatch.setattr(sup, "_vision_agent_instance", agent)
    # tra_loi_truc_tiep tự lấy model bằng get_llm("describe") khi không được đưa vào.
    monkeypatch.setattr("app.core.llm.get_llm", lambda role, *a, **k: llm if role == "describe" else None)

    class He:
        pass

    h = He()
    h.sup, h.llm, h.agent = sup, llm, agent
    h.hoi = lambda cau_hoi, duong_dan=None: sup.vision_tool.invoke(
        {"query": cau_hoi, **({"image_path": duong_dan} if duong_dan else {})}
    )
    return h


# --------------------------- đếm vật thể: YOLO ------------------------------ #
@pytest.mark.parametrize(
    "cau_hoi, can_dem",
    [
        ("Có bao nhiêu con mèo?", True),
        ("co bao nhieu nguoi trong anh", True),
        ("Đếm số xe", True),
        ("Trong ảnh có mấy con chó", True),
        ("How many cats are there?", True),
        ("Detect the objects", True),
        ("Số lượng sản phẩm?", True),
        ("Đây là con gì?", False),
        ("Đây là ở đâu?", False),
        ("Đọc chữ trên hóa đơn", False),
        ("Món này tên gì?", False),
        ("Con mèo màu gì?", False),
    ],
)
def test_nhan_ra_cau_hoi_can_dem(cau_hoi, can_dem):
    assert vtools.can_dem_vat_the(cau_hoi) is can_dem


# ------------------------------ đường nhanh --------------------------------- #
def test_cau_hoi_thuong_chi_tot_mot_luot_model_va_khong_chay_agent(he, anh):
    tra_loi = he.hoi("Đây là con gì?", anh)

    assert tra_loi == "Đây là con mèo cam."
    assert len(he.llm.lan_goi) == 1
    assert he.agent.cau_hoi == []


def test_luot_nhanh_nhan_dung_anh_cau_hoi_va_prompt(he, anh):
    he.hoi("Mô tả ảnh này", anh)

    he_thong, nguoi_dung = he.llm.lan_goi[0]
    assert he_thong.content == DIRECT_ANSWER_SYSTEM_PROMPT
    khoi_chu, khoi_anh = nguoi_dung.content
    assert khoi_chu == {"type": "text", "text": "Mô tả ảnh này"}
    assert khoi_anh["image_url"]["url"].startswith("data:image/png;base64,")


def test_duong_dan_ghi_trong_cau_hoi_duoc_tach_ra_khoi_noi_dung_hoi(he, anh):
    he.hoi(f"Đây là con gì? Image: {anh}")

    cau = he.llm.lan_goi[0][1].content[0]["text"]
    assert anh not in cau and cau.startswith("Đây là con gì?")


def test_cau_hoi_dem_van_di_qua_agent_cu(he, anh):
    tra_loi = he.hoi("Có bao nhiêu con mèo?", anh)

    assert tra_loi == "tra loi tu agent cu"
    assert he.llm.lan_goi == []
    assert len(he.agent.cau_hoi) == 1


def test_khong_co_anh_thi_de_agent_cu_xu_ly(he):
    tra_loi = he.hoi("Đây là con gì?")

    assert tra_loi == "tra loi tu agent cu"
    assert he.llm.lan_goi == []


# ------------------------------ quay về đường cũ ---------------------------- #
@pytest.mark.parametrize(
    "llm",
    [
        _LlmGia(loi=RuntimeError("429 het han muc")),
        _LlmGia(tra_loi=""),
        _LlmGia(tra_loi="   "),
    ],
    ids=["model-loi", "tra-rong", "toan-dau-cach"],
)
def test_duong_nhanh_hong_thi_quay_ve_agent_cu(he, monkeypatch, anh, llm):
    monkeypatch.setattr("app.core.llm.get_llm", lambda role, *a, **k: llm)

    tra_loi = he.hoi("Đây là con gì?", anh)

    assert tra_loi == "tra loi tu agent cu"
    assert len(llm.lan_goi) == 1 and len(he.agent.cau_hoi) == 1


def test_khong_tao_duoc_model_thi_quay_ve_agent_cu(he, monkeypatch, anh):
    def thieu_key(role, *a, **k):
        raise RuntimeError("thieu GEMINI_API_KEY")

    monkeypatch.setattr("app.core.llm.get_llm", thieu_key)

    assert he.hoi("Đây là con gì?", anh) == "tra loi tu agent cu"


def test_anh_khong_doc_duoc_thi_quay_ve_agent_cu(he):
    assert he.hoi("Đây là con gì?", "/khong/co/file.png") == "tra loi tu agent cu"
    assert he.llm.lan_goi == []


# ------------------------------- công tắc ----------------------------------- #
def test_tat_vision_direct_thi_luon_di_agent_cu(he, monkeypatch, anh):
    monkeypatch.setenv("VISION_DIRECT", "false")
    import app.core.config as cfg

    importlib.reload(cfg)

    assert he.hoi("Đây là con gì?", anh) == "tra loi tu agent cu"
    assert he.llm.lan_goi == []


# ------------------------------ chủ đề ảnh ---------------------------------- #
def test_loi_dan_chu_de_nam_trong_prompt_cua_luot_nhanh(he, anh):
    # Câu hỏi "ở đâu" chỉ thẳng chủ đề du lịch -> lời dặn du lịch đi theo vào lượt nhanh.
    he.hoi("Đây là ở đâu?", anh)

    he_thong = he.llm.lan_goi[0][0].content
    assert he_thong.startswith(DIRECT_ANSWER_SYSTEM_PROMPT)
    assert topics.CHU_DE["travel"].loi_dan in he_thong


def test_chu_de_chung_khong_them_gi_vao_prompt(he, anh):
    he.hoi("Mô tả ảnh này", anh)

    assert he.llm.lan_goi[0][0].content == DIRECT_ANSWER_SYSTEM_PROMPT


def test_chu_de_khong_dinh_lai_sau_luot_nhanh(he, anh):
    he.hoi("Đây là ở đâu?", anh)

    assert topics.chu_de_hien_tai() is None
