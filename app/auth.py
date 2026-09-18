"""Đăng nhập bằng Google cho giao diện web.

Vì sao file này nằm ở `app/` chứ không phải `app/core/`: giống `app/store.py`,
đây là chuyện của riêng lớp web. Agent, tool và `python -m app.main` chạy bình
thường mà không cần biết file này tồn tại (quy tắc CT-03).

Hai việc tách bạch:

  1. `xac_minh_google()` — hỏi Google "người cầm tấm vé này là ai?".
     Trình duyệt lấy ID token từ nút "Sign in with Google", gửi lên đây MỘT LẦN.
     Ta không tự đọc token đó mà nhờ thư viện `google-auth` kiểm chữ ký bằng
     khoá công khai của Google. Tự giải mã bằng tay là lỗ hổng kinh điển: token
     chỉ là base64, ai cũng sửa được phần ruột nếu không kiểm chữ ký.

  2. `tao_phieu()` / `doc_phieu()` — phiếu đăng nhập của CHÍNH hệ thống này.
     Sau khi Google xác nhận, ta tự phát một phiếu có hạn dùng (mặc định 30
     ngày) để mỗi request sau không phải gọi lại Google. Phiếu ký bằng HMAC-
     SHA256 với SESSION_SECRET — chỉ dùng thư viện chuẩn của Python, không thêm
     gói nào.

Danh tính người dùng là `sub` của Google (một chuỗi số cố định), KHÔNG phải
email: người ta đổi được email gắn với tài khoản, đổi xong mà ta khoá theo email
thì toàn bộ lịch sử cũ thành của người lạ.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from app.core.config import settings


class LoiDangNhap(Exception):
    """Đăng nhập không hợp lệ. `app/api.py` bắt lỗi này và trả HTTP 401."""


# --------------------------------------------------------------------------- #
# Phiếu đăng nhập của hệ thống (HMAC-SHA256, không cần thư viện ngoài)
# --------------------------------------------------------------------------- #
def _b64(raw: bytes) -> str:
    """Base64 kiểu URL, bỏ dấu '=' để phiếu không vỡ khi nằm trong URL/header."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _un_b64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _chu_ky(phan_ruot: str) -> str:
    return _b64(
        hmac.new(
            settings.session_secret.encode("utf-8"),
            phan_ruot.encode("ascii"),
            hashlib.sha256,
        ).digest()
    )


def tao_phieu(ho_so: dict) -> str:
    """Phát phiếu đăng nhập có hạn dùng cho một người đã được Google xác nhận."""
    if not settings.session_secret:
        raise LoiDangNhap("Server chua cau hinh SESSION_SECRET.")

    ruot = {
        "sub": ho_so["sub"],
        "email": ho_so.get("email", ""),
        "name": ho_so.get("name", ""),
        "picture": ho_so.get("picture", ""),
        "exp": int(time.time()) + settings.session_days * 86400,
    }
    phan_ruot = _b64(json.dumps(ruot, separators=(",", ":")).encode("utf-8"))
    return f"{phan_ruot}.{_chu_ky(phan_ruot)}"


def doc_phieu(phieu: str) -> Optional[dict]:
    """Trả về thông tin trong phiếu, hoặc None nếu phiếu sai/hết hạn/bị sửa.

    Trả None thay vì ném lỗi: nơi gọi chỉ cần biết "không hợp lệ", còn phân biệt
    sai chữ ký hay hết hạn mà báo ra ngoài là tự chỉ đường cho người dò phiếu.
    """
    if not phieu or not settings.session_secret:
        return None
    try:
        phan_ruot, chu_ky = phieu.split(".", 1)
    except ValueError:
        return None

    # compare_digest: so sánh trong thời gian hằng định. Dùng '==' thì thời gian
    # trả lời khác nhau theo số ký tự khớp, đủ để dò dần ra chữ ký đúng.
    if not hmac.compare_digest(chu_ky, _chu_ky(phan_ruot)):
        return None

    try:
        ruot = json.loads(_un_b64(phan_ruot))
    except (ValueError, json.JSONDecodeError):
        return None

    if not isinstance(ruot, dict) or not ruot.get("sub"):
        return None
    if int(ruot.get("exp", 0)) < time.time():
        return None
    return ruot


# --------------------------------------------------------------------------- #
# Xác minh ID token của Google
# --------------------------------------------------------------------------- #
def xac_minh_google(id_token_str: str) -> dict:
    """Kiểm tra ID token do nút đăng nhập của Google trả về.

    `google-auth` lo phần khó: tải khoá công khai của Google (có cache), kiểm
    chữ ký, kiểm hạn dùng, kiểm `iss`, và kiểm `aud` đúng Client ID của ta.
    Thiếu bước kiểm `aud` thì token của một ứng dụng khác cũng đăng nhập được
    vào đây — đó là lý do phải truyền `settings.google_client_id` vào.
    """
    if not settings.google_client_id:
        raise LoiDangNhap("Server chua cau hinh GOOGLE_CLIENT_ID.")
    if not id_token_str:
        raise LoiDangNhap("Thieu id_token.")

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
    except ImportError as exc:  # pragma: no cover
        raise LoiDangNhap(
            "Server thieu thu vien google-auth. Chay: pip install -r requirements.txt"
        ) from exc

    try:
        thong_tin = google_id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            settings.google_client_id,
        )
    except Exception as exc:  # thư viện ném ValueError cho mọi kiểu token hỏng
        raise LoiDangNhap(f"Token Google khong hop le: {exc}") from exc

    if not thong_tin.get("sub"):
        raise LoiDangNhap("Token Google thieu dinh danh nguoi dung.")

    # Google trả email_verified=False với vài loại tài khoản doanh nghiệp. `sub`
    # vẫn tin được, nhưng email chưa xác minh thì không nên đem đi hiển thị hay
    # đối chiếu với danh sách cho phép.
    email = thong_tin.get("email", "") if thong_tin.get("email_verified") else ""

    return {
        "sub": str(thong_tin["sub"]),
        "email": email,
        "name": thong_tin.get("name", "") or email.split("@")[0],
        "picture": thong_tin.get("picture", ""),
    }
