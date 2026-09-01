"""Test tool của Vision Agent — không cần API key, không cần tải model YOLO."""

from __future__ import annotations

import base64
import io
import json

import pytest

from app.core.contracts import ERROR_PREFIX
from app.agents.vision_agent import tools as vision_tools
from app.agents.vision_agent.tools import (
    default_detector,
    make_detect_and_count_tool,
    make_image_describer_tool,
    parse_yolo_results,
)
from app.agents.vision_agent.image_utils import encode_image, extract_image_ref
from tests.fakes import FakeStructuredModel, fake_detector_factory


@pytest.fixture
def anh_png(tmp_path):
    from PIL import Image

    path = tmp_path / "sample.png"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(path)
    return str(path)


# --------------------------- encode_image ---------------------------------- #
def test_encode_image_tra_ve_base64_va_mime(anh_png):
    b64, mime = encode_image(anh_png, get_mime_type=True)
    assert mime == "image/png"
    assert base64.b64decode(b64)[:8] == b"\x89PNG\r\n\x1a\n"


def test_encode_image_file_khong_ton_tai_tra_none():
    assert encode_image("./khong_co_that.png") is None
    assert encode_image("./khong_co_that.png", get_mime_type=True) == (None, None)


def test_encode_image_file_khong_phai_anh_tra_none(tmp_path):
    p = tmp_path / "note.png"  # đuôi .png nhưng nội dung là text
    p.write_text("day khong phai anh")
    assert encode_image(str(p)) is None


# --------------------------- extract_image_ref ----------------------------- #
@pytest.mark.parametrize(
    "cau_hoi, mong_doi",
    [
        ("how many dogs in image: ./dogs.jpg", "./dogs.jpg"),
        ("Ảnh: assets/multi-dogs.jpeg có mấy con chó?", "assets/multi-dogs.jpeg"),
        (
            "What is in https://example.com/a/b/pic.png ?",
            "https://example.com/a/b/pic.png",
        ),
        ("mô tả ảnh C:/Users/tuan/Pictures/cat.PNG giúp tôi", "C:/Users/tuan/Pictures/cat.PNG"),
    ],
)
def test_tach_duoc_duong_dan_anh(cau_hoi, mong_doi):
    assert extract_image_ref(cau_hoi) == mong_doi


def test_khong_co_anh_thi_tra_none():
    assert extract_image_ref("what is machine learning?") is None


# --------------------------- image_describer ------------------------------- #
def test_image_describer_thanh_cong(anh_png):
    tool = make_image_describer_tool(
        vision_llm=FakeStructuredModel(payload={"image_description": "A red square."})
    )
    out = tool.invoke({"text": f"describe this: {anh_png}"})
    assert out == "A red square."


def test_image_describer_khong_co_anh_tra_loi_chuan():
    tool = make_image_describer_tool(vision_llm=FakeStructuredModel(payload={"image_description": "x"}))
    out = tool.invoke({"text": "mô tả giúp tôi"})
    assert out.startswith(ERROR_PREFIX) and "NO_IMAGE_REF" in out


def test_image_describer_llm_loi_van_khong_raise(anh_png):
    tool = make_image_describer_tool(vision_llm=FakeStructuredModel(payload={}, should_fail=True))
    out = tool.invoke({"text": anh_png})
    assert out.startswith(ERROR_PREFIX) and "VISION_LLM_FAILED" in out


def test_image_describer_mac_dinh_khong_return_direct():
    """return_direct=True sẽ cắt ngang vòng ReAct -> agent không kết hợp được 2 tool."""
    tool = make_image_describer_tool(vision_llm=FakeStructuredModel(payload={"image_description": "x"}))
    assert tool.return_direct is False


# --------------------------- detect_and_count ------------------------------ #
def test_dem_vat_the_tra_ve_json_dung_dinh_dang(anh_png):
    detector = fake_detector_factory(
        [("dog", 0.94, (287, 73, 618, 445)), ("dog", 0.84, (159, 120, 369, 418)), ("cat", 0.51, (1, 2, 3, 4))]
    )
    tool = make_detect_and_count_tool(detector=detector)
    payload = json.loads(tool.invoke({"text": f"how many dogs in {anh_png}"}))
    assert payload["counting"] == {"dog": 2, "cat": 1}
    assert payload["detections"][0] == {
        "class": "dog",
        "confidence": 0.94,
        "bbox": [287, 73, 618, 445],
    }


