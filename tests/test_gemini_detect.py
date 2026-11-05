"""Hướng 4: đếm vật ngoài 80 loại COCO bằng Gemini, trong 80 loại thì vẫn YOLO.

Lời hứa:
  - Chia luồng chỉ bằng đọc câu hỏi (không tốn lượt): "mấy con chó" -> YOLO,
    "mấy quả xoài" / "người đội mũ bảo hiểm" / "con mèo màu đen" -> Gemini.
  - Khung Gemini (box_2d, 0-1000, [ymin,xmin,ymax,xmax]) đổi đúng sang pixel [x1,y1,x2,y2].
  - Gemini lỗi: vật hoàn toàn ngoài COCO -> báo lỗi rõ; có loại gốc COCO ("người đội
    mũ") -> YOLO đếm loại gốc kèm ghi chú nói rõ không phân biệt được.
  - Câu hỏi COCO bình thường KHÔNG tốn lượt Gemini nào.

Không gọi mạng, không cần API key: Gemini là model giả.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage
from PIL import Image

from app.agents.vision_agent.gemini_detect import (
    can_dung_gemini,
    dem_bang_gemini,
    doi_khung,
    muc_tieu_dem,
)
from app.agents.vision_agent.labels import dung_cau_hoi
from app.agents.vision_agent.tools import make_detect_and_count_tool
from tests.fakes import fake_detector_factory


class _GeminiGia:
    def __init__(self, tra_loi="[]", loi=None):
        self.tra_loi, self.loi = tra_loi, loi
        self.lan_goi = []

    def invoke(self, messages):
        self.lan_goi.append(messages)
        if self.loi:
            raise self.loi
        return AIMessage(content=self.tra_loi)


@pytest.fixture
def anh(tmp_path):
    p = tmp_path / "a.png"
    Image.new("RGB", (200, 100), "white").save(p)
    return str(p)


# ------------------------------ chia luồng --------------------------------- #
@pytest.mark.parametrize(
    "cau_hoi, muc_tieu",
    [
        ("Có mấy quả xoài?", "quả xoài"),
        ("Có bao nhiêu người đội mũ bảo hiểm trong ảnh?", "người đội mũ bảo hiểm"),
        ("có mấy con mèo màu đen", "con mèo màu đen"),
        ("Có mấy người mặc áo đỏ?", "người mặc áo đỏ"),  # "đỏ" không bị cắt như "đó"
        ("Có bao nhiêu chai Coca", "chai Coca"),
        ("Có bao nhiêu chiếc lá trên cây?", "chiếc lá"),
        ("đếm lại số người đội mũ", "người đội mũ"),
        ("Có mấy quả xoài vậy bạn ơi", "quả xoài"),
        ("How many people wearing helmets are in the image?", "people wearing helmets"),
    ],
)
def test_vat_ngoai_coco_di_gemini(cau_hoi, muc_tieu):
    assert can_dung_gemini(cau_hoi) == muc_tieu


@pytest.mark.parametrize(
    "cau_hoi",
    [
        "Có mấy con chó?",
        "Đếm số xe máy",
        "có mấy người",
        "trong ảnh có mấy người vậy bạn",
        "ảnh có mấy chú chó và mèo",
        "Có mấy cái ghế sofa?",
        "có bao nhiêu cái bánh donut",
        "Dem lai so cho trong anh cho nau",  # "chó" trơ trọi sau khi tách cụm
        "đếm giúp tôi số chó",
        "How many dogs are there?",
        "Đếm các vật thể",  # chung chung -> YOLO đếm hết như cũ
        "Có bao nhiêu",
        "Trong ảnh có gì?",  # không phải câu đếm
    ],
)
def test_trong_coco_hoac_chung_chung_di_yolo(cau_hoi):
    assert can_dung_gemini(cau_hoi) is None


def test_muc_tieu_bo_duong_dan_va_bi_danh():
    assert muc_tieu_dem("Có mấy quả xoài? Image: C:\\Users\\x\\xoai.jpg") == "quả xoài"
    assert muc_tieu_dem("IMG3 có mấy quả xoài") == "quả xoài"


# ------------------------------ đổi khung ---------------------------------- #
def test_doi_khung_tu_0_1000_sang_pixel():
    ds = [{"box_2d": [100, 250, 500, 750]}, {"box_2d": [0, 0, 1000, 1000]}]
    assert doi_khung(ds, 200, 100) == [[50, 10, 150, 50], [0, 0, 200, 100]]


def test_doi_khung_bo_khung_hong():
    ds = [{"box_2d": [500, 500, 100, 100]}, {"box_2d": [1, 2]}, {"x": 1}, "rac", {"box_2d": ["a", 1, 2, 3]}]
    assert doi_khung(ds, 200, 100) == []


def test_doi_khung_ep_toa_do_vao_anh():
    assert doi_khung([{"box_2d": [-50, -50, 1200, 1500]}], 200, 100) == [[0, 0, 200, 100]]


# ------------------------------ một lượt Gemini ---------------------------- #
def test_dem_bang_gemini_tra_payload_cung_dang_yolo(anh):
    gem = _GeminiGia('```json\n[{"box_2d":[100,100,400,300],"label":"xoài"},{"box_2d":[500,500,900,900],"label":"xoài"}]\n```')
    p = dem_bang_gemini(anh, "quả xoài", llm=gem)
    assert p["counting"] == {"quả xoài": 2}
    assert p["source"] == "gemini" and p["target"] == "quả xoài"
    assert all(d["confidence"] is None for d in p["detections"])
    assert p["detections"][0]["bbox"] == [20, 10, 60, 40]
    # một lượt, có ảnh, lời dặn nêu đúng vật cần tìm
    assert len(gem.lan_goi) == 1
    assert '"quả xoài"' in gem.lan_goi[0][0].content
    assert any(x.get("type") == "image_url" for x in gem.lan_goi[0][1].content)


def test_gemini_khong_thay_gi(anh):
    p = dem_bang_gemini(anh, "quả xoài", llm=_GeminiGia("[]"))
    assert p["counting"] == {} and p["detections"] == [] and "0" in p["note"]


@pytest.mark.parametrize("tra_loi", ["Tôi thấy 3 quả xoài.", "[{bad json"])
def test_gemini_tra_rac_thi_bao_loi(anh, tra_loi):
    assert "error" in dem_bang_gemini(anh, "quả xoài", llm=_GeminiGia(tra_loi))


def test_gemini_loi_mang_thi_bao_loi_khong_raise(anh):
    assert "error" in dem_bang_gemini(anh, "quả xoài", llm=_GeminiGia(loi=RuntimeError("429 quota")))


# ------------------------------ trong tool --------------------------------- #
def _yolo_nguoi():
    return fake_detector_factory([("person", 0.9, (1, 1, 5, 5)), ("person", 0.8, (6, 6, 9, 9)), ("dog", 0.9, (1, 1, 3, 3))])


def test_tool_cau_hoi_coco_khong_ton_luot_gemini(anh):
    gem = _GeminiGia("[]")
    tool = make_detect_and_count_tool(detector=_yolo_nguoi(), open_vocab_llm=gem)
    with dung_cau_hoi("Có mấy người?"):
        out = json.loads(tool.invoke({"text": anh}))
    assert out["counting"] == {"person": 2}
    assert gem.lan_goi == []


def test_tool_vat_ngoai_coco_dung_gemini_khong_chay_yolo(anh):
    def _yolo_khong_duoc_goi(_ref):
        raise AssertionError("YOLO không được chạy cho quả xoài")

    gem = _GeminiGia('[{"box_2d":[0,0,500,500]}]')
    tool = make_detect_and_count_tool(detector=_yolo_khong_duoc_goi, open_vocab_llm=gem)
    with dung_cau_hoi("Có mấy quả xoài?"):
        out = json.loads(tool.invoke({"text": anh}))
    assert out["counting"] == {"quả xoài": 1} and out["source"] == "gemini"


def test_gemini_loi_vat_hoan_toan_ngoai_coco_bao_loi_ro(anh):
    tool = make_detect_and_count_tool(detector=_yolo_nguoi(), open_vocab_llm=_GeminiGia(loi=RuntimeError("429")))
    with dung_cau_hoi("Có mấy quả xoài?"):
        out = tool.invoke({"text": anh})
    assert out.startswith("ERROR: OPEN_VOCAB_FAILED |")


def test_gemini_loi_co_loai_goc_coco_thi_yolo_dem_loai_goc_kem_ghi_chu(anh):
    tool = make_detect_and_count_tool(detector=_yolo_nguoi(), open_vocab_llm=_GeminiGia(loi=RuntimeError("429")))
    with dung_cau_hoi("Có mấy người đội mũ bảo hiểm?"):
        out = json.loads(tool.invoke({"text": anh}))
    assert out["counting"] == {"person": 2}  # chỉ người (đã lọc), không có chó
    assert "người đội mũ bảo hiểm" in out["note"] and "cannot tell" in out["note"]


# ------------------------------ api ---------------------------------------- #
def test_api_khong_loc_mat_khung_gemini(tmp_path):
    from app import api

    p = tmp_path / "a.png"
    Image.new("RGB", (200, 100)).save(p)
    tool_out = json.dumps({
        "counting": {"người đội mũ": 1}, "source": "gemini", "target": "người đội mũ",
        "detections": [{"class": "người đội mũ", "confidence": None, "bbox": [1, 1, 50, 50]}],
    }, ensure_ascii=False)
    response: dict = {}
    api._extract_vision_extras({"detect_and_count_objects": tool_out}, response)
    api._bo_sung_khung_yolo(p, "Có mấy người đội mũ?", response)
    # "người" là lớp COCO person, nhưng nhãn Gemini là cụm từ: không được lọc mất.
    assert response["counting"] == {"người đội mũ": 1}
    assert response["detect_source"] == "gemini" and response["image_size"] == [200, 100]


def test_api_khong_ve_khung_yolo_cho_cau_hoi_vat_ngoai_coco(tmp_path, monkeypatch):
    from app import api

    p = tmp_path / "a.png"
    Image.new("RGB", (20, 10)).save(p)
    monkeypatch.setattr("app.agents.vision_agent.tools.default_detector", _yolo_nguoi())
    response: dict = {}
    api._bo_sung_khung_yolo(p, "Có mấy quả xoài?", response)
    assert "detections" not in response


def test_vision_tool_duong_tat_mot_luot_gemini(anh, monkeypatch):
    """vision_agent_tool: câu đếm vật ngoài COCO -> gọi thẳng tool đếm, không chạy agent ReAct."""
    import app.agents.supervisor.tools as sup

    gem = _GeminiGia('[{"box_2d":[0,0,500,500]},{"box_2d":[500,500,1000,1000]}]')
    monkeypatch.setattr("app.core.llm.get_llm", lambda role, *a, **k: gem if role == "vision" else None)

    class _AgentKhongDuocGoi:
        def invoke(self, *a, **k):
            raise AssertionError("không được chạy vision agent")

    monkeypatch.setattr(sup, "_vision_agent_instance", _AgentKhongDuocGoi())
    kho: dict = {}
    tin = sup.vision_tool.invoke(
        {"type": "tool_call", "id": "t", "name": "vision_agent_tool",
         "args": {"query": "Có mấy quả xoài?", "image_path": anh}},
        config={"configurable": {"tool_sink": kho}},
    )
    assert "2 quả xoài" in tin.content and "Gemini" in tin.content
    assert json.loads(kho["detect_and_count_objects"])["source"] == "gemini"
    assert len(gem.lan_goi) == 1
