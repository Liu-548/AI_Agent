"""Phát hiện vật thể bằng ONNX Runtime — bản thay thế cho torch khi deploy.

Vì sao có file này: `ultralytics` kéo theo `torch`, mà đo thực tế trên một ảnh
thì đỉnh RAM là ~780MB (bản CUDA) / ~500MB (bản CPU). Gói Free của Render chỉ
cho 512MB cho CẢ tiến trình, tính luôn FastAPI và uvicorn — nên bản deploy luôn
bị kill giữa chừng. Cùng model đó chạy qua ONNX Runtime chỉ tốn ~123MB.

Model dùng ở đây là CHÍNH `yolo11n.pt` đã xuất sang `.onnx`, không phải model
khác — cùng trọng số, cùng kết quả. Xuất một lần trên máy có ultralytics:

    yolo export model=yolo11n.pt format=onnx imgsz=640 opset=12

Tên 80 lớp COCO nằm sẵn trong metadata của file .onnx nên không phải chép tay.
"""

from __future__ import annotations

import ast
import io
import os
from functools import lru_cache
from typing import Any, List, Optional, Tuple

import numpy as np
import requests

REQUEST_TIMEOUT = 15
MAU_DEM = (114, 114, 114)  # xám trung tính, đúng màu ultralytics dùng khi letterbox


# --------------------------------------------------------------------------- #
# Vỏ bọc cho kết quả — để parse_yolo_results() trong tools.py dùng lại y nguyên
# --------------------------------------------------------------------------- #
class _Box:
    """Bắt chước đúng phần `box.cls[0]`, `box.conf[0]`, `box.xyxy[0]` mà
    parse_yolo_results() đọc. Nhờ vậy đổi sang ONNX không phải sửa một dòng nào
    trong tools.py, và test cũ vẫn đúng."""

    __slots__ = ("cls", "conf", "xyxy")

    def __init__(self, cls_id: int, conf: float, xyxy: List[float]):
        self.cls = [cls_id]
        self.conf = [conf]
        self.xyxy = [xyxy]


class _Result:
    __slots__ = ("boxes", "names")

    def __init__(self, boxes: List[_Box], names: dict):
        self.boxes = boxes
        self.names = names


# --------------------------------------------------------------------------- #
# Nạp model
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=2)
def _nap_phien(weights: str):
    """Nạp file .onnx một lần duy nhất cho cả tiến trình.

    Import onnxruntime ở trong hàm (không phải đầu file) để ai chỉ làm Research
    hay Supervisor không cần cài thêm gói nào — đúng cách tools.py đang làm với
    ultralytics.
    """
    import onnxruntime as ort

    if not os.path.exists(weights):
        raise FileNotFoundError(
            f"Không thấy file model {weights!r}. Xuất từ máy có ultralytics bằng:\n"
            f"    yolo export model=yolo11n.pt format=onnx imgsz=640 opset=12"
        )

    phien = ort.InferenceSession(weights, providers=["CPUExecutionProvider"])
    meta = phien.get_modelmeta().custom_metadata_map
    ten_lop = ast.literal_eval(meta.get("names", "{}"))
    canh = 640
    if meta.get("imgsz"):
        canh = int(ast.literal_eval(meta["imgsz"])[0])
    return phien, ten_lop, canh


