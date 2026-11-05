"""Hướng 6: so sánh nhiều ảnh trong MỘT lượt model.

Lời hứa:
  - vision_agent_tool nhận "IMG1,IMG3" (tối đa 5 ảnh) -> đúng MỘT lần gọi model, mang cả hai ảnh, mỗi
    ảnh có nhãn "Ảnh <n>" đứng ngay trước. Không chạy vision agent ReAct.
  - Câu hỏi đếm ("ảnh nào nhiều chó hơn") -> YOLO đếm từng ảnh, số đếm được đưa cho model.
  - Một ảnh như cũ không đổi hành vi. Ảnh không có trong bộ nhớ -> lỗi theo hợp đồng tool.
  - Artifact mang `compared_images` để web UI hiện dải ảnh đã so sánh.

Không gọi mạng, không cần API key.
"""

from __future__ import annotations

import importlib

import pytest
from langchain_core.messages import AIMessage
from PIL import Image

from tests.fakes import fake_detector_factory


class _LlmGia:
    def __init__(self, tra_loi="Ảnh 1 có mèo cam, Ảnh 3 có mèo đen."):
        self.tra_loi = tra_loi
        self.lan_goi = []

    def invoke(self, messages):
        self.lan_goi.append(messages)
        return AIMessage(content=self.tra_loi)


class _AgentGia:
    def __init__(self):
        self.so_lan = 0

    def invoke(self, state, config=None):
        self.so_lan += 1
        return {"messages": [AIMessage(content="tra loi tu agent cu")]}


class _BoGiai:
    """Đứng thay image_memory.BoGiaiAnh."""

    def __init__(self, anh: dict, chu_de: dict | None = None):
        self.anh, self._chu_de = anh, chu_de or {}

    def __call__(self, so):
        return self.anh.get(int(so))

    def chu_de(self, so):
        return self._chu_de.get(int(so))


@pytest.fixture()
def he(monkeypatch, tmp_path):
    import app.core.config as cfg

    importlib.reload(cfg)
    import app.agents.supervisor.tools as sup

    llm, agent = _LlmGia(), _AgentGia()
    monkeypatch.setattr(sup, "_vision_agent_instance", agent)
    monkeypatch.setattr("app.core.llm.get_llm", lambda role, *a, **k: llm if role == "describe" else None)

    anh = {}
    for so, mau in ((1, (240, 140, 20)), (3, (20, 20, 20)), (4, (0, 120, 0))):
        p = tmp_path / f"a{so}.png"
        Image.new("RGB", (40, 30), mau).save(p)
        anh[so] = str(p)

    class He:
        pass

    h = He()
    h.sup, h.llm, h.agent, h.anh = sup, llm, agent, anh
    h.giai = _BoGiai(anh, {1: "animal", 3: "animal", 4: "food"})
    h.hoi = lambda q, image_path=None: sup.vision_tool.invoke(
        {
            "type": "tool_call", "id": "t1", "name": "vision_agent_tool",
            "args": {"query": q, **({"image_path": image_path} if image_path else {})},
        },
        config={"configurable": {"image_resolver": h.giai}},
    )
    return h


def _anh_trong(messages):
    return [p for p in messages[1].content if p.get("type") == "image_url"]


def _chu_trong(messages):
    return [p["text"] for p in messages[1].content if p.get("type") == "text"]


def test_hai_anh_mot_luot_model_co_nhan(he):
    tin = he.hoi("Ảnh 1 và ảnh 3 khác gì nhau?", "IMG1,IMG3")
    assert tin.content == "Ảnh 1 có mèo cam, Ảnh 3 có mèo đen."
    assert len(he.llm.lan_goi) == 1 and he.agent.so_lan == 0
    msgs = he.llm.lan_goi[0]
    assert len(_anh_trong(msgs)) == 2
    chu = _chu_trong(msgs)
    assert "Ảnh 1:" in chu and "Ảnh 3:" in chu
    assert chu.index("Ảnh 1:") < chu.index("Ảnh 3:")
    assert tin.artifact["compared_images"] == [1, 3]


def test_ma_thu_hai_nam_trong_cau_hoi_cung_duoc(he):
    he.hoi("So sánh với IMG3", "IMG1")
    assert len(_anh_trong(he.llm.lan_goi[0])) == 2


