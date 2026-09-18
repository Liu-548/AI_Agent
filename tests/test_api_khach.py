"""Test hai chế độ của giao diện web: khách vãng lai và người đã đăng nhập.

Lời hứa của tính năng:
  - Khách (không đăng nhập) VẪN hỏi được agent, nhưng KHÔNG lưu lại gì.
  - Người đã đăng nhập thì mọi lượt hỏi-đáp được lưu theo tài khoản Google.
  - Không ai đọc được hội thoại của người khác, kể cả khi tự khai `user_id`.

Không gọi mạng, không cần API key: graph của supervisor bị thay bằng một graph
giả trả lời cố định (cùng tinh thần với tests/fakes.py).
"""

from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

CLIENT_ID = "123456789-test.apps.googleusercontent.com"
BI_MAT = "bi_mat_test_" + "0123456789abcdef"

A = {"sub": "sub_A", "email": "a@gmail.com", "name": "Ban A", "picture": ""}
B = {"sub": "sub_B", "email": "b@gmail.com", "name": "Ban B", "picture": ""}


class _GraphGia:
    """Đứng thay supervisor: không gọi LLM, không import langchain.

    Trả về trạng thái rỗng là đủ, vì các hàm bóc tách kết quả cũng bị thay ở
    `_nap()` — test này chỉ quan tâm việc CÓ LƯU hay KHÔNG LƯU, không quan tâm
    nội dung câu trả lời.
    """

    @staticmethod
    def invoke(state, config=None):
        return {"messages": []}


def _nap(monkeypatch, tmp_path, bat_dang_nhap=True):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'web.db'}")
    for ten, gia_tri in (("GOOGLE_CLIENT_ID", CLIENT_ID), ("SESSION_SECRET", BI_MAT)):
        if bat_dang_nhap:
            monkeypatch.setenv(ten, gia_tri)
        else:
            monkeypatch.delenv(ten, raising=False)

    import app.core.config as cfg

    importlib.reload(cfg)
    import app.store as store_mod
    import app.auth as auth_mod
    import app.api as api_mod

    importlib.reload(store_mod)
    importlib.reload(auth_mod)
    importlib.reload(api_mod)

    # Chặn mọi đường ra LLM: test này chỉ quan tâm chuyện lưu hay không lưu.
    monkeypatch.setattr(api_mod, "_get_supervisor_graph", lambda: _GraphGia)
    monkeypatch.setattr(api_mod, "_final_answer", lambda ket_qua: "Tra loi gia")
    monkeypatch.setattr(api_mod, "_collect_tool_outputs", lambda ket_qua: {})
    monkeypatch.setattr(api_mod, "_extract_agent_trace", lambda ket_qua: ([], []))

    return api_mod, auth_mod, store_mod


def _bearer(auth_mod, ho_so):
    return {"Authorization": "Bearer " + auth_mod.tao_phieu(ho_so)}


# ------------------------------- khách ------------------------------------- #
def test_khach_van_hoi_duoc_nhung_khong_luu_gi(monkeypatch, tmp_path):
    api_mod, _, store_mod = _nap(monkeypatch, tmp_path)
    client = TestClient(api_mod.app)

    r = client.post("/api/ask", data={"question": "Xin chao"})
    assert r.status_code == 200
    assert r.json()["answer"] == "Tra loi gia"
    # Không có conversation_id nghĩa là không có gì được lưu lại.
    assert "conversation_id" not in r.json()

    with store_mod.get_engine().begin() as conn:
        from sqlalchemy import func, select

        so_hoi_thoai = conn.execute(
            select(func.count()).select_from(store_mod.conversations)
        ).scalar()
    assert so_hoi_thoai == 0


def test_khach_tu_khai_user_id_cung_khong_luu(monkeypatch, tmp_path):
    """Client tự gửi user_id để 'ép' server lưu -> phải bị bỏ qua hoàn toàn."""
    api_mod, _, store_mod = _nap(monkeypatch, tmp_path)
    client = TestClient(api_mod.app)

    client.post("/api/ask", data={"question": "Xin chao", "user_id": "sub_A"})

    from sqlalchemy import func, select

    with store_mod.get_engine().begin() as conn:
        assert conn.execute(
            select(func.count()).select_from(store_mod.conversations)
        ).scalar() == 0


def test_khach_xem_danh_sach_thi_rong_chu_khong_loi(monkeypatch, tmp_path):
    api_mod, _, store_mod = _nap(monkeypatch, tmp_path)
    store_mod.tao_hoi_thoai("sub_A", "Hoi thoai cua A")
    client = TestClient(api_mod.app)

    r = client.get("/api/conversations")
    assert r.status_code == 200
    assert r.json() == {"conversations": []}


