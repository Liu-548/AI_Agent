"""Gửi NHIỀU ảnh (2-5) trong MỘT tin nhắn để so sánh.

Trước đây: chọn ảnh thứ hai thì ảnh thứ nhất bị thay mất, server cũng chỉ nhận một
file. Lời hứa bây giờ:
  - /api/ask nhận nhiều ảnh (trường `files`), mỗi ảnh có số riêng trong bộ nhớ ảnh
    (IMG1, IMG2, IMG3...), supervisor thấy "Images: IMG1, IMG2, IMG3".
  - Supervisor gọi vision_agent_tool MỘT lần với cả ba mã -> một lượt model nhìn cả ba.
  - Lịch sử giữ đủ ảnh nhỏ + số của từng ảnh để mở lại hội thoại vẫn thấy.
  - Khách chưa đăng nhập gửi nhiều ảnh vẫn so sánh được (đánh số riêng lượt đó).
  - Quá 5 ảnh -> 400. Một ảnh -> y như cũ.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage

from tests.fakes import tool_call
from tests.test_image_memory import _anh, he  # noqa: F401


class _LlmSoSanh:
    def __init__(self):
        self.lan_goi = []

    def invoke(self, messages):
        self.lan_goi.append(messages)
        return AIMessage(content="Ảnh 1 cam, Ảnh 2 trắng, Ảnh 3 đen.")


def _so_anh_trong(msgs):
    return sum(1 for p in msgs[1].content if p.get("type") == "image_url")


def _gui_nhieu(he, cau_hoi, ten_anh, headers):  # noqa: F811
    files = [("files", (f"{t}.png", _anh(t), "image/png")) for t in ten_anh]
    data = {"question": cau_hoi}
    if he.cid and headers:
        data["conversation_id"] = he.cid
    return he.client.post("/api/ask", data=data, files=files, headers=headers or {})


def _kich_ban_so_sanh(he, ma):  # noqa: F811
    he.model.kich_ban(
        AIMessage(content="", tool_calls=[tool_call("vision_agent_tool", {"query": "So sánh", "image_path": ma}, "s1")]),
        AIMessage(content="Đã so sánh."),
    )


def test_ba_anh_mot_tin_nhan_duoc_so_sanh_mot_luot(he, monkeypatch):  # noqa: F811
    llm = _LlmSoSanh()
    monkeypatch.setattr("app.core.llm.get_llm", lambda role, *a, **k: llm if role == "describe" else None)
    _kich_ban_so_sanh(he, "IMG1,IMG2,IMG3")

    r = _gui_nhieu(he, "So sánh ba ảnh này", ["meo_cam", "cho_trang", "meo_den"], he.headers)
    assert r.status_code == 200, r.text
    tra_loi = r.json()
    he.cid = tra_loi["conversation_id"]

    assert "Images: IMG1, IMG2, IMG3" in he.model.tin_nguoi_dung_cuoi
    assert tra_loi["image_nos"] == [1, 2, 3]
    assert tra_loi["compared_images"] == [1, 2, 3]
    # đúng MỘT lượt model, nhìn cả ba ảnh
    assert len(llm.lan_goi) == 1 and _so_anh_trong(llm.lan_goi[0]) == 3

    # bộ nhớ ảnh có đủ 3 ảnh, đúng thứ tự gửi
    ds = he.store.danh_sach_anh(he.cid, 20)
    assert [a["stt"] for a in ds] == [1, 2, 3]
    # tin nhắn người dùng giữ đủ ảnh nhỏ + số ảnh để mở lại hội thoại
    tin = he.store.lay_tin_nhan(he.cid)[0]["extras"]
    assert tin["image_nos"] == [1, 2, 3] and len(tin["image_thumbs_base64"]) == 3
    assert tin["image_no"] == 1  # trường cũ vẫn còn cho UI cũ


def test_anh_moi_tiep_theo_duoc_danh_so_noi_tiep(he, monkeypatch):  # noqa: F811
    llm = _LlmSoSanh()
    monkeypatch.setattr("app.core.llm.get_llm", lambda role, *a, **k: llm if role == "describe" else None)
    he.gui_anh("meo_cam", 1)
    _kich_ban_so_sanh(he, "IMG2,IMG3")
    r = _gui_nhieu(he, "So sánh hai ảnh mới", ["cho_trang", "cho_nau"], he.headers)
    assert r.json()["image_nos"] == [2, 3]
    assert "Images: IMG2, IMG3" in he.model.tin_nguoi_dung_cuoi


def test_khach_chua_dang_nhap_van_so_sanh_duoc(he, monkeypatch):  # noqa: F811
    llm = _LlmSoSanh()
    monkeypatch.setattr("app.core.llm.get_llm", lambda role, *a, **k: llm if role == "describe" else None)
    _kich_ban_so_sanh(he, "IMG1,IMG2")
    r = _gui_nhieu(he, "So sánh", ["meo_cam", "meo_den"], headers=None)
    assert r.status_code == 200, r.text
    assert "Images: IMG1, IMG2" in he.model.tin_nguoi_dung_cuoi
    assert r.json()["compared_images"] == [1, 2]
    assert _so_anh_trong(llm.lan_goi[0]) == 2


def test_qua_nam_anh_bi_tu_choi(he):  # noqa: F811
    r = _gui_nhieu(he, "So sánh", ["meo_cam", "cho_trang", "meo_den", "cho_nau", "cho_xam", "meo_cam"], he.headers)
    assert r.status_code == 400


def test_mot_anh_nhu_cu(he):  # noqa: F811
    tra_loi = he.gui_anh("meo_cam", 1)
    assert tra_loi["image_no"] == 1 and "image_nos" not in tra_loi
    assert "Image: IMG1" in he.model.tin_nguoi_dung_cuoi