def test_mot_anh_van_di_duong_cu(he):
    he.hoi("Con mèo màu gì?", "IMG1")
    # đường nhanh một ảnh: một lượt, MỘT ảnh
    assert len(he.llm.lan_goi) == 1
    assert len(_anh_trong(he.llm.lan_goi[0])) == 1


def test_toi_da_nam_anh(he, tmp_path):
    for so in (5, 6, 7):
        p = tmp_path / f"a{so}.png"
        Image.new("RGB", (8, 8)).save(p)
        he.anh[so] = str(p)
    tin = he.hoi("So sánh", "IMG1,IMG3,IMG4,IMG5,IMG6,IMG7")
    assert len(_anh_trong(he.llm.lan_goi[0])) == 5
    assert tin.artifact["compared_images"] == [1, 3, 4, 5, 6]


def test_anh_khong_con_trong_bo_nho(he):
    tin = he.hoi("So sánh", "IMG1,IMG9")
    assert tin.content.startswith("ERROR: IMAGE_NOT_IN_MEMORY |")
    assert he.llm.lan_goi == []


def test_cau_hoi_dem_dua_so_dem_yolo_cua_tung_anh(he, monkeypatch):
    ket_qua = {
        he.anh[1]: [("dog", 0.9, (1, 1, 5, 5)), ("dog", 0.8, (6, 6, 9, 9)), ("cat", 0.7, (1, 1, 2, 2))],
        he.anh[3]: [("dog", 0.9, (1, 1, 5, 5))],
    }
    monkeypatch.setattr(
        "app.agents.vision_agent.tools.default_detector",
        lambda ref: fake_detector_factory(ket_qua[ref])(ref),
    )
    tin = he.hoi("Ảnh nào có nhiều con chó hơn?", "IMG1,IMG3")
    chu = "\n".join(_chu_trong(he.llm.lan_goi[0]))
    # chỉ chó (câu hỏi về chó), số đúng từng ảnh, tên tiếng Việt
    assert "- Ảnh 1: chó 2" in chu and "- Ảnh 3: chó 1" in chu
    assert "mèo" not in chu
    assert tin.artifact["counts_per_image"] == {1: {"dog": 2}, 3: {"dog": 1}}


def test_chu_de_chung_khi_anh_khac_chu_de(he):
    from app.agents.vision_agent.prompts import COMPARE_SYSTEM_PROMPT

    he.hoi("So sánh hai ảnh", "IMG1,IMG4")  # động vật vs món ăn -> không ép chủ đề nào
    assert he.llm.lan_goi[0][0].content == COMPARE_SYSTEM_PROMPT
    he.hoi("So sánh hai ảnh", "IMG1,IMG3")  # cùng động vật -> có lời dặn động vật
    assert "TOPIC FOCUS - animals" in he.llm.lan_goi[1][0].content


def test_khong_co_bo_nho_anh_thi_bao_loi(he):
    tin = he.sup.vision_tool.invoke(
        {"type": "tool_call", "id": "t1", "name": "vision_agent_tool",
         "args": {"query": "So sánh", "image_path": "IMG1,IMG3"}},
    )
    assert tin.content.startswith("ERROR: NO_IMAGE_MEMORY |")


def test_api_dua_compared_images_ra_response():
    from langchain_core.messages import ToolMessage

    from app import api

    r = {"messages": [ToolMessage(
        content="x", name="vision_agent_tool", tool_call_id="1",
        artifact={"compared_images": [1, 3], "counts_per_image": {1: {"dog": 2}, 3: {}}},
    )]}
    response: dict = {}
    api._so_sanh_extras(r, response)
    assert response["compared_images"] == [1, 3]
    assert response["counts_per_image"] == {"1": {"dog": 2}, "3": {}}
    assert response["ten_viet"] == {"dog": "chó"}


def test_prompt_supervisor_day_so_sanh_mot_luot():
    from app.agents.supervisor.prompts import SUPERVISOR_PROMPT_TEMPLATE as p

    assert 'image_path="IMG1,IMG3"' in p
    assert p.format(agent_catalog="x")
