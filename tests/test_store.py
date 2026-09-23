"""Test tầng lưu trữ hội thoại (app/store.py).

Không cần mạng, không cần API key, không gọi LLM — chạy được trong
`pytest -m "not network"`. Mỗi test dùng một file SQLite riêng trong thư mục tạm
của pytest nên không đụng `conversations.db` thật của người đang chạy.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def store(monkeypatch, tmp_path):
    """Nạp lại app.store với DATABASE_URL trỏ vào một file SQLite dùng một lần.

    Phải reload cả `app.core.config`: `settings` là dataclass đóng băng, đọc biến
    môi trường đúng một lần lúc import, nên đổi env sau đó không có tác dụng.
    Cùng cách làm với tests/test_llm_config.py.
    """
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    import app.core.config as cfg

    importlib.reload(cfg)
    import app.store as store_mod

    importlib.reload(store_mod)
    return store_mod


def test_tao_hoi_thoai_va_doc_lai_tin_nhan(store):
    c = store.tao_hoi_thoai("user_a", "Câu hỏi đầu")
    store.them_tin_nhan(c["id"], "user", "Có mấy con chó?", {"image_path": "/tmp/x.jpg"})
    store.them_tin_nhan(c["id"], "assistant", "Có 2 con.", {"counting": {"dog": 2}})

    tin = store.lay_tin_nhan(c["id"])
    assert [m["role"] for m in tin] == ["user", "assistant"]
    assert tin[0]["extras"]["image_path"] == "/tmp/x.jpg"
    assert tin[1]["extras"]["counting"] == {"dog": 2}


def test_moi_nguoi_chi_thay_hoi_thoai_cua_minh(store):
    """Không có đăng nhập, nên đây là hàng rào duy nhất giữa hai người cùng test."""
    cua_a = store.tao_hoi_thoai("user_a", "Của A")
    store.tao_hoi_thoai("user_b", "Của B")

    assert len(store.danh_sach_hoi_thoai("user_a")) == 1
    assert len(store.danh_sach_hoi_thoai("user_b")) == 1
    # Người lạ hỏi đúng id vẫn không đọc được, và cũng không xoá được.
    assert store.lay_hoi_thoai(cua_a["id"], "user_b") is None
    assert store.xoa_hoi_thoai(cua_a["id"], "user_b") is False
    assert store.lay_hoi_thoai(cua_a["id"], "user_a") is not None


def test_hoi_thoai_ghim_luon_nam_tren_dau(store):
    cu = store.tao_hoi_thoai("user_a", "Cũ")
    store.tao_hoi_thoai("user_a", "Mới hơn")
    store.ghim_hoi_thoai(cu["id"], "user_a", True)

    ds = store.danh_sach_hoi_thoai("user_a")
    assert ds[0]["title"] == "Cũ" and ds[0]["pinned"] is True


def test_dem_so_tin_nhan_cua_tung_hoi_thoai(store):
    c = store.tao_hoi_thoai("user_a", "A")
    store.tao_hoi_thoai("user_a", "Rỗng")
    store.them_tin_nhan(c["id"], "user", "hỏi")
    store.them_tin_nhan(c["id"], "assistant", "đáp")

    dem = {x["title"]: x["message_count"] for x in store.danh_sach_hoi_thoai("user_a")}
    assert dem == {"A": 2, "Rỗng": 0}


def test_xoa_hoi_thoai_khong_de_lai_tin_nhan_mo_coi(store):
    """SQLite mặc định TẮT khoá ngoại nên ON DELETE CASCADE im lặng không chạy."""
    c = store.tao_hoi_thoai("user_a", "Sẽ xoá")
    store.them_tin_nhan(c["id"], "user", "hỏi")

    assert store.xoa_hoi_thoai(c["id"], "user_a") is True
    assert store.lay_tin_nhan(c["id"]) == []
    assert store.xoa_hoi_thoai(c["id"], "user_a") is False


def test_anh_qua_nang_bi_bo_nhung_van_giu_so_lieu(store):
    """Database miễn phí chỉ 0.5GB — thà mất ảnh còn hơn đầy database."""
    c = store.tao_hoi_thoai("user_a", "Ảnh nặng")
    store.them_tin_nhan(
        c["id"],
        "assistant",
        "xong",
        {"annotated_image_base64": "x" * (store.MAX_ANH_LUU_BYTES + 1), "counting": {"cat": 1}},
    )

    extras = store.lay_tin_nhan(c["id"])[0]["extras"]
    assert "annotated_image_base64" not in extras
    assert extras["annotated_image_skipped"] is True
    assert extras["counting"] == {"cat": 1}


def test_anh_vua_du_nho_thi_duoc_giu(store):
    c = store.tao_hoi_thoai("user_a", "Ảnh nhẹ")
    store.them_tin_nhan(c["id"], "assistant", "xong", {"annotated_image_base64": "x" * 100})
    assert store.lay_tin_nhan(c["id"])[0]["extras"]["annotated_image_base64"] == "x" * 100


def test_tieu_de_suy_ra_tu_cau_hoi(store):
    assert store.dat_tieu_de("  Máy học là gì?  ") == "Máy học là gì?"
    assert store.dat_tieu_de("") == "Hội thoại mới"
    dai = store.dat_tieu_de("a" * 200)
    assert len(dai) <= store.DO_DAI_TIEU_DE + 3 and dai.endswith("...")


@pytest.mark.parametrize(
    "vao, ra",
    [
        # Neon/Render/Supabase đưa chuỗi dạng này, SQLAlchemy lại đi tìm psycopg2
        # (bản cũ) -> deploy chết với ModuleNotFoundError. Đây là lỗi kinh điển.
        ("postgres://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        # Đã ghi rõ driver thì để nguyên.
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("sqlite:///abc.db", "sqlite:///abc.db"),
    ],
)
def test_chuan_hoa_chuoi_ket_noi(store, vao, ra):
    assert store._chuan_hoa_url(vao) == ra


def test_mo_ta_database_khong_lo_mat_khau():
    """`python -m app.main --config` in dòng này ra màn hình -> không được lộ."""
    import importlib
    import os

    os.environ["DATABASE_URL"] = "postgresql://nguoidung:matkhausieubimat@ep-abc.neon.tech/db"
    try:
        import app.core.config as cfg

        importlib.reload(cfg)
        mo_ta = cfg.settings.mo_ta_database()
        assert "matkhausieubimat" not in mo_ta
        assert "nguoidung" not in mo_ta
        assert "ep-abc.neon.tech" in mo_ta
    finally:
        os.environ.pop("DATABASE_URL", None)
        importlib.reload(cfg)


# --------------------------- hồ sơ người đăng nhập -------------------------- #
def test_luu_nguoi_dung_cap_nhat_khong_tao_ban_sao(store):
    """Đăng nhập lần hai phải CẬP NHẬT hồ sơ cũ, không đẻ thêm dòng mới."""
    from sqlalchemy import func, select

    store.luu_nguoi_dung({"sub": "sub_1", "email": "a@gmail.com", "name": "Ten Cu"})
    store.luu_nguoi_dung({"sub": "sub_1", "email": "a@gmail.com", "name": "Ten Moi"})

    with store.get_engine().begin() as conn:
        so_dong = conn.execute(select(func.count()).select_from(store.users)).scalar()
        ten = conn.execute(
            select(store.users.c.name).where(store.users.c.id == "sub_1")
        ).scalar()

    assert so_dong == 1
    assert ten == "Ten Moi"


def test_luu_nguoi_dung_bo_qua_ho_so_thieu_sub(store):
    from sqlalchemy import func, select

    store.luu_nguoi_dung({"email": "khong_co_sub@gmail.com"})
    with store.get_engine().begin() as conn:
        assert conn.execute(select(func.count()).select_from(store.users)).scalar() == 0


def test_hai_tai_khoan_google_khong_thay_hoi_thoai_cua_nhau(store):
    """Đây là lời hứa chính của tính năng đăng nhập: lịch sử phải tách theo `sub`."""
    cua_a = store.tao_hoi_thoai("sub_a", "Hỏi của A")
    store.tao_hoi_thoai("sub_b", "Hỏi của B")

    assert [c["title"] for c in store.danh_sach_hoi_thoai("sub_a")] == ["Hỏi của A"]
    assert store.lay_hoi_thoai(cua_a["id"], "sub_b") is None
    assert store.xoa_hoi_thoai(cua_a["id"], "sub_b") is False
