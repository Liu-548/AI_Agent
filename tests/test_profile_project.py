"""Mục 4 (hồ sơ người dùng) + mục 6 (project). SQLite tạm, graph giả, không gọi LLM."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from tests.test_api_khach import _nap  # noqa: E402


class _GraphGhiLai:
    da_nhan = []

    @classmethod
    def invoke(cls, state, config=None):
        cls.da_nhan.append(state["messages"])
        return {"messages": []}


@pytest.fixture()
def moi_truong(monkeypatch, tmp_path):
    api_mod, _, store_mod = _nap(monkeypatch, tmp_path, bat_dang_nhap=False)
    _GraphGhiLai.da_nhan = []
    monkeypatch.setattr(api_mod, "_get_supervisor_graph", lambda: _GraphGhiLai)
    return TestClient(api_mod.app), store_mod


def test_ho_so_luu_cat_do_dai_chen_vao_dau_lich_su_va_xoa_duoc(moi_truong):
    client, _ = moi_truong
    r = client.put("/api/profile", data={"user_id": "u1", "display_name": "Tuấn",
                                         "linh_vuc": "sinh viên CNTT", "ghi_chu": "x" * 900})
    assert r.status_code == 200 and len(r.json()["profile"]["ghi_chu"]) == 500

    client.post("/api/ask", data={"question": "Xin chào", "user_id": "u1"})
    dau = _GraphGhiLai.da_nhan[-1]
    assert "name: Tuấn" in dau[0]["content"] and "field: sinh viên CNTT" in dau[0]["content"]
    assert len(dau[0]["content"]) < 700  # đã cắt
    assert dau[-1]["content"] == "Xin chào"

    client.delete("/api/profile?user_id=u1")
    assert client.get("/api/profile?user_id=u1").json()["profile"] is None
    client.post("/api/ask", data={"question": "Lần 2", "user_id": "u1"})
    assert len(_GraphGhiLai.da_nhan[-1]) == 1  # không còn ngữ cảnh


def test_project_tao_gan_huong_dan_va_xoa_khong_mat_hoi_thoai(moi_truong):
    client, store_mod = moi_truong
    p = client.post("/api/projects", data={"user_id": "u1", "name": "Luận văn",
                                           "instructions": "Luôn trả lời kèm trích dẫn"}).json()
    # Hội thoại mới tạo thẳng trong project -> hướng dẫn được chèn
    r = client.post("/api/ask", data={"question": "Hỏi A", "user_id": "u1", "project_id": p["id"]}).json()
    assert "Luôn trả lời kèm trích dẫn" in _GraphGhiLai.da_nhan[-1][0]["content"]
    ds = client.get("/api/conversations?user_id=u1").json()["conversations"]
    assert ds[0]["project_id"] == p["id"]

    # Hỏi tiếp trong hội thoại đó vẫn có hướng dẫn
    client.post("/api/ask", data={"question": "Hỏi B", "user_id": "u1", "conversation_id": r["conversation_id"]})
    assert "Luôn trả lời" in _GraphGhiLai.da_nhan[-1][0]["content"]

    # Người khác không gắn được vào project của u1, không thấy project của u1
    assert client.get("/api/projects?user_id=u2").json()["projects"] == []
    assert client.patch(f"/api/projects/{p['id']}", data={"user_id": "u2", "name": "x"}).status_code == 404

    # Gỡ khỏi project, gắn lại, rồi xoá project: hội thoại còn nguyên
    client.patch(f"/api/conversations/{r['conversation_id']}", data={"user_id": "u1", "project_id": ""})
    assert client.get("/api/conversations?user_id=u1").json()["conversations"][0]["project_id"] is None
    client.patch(f"/api/conversations/{r['conversation_id']}", data={"user_id": "u1", "project_id": p["id"]})
    assert client.delete(f"/api/projects/{p['id']}?user_id=u1").status_code == 200
    ds = client.get("/api/conversations?user_id=u1").json()["conversations"]
    assert len(ds) == 1 and ds[0]["project_id"] is None
    assert len(store_mod.lay_tin_nhan(r["conversation_id"])) == 4