# --------------------------------------------------------------------------- #
# Tiền xử lý / hậu xử lý
# --------------------------------------------------------------------------- #
def _doc_anh(image_ref: str):
    from PIL import Image

    if image_ref.lower().startswith("http"):
        resp = requests.get(image_ref, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    return Image.open(image_ref).convert("RGB")


def _letterbox(im, canh: int) -> Tuple[np.ndarray, float, int, int]:
    """Thu ảnh về khung vuông mà GIỮ NGUYÊN tỉ lệ, phần thừa đệm xám.

    Nếu kéo méo ảnh cho vừa khung vuông thì khung phát hiện trả về cũng méo
    theo, toạ độ vẽ lên ảnh gốc sẽ lệch — lỗi rất khó nhìn ra vì ảnh vẫn có
    khung, chỉ là khung không ôm đúng con vật.
    """
    from PIL import Image

    w0, h0 = im.size
    ty_le = min(canh / w0, canh / h0)
    w, h = int(round(w0 * ty_le)), int(round(h0 * ty_le))
    dx, dy = (canh - w) // 2, (canh - h) // 2

    nen = Image.new("RGB", (canh, canh), MAU_DEM)
    nen.paste(im.resize((w, h), Image.BILINEAR), (dx, dy))

    x = np.asarray(nen, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
    return np.ascontiguousarray(x), ty_le, dx, dy


def _nms(khung: np.ndarray, diem: np.ndarray, nguong_iou: float) -> List[int]:
    """Non-Maximum Suppression thuần numpy: bỏ các khung chồng nhau quá nhiều.

    Không dùng được torchvision.ops.nms vì cả mục đích của file này là không
    phải cài torch.
    """
    x1, y1, x2, y2 = khung[:, 0], khung[:, 1], khung[:, 2], khung[:, 3]
    dien_tich = (x2 - x1) * (y2 - y1)
    thu_tu = diem.argsort()[::-1]

    giu: List[int] = []
    while thu_tu.size > 0:
        i = thu_tu[0]
        giu.append(int(i))
        if thu_tu.size == 1:
            break
        con_lai = thu_tu[1:]

        xx1 = np.maximum(x1[i], x1[con_lai])
        yy1 = np.maximum(y1[i], y1[con_lai])
        xx2 = np.minimum(x2[i], x2[con_lai])
        yy2 = np.minimum(y2[i], y2[con_lai])
        chong = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        iou = chong / (dien_tich[i] + dien_tich[con_lai] - chong + 1e-9)

        thu_tu = con_lai[iou <= nguong_iou]
    return giu


# --------------------------------------------------------------------------- #
# Hàm chính
# --------------------------------------------------------------------------- #
def onnx_detect(
    image_ref: str,
    weights: str = "yolo11n.onnx",
    conf: float = 0.25,
    iou: float = 0.45,
) -> List[Any]:
    """Trả về danh sách kết quả CÙNG HÌNH DẠNG với ultralytics, để
    `parse_yolo_results()` và `draw_detections()` dùng lại không cần sửa."""
    phien, ten_lop, canh = _nap_phien(weights)

    im = _doc_anh(image_ref)
    w0, h0 = im.size
    x, ty_le, dx, dy = _letterbox(im, canh)

    raw = phien.run(None, {phien.get_inputs()[0].name: x})[0]
    # (1, 84, 8400) -> (8400, 84): 4 số toạ độ + 80 điểm số của 80 lớp
    du_doan = raw[0].T

    toa_do = du_doan[:, :4]
    diem_lop = du_doan[:, 4:]
    diem = diem_lop.max(axis=1)
    lop = diem_lop.argmax(axis=1)

    giu = diem > conf
    if not giu.any():
        return [_Result([], ten_lop)]
    toa_do, diem, lop = toa_do[giu], diem[giu], lop[giu]

    # Model trả về (tâm_x, tâm_y, rộng, cao) -> đổi sang (x1, y1, x2, y2)
    cx, cy, w, h = toa_do[:, 0], toa_do[:, 1], toa_do[:, 2], toa_do[:, 3]
    khung = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)

    # NMS theo TỪNG LỚP: cộng một khoảng lệch lớn theo id lớp để hai vật thể
    # khác loại nằm chồng nhau (người ôm chó) không triệt tiêu lẫn nhau.
    lech = lop.astype(np.float32) * 8192.0
    khung_lech = khung + lech[:, None]
    chi_so = _nms(khung_lech, diem, iou)

    # Gỡ letterbox: trừ phần đệm rồi chia tỉ lệ để về đúng toạ độ ảnh gốc.
    ket_qua: List[_Box] = []
    for i in chi_so:
        x1 = (khung[i, 0] - dx) / ty_le
        y1 = (khung[i, 1] - dy) / ty_le
        x2 = (khung[i, 2] - dx) / ty_le
        y2 = (khung[i, 3] - dy) / ty_le
        ket_qua.append(
            _Box(
                int(lop[i]),
                round(float(diem[i]), 3),
                [
                    max(0.0, min(x1, w0)),
                    max(0.0, min(y1, h0)),
                    max(0.0, min(x2, w0)),
                    max(0.0, min(y2, h0)),
                ],
            )
        )
    return [_Result(ket_qua, ten_lop)]
