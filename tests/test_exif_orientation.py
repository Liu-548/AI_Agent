"""Ảnh dọc chụp từ điện thoại: pixel lưu nằm ngang + cờ EXIF Orientation.

Trước khi sửa: đường ONNX mở ảnh mà không xoay theo cờ nên model nhìn ảnh nằm ngang,
khung phát hiện lệch khỏi vật thể và số đếm sai. Test dưới đây dựng lại đúng tình
huống đó bằng ảnh tổng hợp (không cần ảnh thật, không cần model).
"""

from __future__ import annotations

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageOps  # noqa: E402

from app.agents.vision_agent.image_utils import chuan_hoa_huong_anh, mo_anh_dung_huong  # noqa: E402


def _anh_dung(w=60, h=100):
    """Ảnh ĐÚNG CHIỀU (dọc): nửa trên đỏ, nửa dưới xanh."""
    im = Image.new("RGB", (w, h), (0, 0, 255))
    im.paste((255, 0, 0), (0, 0, w, h // 2))
    return im


def _file_kieu_dien_thoai(duong_dan, orient=6):
    """Pixel lưu = ảnh đúng xoay ngược lại, kèm cờ EXIF để trình xem xoay lại."""
    dung = _anh_dung()
    nguoc = {6: Image.ROTATE_90, 8: Image.ROTATE_270, 3: Image.ROTATE_180}[orient]
    luu = dung.transpose(nguoc)
    ex = Image.Exif()
    ex[0x0112] = orient
    luu.save(duong_dan, "JPEG", quality=95, exif=ex.tobytes())
    return dung


@pytest.mark.parametrize("orient", [3, 6, 8])
def test_mo_anh_dung_huong_xoay_theo_co_exif(tmp_path, orient):
    p = tmp_path / "dt.jpg"
    dung = _file_kieu_dien_thoai(p, orient)
    # cảnh báo nền: mở thẳng bằng Pillow thì KHÔNG đúng chiều (đây là lỗi cũ)
    if orient in (6, 8):
        with Image.open(p) as im0:
            assert im0.size == (100, 60)
    ra = mo_anh_dung_huong(p)
    assert ra.size == dung.size == (60, 100)
    # nửa trên vẫn đỏ, nửa dưới vẫn xanh (cho phép sai số nén JPEG)
    r_tren = ra.getpixel((30, 10))
    r_duoi = ra.getpixel((30, 90))
    assert r_tren[0] > 200 and r_tren[2] < 80
    assert r_duoi[2] > 200 and r_duoi[0] < 80


@pytest.mark.parametrize("orient", [3, 6, 8])
def test_chuan_hoa_huong_anh_ghi_de_file_va_xoa_co(tmp_path, orient):
    p = tmp_path / "dt.jpg"
    _file_kieu_dien_thoai(p, orient)
    assert chuan_hoa_huong_anh(p) is True
    with Image.open(p) as im:
        assert im.size == (60, 100)
        assert im.getexif().get(0x0112, 1) == 1
    # gọi lần hai: không còn gì để sửa, không nén lại
    truoc = p.read_bytes()
    assert chuan_hoa_huong_anh(p) is False
    assert p.read_bytes() == truoc


def test_anh_khong_co_co_exif_khong_bi_dong_vao(tmp_path):
    p = tmp_path / "thuong.jpg"
    _anh_dung().save(p, "JPEG")
    truoc = p.read_bytes()
    assert chuan_hoa_huong_anh(p) is False
    assert p.read_bytes() == truoc


def test_file_hong_khong_raise(tmp_path):
    p = tmp_path / "hong.jpg"
    p.write_bytes(b"day khong phai anh")
    assert chuan_hoa_huong_anh(p) is False
    assert chuan_hoa_huong_anh(tmp_path / "khong-ton-tai.jpg") is False


def test_onnx_doc_anh_xoay_theo_exif(tmp_path):
    pytest.importorskip("numpy")
    from app.agents.vision_agent.onnx_detector import _doc_anh

    p = tmp_path / "dt.jpg"
    _file_kieu_dien_thoai(p, 6)
    assert _doc_anh(str(p)).size == (60, 100)


def test_ve_khung_len_anh_xoay_dung_chieu(tmp_path):
    from app.agents.vision_agent.image_utils import draw_detections

    p = tmp_path / "dt.jpg"
    _file_kieu_dien_thoai(p, 6)
    out = tmp_path / "ra.jpg"
    kq = draw_detections(str(p), [{"class": "x", "confidence": 0.9, "bbox": [5, 5, 50, 50]}], str(out))
    assert kq == str(out)
    with Image.open(out) as im:
        assert im.size == (60, 100)


def test_upload_xoay_that_su_truoc_khi_vao_pipeline(tmp_path, monkeypatch):
    """Chạm đúng chỗ nhận ảnh của API: file lưu xuống đĩa đã đúng chiều."""
    pytest.importorskip("fastapi")
    import io

    from fastapi import UploadFile

    from app import api

    monkeypatch.setattr(api, "UPLOAD_DIR", tmp_path)
    nguon = tmp_path / "nguon.jpg"
    _file_kieu_dien_thoai(nguon, 6)
    with nguon.open("rb") as f:
        up = UploadFile(file=io.BytesIO(f.read()), filename="IMG_0001.JPG")
    dest = api._save_upload(up)
    with Image.open(dest) as im:
        assert im.size == (60, 100)
    # ảnh thu nhỏ cũng đúng chiều (dọc: cao hơn rộng)
    import base64

    thumb = Image.open(io.BytesIO(base64.b64decode(api._thumbnail_base64(dest))))
    assert thumb.size[1] > thumb.size[0]
