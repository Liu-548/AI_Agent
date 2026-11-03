"""Nhãn tiếng Việt + lọc theo loại vật thể (labels.py). Không cần mạng/API key/model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.vision_agent.labels import (
    COCO_VI,
    dung_cau_hoi,
    lop_dang_loc,
    lop_tu_cau_hoi,
    loc_theo_lop,
    nhan_viet,
    ten_viet,
)
from app.agents.vision_agent.tools import make_detect_and_count_tool

from tests.fakes import fake_detector_factory


@pytest.mark.parametrize(
    "cau_hoi, mong_doi",
    [
        ("Có mấy con mèo?", {"cat"}),
        ("Có bao nhiêu con chó trong ảnh", {"dog"}),
        ("cho tôi biết có mấy người", {"person"}),
        ("có mấy con ngựa vằn", {"zebra"}),  # không được kéo theo "horse"
        ("có mấy con ngựa", {"horse"}),
        ("bao nhiêu chiếc xe máy", {"motorcycle"}),
        ("có mấy chiếc ô tô", {"car"}),  # "ô tô" không phải "ô" (dù)
        ("có mấy chiếc ô", {"umbrella"}),
        ("bao nhiêu cái ghế sofa", {"couch"}),  # không kéo theo "chair"
        ("có mấy quả táo", {"apple"}),
        ("Có bao nhiêu chiếc bánh donut", {"donut"}),
        ("How many dogs are there?", {"dog"}),
        ("có mấy con chó và mèo", {"dog", "cat"}),
        ("Đếm số chó và mèo", {"dog", "cat"}),  # "chó" trần trong cụm đếm/liệt kê
        ("đếm số chó", {"dog"}),
    ],
)
def test_lop_tu_cau_hoi(cau_hoi, mong_doi):
    assert lop_tu_cau_hoi(cau_hoi) == frozenset(mong_doi)


@pytest.mark.parametrize(
    "cau_hoi",
    [
        "Trong ảnh có gì?",
        "đếm các vật thể",
        "mô tả ảnh với tôi",
        "với anh này có điều gì đặc biệt",  # "với"/"điều" trùng âm voi/dieu
        "đây là chỗ nào, bạn cho biết giúp",  # "cho" = give, "bạn", "chỗ"
        "tôi muốn biết có bao nhiêu",
        "bạn cho tôi xem ảnh",
        "cho tôi biết số lượng",
    ],
)
def test_cau_hoi_khong_neu_loai_thi_khong_loc(cau_hoi):
    assert lop_tu_cau_hoi(cau_hoi) == frozenset()


def test_ten_file_trong_cau_hoi_khong_bi_hieu_nham_la_loai_vat():
    q = "Có bao nhiêu vật? Image: C:\\Users\\Dell\\Downloads\\cat.jpg và /tmp/dog.png"
    assert lop_tu_cau_hoi(q) == frozenset()


def test_nhom_chung():
    assert {"dog", "cat", "zebra"} <= lop_tu_cau_hoi("có bao nhiêu động vật")
    assert "person" not in lop_tu_cau_hoi("có bao nhiêu động vật")
    assert lop_tu_cau_hoi("đếm số xe") == frozenset({"bicycle", "car", "motorcycle", "bus", "truck"})


def test_ten_viet():
    assert ten_viet("cat") == "mèo"
    assert ten_viet("dog") == "chó"
    assert ten_viet("khong-co-lop-nay") == "khong-co-lop-nay"
    assert nhan_viet(["cat", "bus"]) == {"cat": "mèo", "bus": "xe buýt"}
    assert len(COCO_VI) == 80


def test_coco_vi_khop_ten_lop_trong_model_onnx():
    """Nếu ai đó đổi sang model có lớp khác, test này chỉ ra lớp nào chưa có tên Việt."""
    ort = pytest.importorskip("onnxruntime")
    model = Path(__file__).resolve().parent.parent / "yolo11n.onnx"
    if not model.is_file():
        pytest.skip("chưa có yolo11n.onnx")
    import ast

    meta = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"]).get_modelmeta()
    ten_lop = set(ast.literal_eval(meta.custom_metadata_map["names"]).values())
    assert ten_lop == set(COCO_VI)


# --------------------------- loc payload ------------------------------------ #
def _payload():
    return {
        "counting": {"cat": 1, "dog": 2, "chair": 1},
        "detections": [
            {"class": "dog", "confidence": 0.9, "bbox": [0, 0, 1, 1]},
            {"class": "cat", "confidence": 0.8, "bbox": [0, 0, 1, 1]},
            {"class": "dog", "confidence": 0.7, "bbox": [0, 0, 1, 1]},
            {"class": "chair", "confidence": 0.6, "bbox": [0, 0, 1, 1]},
        ],
    }


def test_loc_theo_lop_chi_giu_loai_duoc_hoi():
    ra = loc_theo_lop(_payload(), {"dog"})
    assert ra["counting"] == {"dog": 2}
    assert [d["class"] for d in ra["detections"]] == ["dog", "dog"]
    assert ra["filtered_by"] == ["dog"]


def test_loc_rong_thi_tra_nguyen_va_khong_sua_ban_goc():
    goc = _payload()
    assert loc_theo_lop(goc, set()) is goc
    loc_theo_lop(goc, {"cat"})
    assert goc["counting"] == {"cat": 1, "dog": 2, "chair": 1}


# --------------------------- tool detect_and_count --------------------------- #
@pytest.fixture
def anh(tmp_path):
    from PIL import Image

    p = tmp_path / "a.png"
    Image.new("RGB", (32, 32), "white").save(p)
    return str(p)


def _det():
    return fake_detector_factory(
        [("dog", 0.94, (1, 2, 3, 4)), ("dog", 0.84, (5, 6, 7, 8)), ("cat", 0.51, (1, 2, 3, 4)), ("chair", 0.4, (1, 1, 2, 2))]
    )


def test_tool_hoi_ve_meo_chi_tra_meo(anh):
    tool = make_detect_and_count_tool(detector=_det())
    with dung_cau_hoi("Có mấy con mèo?"):
        out = json.loads(tool.invoke({"text": anh}))
    assert out["counting"] == {"cat": 1}
    assert out["labels_vi"] == {"cat": "mèo"}
    assert all(d["class"] == "cat" for d in out["detections"])


def test_tool_khong_co_loai_duoc_hoi_thi_noi_la_0_khong_tra_loai_khac(anh):
    tool = make_detect_and_count_tool(detector=_det())
    with dung_cau_hoi("Có mấy con voi?"):
        out = json.loads(tool.invoke({"text": anh}))
    assert out["counting"] == {} and out["detections"] == []
    assert "voi" in out["note"] and "0" in out["note"]


def test_tool_cau_hoi_chung_khong_loc(anh):
    tool = make_detect_and_count_tool(detector=_det())
    with dung_cau_hoi("Trong ảnh có gì?"):
        out = json.loads(tool.invoke({"text": anh}))
    assert out["counting"] == {"dog": 2, "cat": 1, "chair": 1}
    assert out["labels_vi"]["dog"] == "chó"


def test_tool_khong_co_cau_hoi_thi_hanh_vi_nhu_cu(anh):
    tool = make_detect_and_count_tool(detector=_det())
    out = json.loads(tool.invoke({"text": anh}))
    assert out["counting"] == {"dog": 2, "cat": 1, "chair": 1}


def test_context_tu_dong_tra_ve_sau_khoi_with():
    with dung_cau_hoi("có mấy con mèo"):
        assert lop_dang_loc() == frozenset({"cat"})
    assert lop_dang_loc() == frozenset()
