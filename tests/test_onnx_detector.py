"""Test bộ phát hiện vật thể chạy bằng ONNX Runtime (đường dùng khi deploy).

Không cần mạng, không cần API key, không cần torch — chỉ cần `onnxruntime` và
file `yolo11n.onnx` ở gốc repo. Thiếu một trong hai thì test tự bỏ qua chứ không
báo đỏ, để người chưa cài không bị chặn (quy tắc TS-03).
"""

from __future__ import annotations

from pathlib import Path

import pytest

GOC_REPO = Path(__file__).resolve().parent.parent
MODEL = GOC_REPO / "yolo11n.onnx"
ANH_CHIM = GOC_REPO / "assets" / "chim.jpg"
ANH_MEO = GOC_REPO / "assets" / "cat.jpg"
ANH_NHIEU_CHO = GOC_REPO / "assets" / "test.jpeg"

pytest.importorskip("onnxruntime", reason="chưa cài onnxruntime")
pytestmark = pytest.mark.skipif(
    not MODEL.is_file(), reason="chưa có yolo11n.onnx ở gốc repo"
)


@pytest.fixture(scope="module")
def detect():
    from app.agents.vision_agent.onnx_detector import onnx_detect

    def _chay(anh: Path, conf: float = 0.25, iou: float = 0.45):
        return onnx_detect(str(anh), str(MODEL), conf, iou)

    return _chay


def _gom(results):
    """Rút kết quả về dạng dễ so sánh: [(tên lớp, độ tin cậy, [x1,y1,x2,y2])]."""
    ra = []
    for r in results:
        for b in r.boxes:
            ra.append(
                (
                    r.names[int(b.cls[0])],
                    float(b.conf[0]),
                    [float(v) for v in b.xyxy[0]],
                )
            )
    return ra


def test_ket_qua_dung_dinh_dang_ultralytics(detect):
    """parse_yolo_results() đọc được kết quả này mà không phải sửa gì."""
    from app.agents.vision_agent.tools import parse_yolo_results

    payload = parse_yolo_results(detect(ANH_CHIM))
    assert payload["counting"] == {"bird": 1}
    assert len(payload["detections"]) == 1
    d = payload["detections"][0]
    assert set(d) == {"class", "confidence", "bbox"}
    assert len(d["bbox"]) == 4


def test_nhan_dien_dung_con_chim(detect):
    ra = _gom(detect(ANH_CHIM))
    assert len(ra) == 1
    ten, tin_cay, _ = ra[0]
    assert ten == "bird"
    assert tin_cay > 0.8


def test_dem_dung_bon_con_cho(detect):
    """Ảnh nhiều vật thể cùng loại nằm sát nhau — đây là ca NMS dễ sai nhất."""
    ra = _gom(detect(ANH_NHIEU_CHO))
    assert [t for t, _, _ in ra] == ["dog"] * 4


def test_khung_nam_gon_trong_anh_goc(detect):
    """Gỡ letterbox sai thì toạ độ tràn ra ngoài ảnh hoặc lệch tỉ lệ."""
    from PIL import Image

    with Image.open(ANH_MEO) as im:
        rong, cao = im.size

    for _, _, (x1, y1, x2, y2) in _gom(detect(ANH_MEO)):
        assert 0 <= x1 < x2 <= rong
        assert 0 <= y1 < y2 <= cao


def test_nguong_tin_cay_cao_thi_loai_bot(detect):
    it_hon = _gom(detect(ANH_NHIEU_CHO, conf=0.85))
    nhieu_hon = _gom(detect(ANH_NHIEU_CHO, conf=0.25))
    assert len(it_hon) < len(nhieu_hon)
    assert all(tin_cay > 0.85 for _, tin_cay, _ in it_hon)


def test_khong_co_vat_the_thi_tra_danh_sach_rong(detect):
    """Ngưỡng bất khả thi -> phải trả kết quả rỗng chứ không được nổ lỗi."""
    payload_rong = detect(ANH_CHIM, conf=0.999)
    assert _gom(payload_rong) == []

    from app.agents.vision_agent.tools import parse_yolo_results

    assert parse_yolo_results(payload_rong) == {"counting": {}, "detections": []}


def test_thieu_file_model_thi_bao_ro_rang():
    from app.agents.vision_agent.onnx_detector import onnx_detect

    with pytest.raises(FileNotFoundError, match="yolo export"):
        onnx_detect(str(ANH_CHIM), str(GOC_REPO / "khong_ton_tai.onnx"))