def test_khach_khong_mo_duoc_hoi_thoai_cua_nguoi_khac(monkeypatch, tmp_path):
    api_mod, _, store_mod = _nap(monkeypatch, tmp_path)
    cua_a = store_mod.tao_hoi_thoai("sub_A", "Hoi thoai cua A")
    client = TestClient(api_mod.app)

    assert client.get(f"/api/conversations/{cua_a['id']}?user_id=sub_A").status_code == 401
    assert client.delete(f"/api/conversations/{cua_a['id']}?user_id=sub_A").status_code == 401


# --------------------------- người đã đăng nhập ----------------------------- #
def test_dang_nhap_thi_luu_lich_su_theo_tai_khoan(monkeypatch, tmp_path):
    api_mod, auth_mod, store_mod = _nap(monkeypatch, tmp_path)
    client = TestClient(api_mod.app)

    r = client.post("/api/ask", data={"question": "Cau hoi cua A"}, headers=_bearer(auth_mod, A))
    assert r.status_code == 200
    cid = r.json()["conversation_id"]

    # Hỏi tiếp trong cùng hội thoại -> vẫn đúng hội thoại đó, không đẻ thêm.
    r2 = client.post(
        "/api/ask",
        data={"question": "Hoi tiep", "conversation_id": cid},
        headers=_bearer(auth_mod, A),
    )
    assert r2.json()["conversation_id"] == cid

    ds = client.get("/api/conversations", headers=_bearer(auth_mod, A)).json()["conversations"]
    assert len(ds) == 1 and ds[0]["message_count"] == 4  # 2 lượt hỏi + 2 lượt đáp


def test_nguoi_khac_khong_thay_hoi_thoai_cua_minh(monkeypatch, tmp_path):
    api_mod, auth_mod, store_mod = _nap(monkeypatch, tmp_path)
    client = TestClient(api_mod.app)

    r = client.post("/api/ask", data={"question": "Rieng tu"}, headers=_bearer(auth_mod, A))
    cid = r.json()["conversation_id"]

    assert client.get("/api/conversations", headers=_bearer(auth_mod, B)).json() == {
        "conversations": []
    }
    assert client.get(f"/api/conversations/{cid}", headers=_bearer(auth_mod, B)).status_code == 404


# ------------------------ chưa bật đăng nhập (chế độ cũ) -------------------- #
def test_chua_bat_dang_nhap_thi_van_luu_theo_ma_trinh_duyet(monkeypatch, tmp_path):
    """Ai trong nhóm chưa tạo Client ID vẫn phải chạy được y như trước."""
    api_mod, _, store_mod = _nap(monkeypatch, tmp_path, bat_dang_nhap=False)
    client = TestClient(api_mod.app)

    assert client.get("/api/me").json()["login_required"] is False

    r = client.post("/api/ask", data={"question": "Xin chao", "user_id": "ma_trinh_duyet"})
    assert "conversation_id" in r.json()

    ds = client.get("/api/conversations?user_id=ma_trinh_duyet").json()["conversations"]
    assert len(ds) == 1


# ------------------------- agent loi giua chung ----------------------------- #
class _GraphGiaLoi:
    """Gia lap agent bi loi (vd Gemini 503 qua tai) sau khi da nhan cau hoi."""

    @staticmethod
    def invoke(state, config=None):
        raise RuntimeError("503 UNAVAILABLE: model qua tai (gia lap)")


def test_nguoi_dang_nhap_agent_loi_khong_de_lai_hoi_thoai_rong(monkeypatch, tmp_path):
    """Bug that: hoi thoai duoc tao truoc khi goi agent, agent loi giua chung thi
    hoi thoai rong (0 tin nhan) van con trong database, hien trong sidebar nhung
    mo ra trong khong. Phai dam bao KHONG con hoi thoai rong nao sau khi loi."""
    api_mod, auth_mod, store_mod = _nap(monkeypatch, tmp_path)
    monkeypatch.setattr(api_mod, "_get_supervisor_graph", lambda: _GraphGiaLoi)
    client = TestClient(api_mod.app)

    r = client.post(
        "/api/ask",
        data={"question": "Cau hoi se loi"},
        headers=_bearer(auth_mod, A),
    )
    assert r.status_code == 502

    from sqlalchemy import func, select

    with store_mod.get_engine().begin() as conn:
        so_hoi_thoai = conn.execute(
            select(func.count()).select_from(store_mod.conversations)
        ).scalar()
    assert so_hoi_thoai == 0, "Agent loi khong duoc de lai hoi thoai rong trong database"