def test_khong_phat_hien_gi_van_tra_json_hop_le(anh_png):
    tool = make_detect_and_count_tool(detector=fake_detector_factory([]))
    payload = json.loads(tool.invoke({"text": anh_png}))
    assert payload["counting"] == {} and payload["detections"] == []


def test_yolo_loi_thi_tra_error_chu_khong_raise(anh_png):
    def _bung(_ref):
        raise RuntimeError("CUDA out of memory")

    tool = make_detect_and_count_tool(detector=_bung)
    out = tool.invoke({"text": anh_png})
    assert out.startswith(ERROR_PREFIX) and "YOLO_INFERENCE_FAILED" in out


def test_thieu_ultralytics_bao_loi_de_hieu(anh_png):
    def _thieu(_ref):
        raise ImportError("No module named 'ultralytics'")

    tool = make_detect_and_count_tool(detector=_thieu)
    out = tool.invoke({"text": anh_png})
    assert "YOLO_NOT_INSTALLED" in out and "pip install ultralytics" in out


# --------------------------- default_detector ------------------------------ #
class _FakeYoloModel:
    """Model YOLO giả — chỉ ghi lại tham số nó nhận được, không suy luận gì cả."""

    def __init__(self):
        self.calls = []

    def __call__(self, image_ref, **kwargs):
        self.calls.append({"image_ref": image_ref, **kwargs})
        return []


class _FakeSettings:
    """Đứng thay app.core.config.settings — chỉ có đúng field default_detector cần."""

    def __init__(self, yolo_conf: float, yolo_iou: float = 0.45, yolo_weights: str = "yolo11n.pt"):
        self.yolo_conf = yolo_conf
        self.yolo_iou = yolo_iou
        self.yolo_weights = yolo_weights


def test_default_detector_truyen_dung_conf_xuong_model(monkeypatch):
    """Khóa lại fix: thiếu dòng conf=settings.yolo_conf thì test này phải đỏ.

    Trước fix, default_detector() gọi model(image_ref, verbose=False) — không hề
    truyền `conf`, nên dù settings.yolo_conf là bao nhiêu cũng không có tác dụng.
    """
    fake_model = _FakeYoloModel()
    monkeypatch.setattr(vision_tools, "_load_yolo", lambda weights: fake_model)
    monkeypatch.setattr(vision_tools, "settings", _FakeSettings(yolo_conf=0.42, yolo_iou=0.5))

    default_detector("bat_ky_anh_nao.jpg")

    assert len(fake_model.calls) == 1
    assert fake_model.calls[0]["conf"] == 0.42
    assert fake_model.calls[0]["iou"] == 0.5
    assert fake_model.calls[0]["verbose"] is False


def test_default_detector_conf_khac_nhau_thi_truyen_khac_nhau(monkeypatch):
    """Đổi YOLO_CONF (qua settings) phải phản ánh đúng vào lời gọi model — không bị cache/giữ giá trị cũ."""
    fake_model = _FakeYoloModel()
    monkeypatch.setattr(vision_tools, "_load_yolo", lambda weights: fake_model)

    monkeypatch.setattr(vision_tools, "settings", _FakeSettings(yolo_conf=0.1))
    default_detector("anh_1.jpg")

    monkeypatch.setattr(vision_tools, "settings", _FakeSettings(yolo_conf=0.9))
    default_detector("anh_2.jpg")

    assert fake_model.calls[0]["conf"] == 0.1
    assert fake_model.calls[1]["conf"] == 0.9


def test_parse_yolo_results_bbox_dung_thu_tu_xyxy():
    results = fake_detector_factory([("person", 0.9, (10, 20, 30, 40))])("x")
    assert parse_yolo_results(results)["detections"][0]["bbox"] == [10, 20, 30, 40]