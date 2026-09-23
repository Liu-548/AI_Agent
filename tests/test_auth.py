"""Test phiếu đăng nhập của hệ thống (app/auth.py).

Không gọi mạng, không cần Client ID thật, không cần .env: mọi test đều nạp lại
`app.core.config` với biến môi trường giả — cùng cách làm với test_store.py và
test_llm_config.py (quy tắc TS-03).

Phần `xac_minh_google()` gọi ra máy chủ Google nên KHÔNG test ở đây; chỗ đó chỉ
bọc lại thư viện `google-auth`, còn phần tự viết — và cũng là phần nguy hiểm nếu
sai — là chữ ký và hạn dùng của phiếu.
"""

from __future__ import annotations

import importlib
import time

import pytest

BI_MAT = "bi_mat_chi_de_test_" + "0123456789abcdef"
BI_MAT_KHAC = "mot_bi_mat_hoan_toan_khac_" + "fedcba9876543210"
CLIENT_ID = "123456789-test.apps.googleusercontent.com"

HO_SO = {
    "sub": "110123456789012345678",
    "email": "ai_do@gmail.com",
    "name": "Ai Do",
    "picture": "https://example.com/a.jpg",
}


def _nap(monkeypatch, client_id=CLIENT_ID, secret=BI_MAT, days="30"):
    for ten in ("GOOGLE_CLIENT_ID", "SESSION_SECRET", "SESSION_DAYS"):
        monkeypatch.delenv(ten, raising=False)
    if client_id:
        monkeypatch.setenv("GOOGLE_CLIENT_ID", client_id)
    if secret:
        monkeypatch.setenv("SESSION_SECRET", secret)
    if days:
        monkeypatch.setenv("SESSION_DAYS", days)

    import app.core.config as cfg

    importlib.reload(cfg)
    import app.auth as auth_mod

    importlib.reload(auth_mod)
    return cfg.settings, auth_mod


# ------------------------------ bật / tắt ---------------------------------- #
def test_thieu_mot_trong_hai_thi_khong_bat_dang_nhap(monkeypatch):
    """Chỉ có Client ID hoặc chỉ có secret đều phải coi là TẮT.

    Bật nửa vời nguy hiểm hơn tắt hẳn: có Client ID mà thiếu secret thì phiếu
    không ký được, còn có secret mà thiếu Client ID thì không xác minh nổi
    người đăng nhập là ai.
    """
    settings, _ = _nap(monkeypatch, client_id=CLIENT_ID, secret="")
    assert settings.dang_nhap_bat() is False

    settings, _ = _nap(monkeypatch, client_id="", secret=BI_MAT)
    assert settings.dang_nhap_bat() is False

    settings, _ = _nap(monkeypatch)
    assert settings.dang_nhap_bat() is True


def test_mo_ta_dang_nhap_khong_lo_bi_mat(monkeypatch):
    settings, _ = _nap(monkeypatch)
    mo_ta = settings.mo_ta_dang_nhap()
    assert BI_MAT not in mo_ta
    assert "Google" in mo_ta


# ------------------------------ phiếu hợp lệ -------------------------------- #
def test_tao_roi_doc_lai_phieu(monkeypatch):
    _, auth = _nap(monkeypatch)
    ruot = auth.doc_phieu(auth.tao_phieu(HO_SO))
    assert ruot["sub"] == HO_SO["sub"]
    assert ruot["email"] == HO_SO["email"]
    assert ruot["name"] == HO_SO["name"]
    assert ruot["exp"] > time.time()


def test_phieu_khong_chua_bi_mat(monkeypatch):
    """Phiếu nằm trong localStorage của trình duyệt — lộ secret là mất tất cả."""
    _, auth = _nap(monkeypatch)
    assert BI_MAT not in auth.tao_phieu(HO_SO)


# ------------------------------ phiếu không hợp lệ -------------------------- #
@pytest.mark.parametrize("phieu", ["", "khong-co-dau-cham", "a.b", "....", "x" * 50])
def test_phieu_rac_bi_tu_choi(monkeypatch, phieu):
    _, auth = _nap(monkeypatch)
    assert auth.doc_phieu(phieu) is None


def test_sua_ruot_phieu_bi_phat_hien(monkeypatch):
    """Đổi `sub` trong phiếu để đọc lịch sử người khác — chữ ký phải chặn lại."""
    import base64
    import json

    _, auth = _nap(monkeypatch)
    phan_ruot, chu_ky = auth.tao_phieu(HO_SO).split(".", 1)

    ruot = json.loads(base64.urlsafe_b64decode(phan_ruot + "=" * (-len(phan_ruot) % 4)))
    ruot["sub"] = "999999999999999999999"
    ruot_moi = base64.urlsafe_b64encode(
        json.dumps(ruot, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")

    assert auth.doc_phieu(f"{ruot_moi}.{chu_ky}") is None


def test_phieu_ky_bang_bi_mat_khac_bi_tu_choi(monkeypatch):
    _, auth = _nap(monkeypatch)
    phieu = auth.tao_phieu(HO_SO)

    _, auth_khac = _nap(monkeypatch, secret=BI_MAT_KHAC)
    assert auth_khac.doc_phieu(phieu) is None


def test_phieu_het_han_bi_tu_choi(monkeypatch):
    """SESSION_DAYS=0 -> phiếu hết hạn ngay, dùng để kiểm tra nhánh hết hạn."""
    _, auth = _nap(monkeypatch, days="0")
    phieu = auth.tao_phieu(HO_SO)
    time.sleep(1.1)
    assert auth.doc_phieu(phieu) is None


def test_tat_dang_nhap_thi_khong_tao_duoc_phieu(monkeypatch):
    _, auth = _nap(monkeypatch, secret="")
    with pytest.raises(auth.LoiDangNhap):
        auth.tao_phieu(HO_SO)
    assert auth.doc_phieu("bat-ky-thu-gi") is None


def test_xac_minh_google_bao_loi_ro_khi_thieu_cau_hinh(monkeypatch):
    _, auth = _nap(monkeypatch, client_id="")
    with pytest.raises(auth.LoiDangNhap):
        auth.xac_minh_google("token-gia")
