"""Lưu trữ hội thoại cho web UI — KHÔNG phải tài sản chung của agent.

Vì sao file này nằm ở `app/` chứ không phải `app/core/`: `app/core/` là code mà
cả ba agent cùng dùng (Bảng 9). Lưu lịch sử chat là việc riêng của tầng web, CLI
(`app/main.py`) không đụng tới một dòng nào ở đây. Đặt vào `core/` là nhét logic
riêng vào tài sản chung — đúng thứ quy tắc CT-03 cấm.

Chạy được TRÊN HAI LOẠI DATABASE bằng cùng một đoạn code:

  - `DATABASE_URL` để trống -> SQLite, file `conversations.db` trong repo.
    Dùng khi dev trên máy: không cần mạng, không cần cài gì thêm.
  - `DATABASE_URL` trỏ Postgres -> dùng Postgres.
    BẮT BUỘC khi deploy. Render free tier xoá sạch ổ đĩa mỗi lần restart hoặc
    deploy lại, nên file SQLite nằm trên server sẽ bốc hơi cùng toàn bộ lịch sử
    hội thoại của người dùng. Database phải nằm NGOÀI Render (Neon, Supabase...).

Mọi hàm ở đây nhận/trả kiểu Python thuần (dict, list, str) để tầng API không phải
biết gì về SQLAlchemy.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.engine import Engine

from app.core.config import ROOT_DIR, settings

# Ảnh đã khoanh vùng được lưu kèm tin nhắn để mở lại hội thoại cũ vẫn thấy ảnh.
# Có trần: Neon free chỉ 0.5GB, mà một ảnh base64 nặng cỡ 100-400KB. Ảnh vượt
# ngưỡng thì bỏ phần base64 và chỉ giữ số liệu đếm — mất ảnh còn hơn đầy database.
MAX_ANH_LUU_BYTES = 400_000

# Tiêu đề hội thoại lấy từ câu hỏi đầu tiên, cắt cho vừa sidebar.
DO_DAI_TIEU_DE = 60

metadata = MetaData()

conversations = Table(
    "conversations",
    metadata,
    Column("id", String(36), primary_key=True),
    # user_id là chuỗi ngẫu nhiên trình duyệt tự sinh, KHÔNG phải tài khoản đăng
    # nhập. Đủ để mỗi người test thấy lịch sử của riêng mình mà không phải dựng
    # hệ thống xác thực — nhưng cũng có nghĩa là ai có id thì đọc được, nên đừng
    # gõ thông tin nhạy cảm vào bản demo.
    Column("user_id", String(64), nullable=False, index=True),
    Column("title", String(200), nullable=False, default=""),
    Column("pinned", Boolean, nullable=False, default=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, index=True),
)

messages = Table(
    "messages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "conversation_id",
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("role", String(16), nullable=False),  # "user" | "assistant"
    Column("content", Text, nullable=False, default=""),
    # extras: JSON dạng chuỗi — agents_used, agent_answers, counting, ảnh...
    # Lưu TEXT thay vì kiểu JSON riêng của Postgres để SQLite và Postgres dùng
    # chung đúng một câu lệnh, không phải rẽ nhánh theo loại database.
    Column("extras", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

# Hồ sơ người đăng nhập bằng Google. Bảng này CHỈ để hiển thị (tên, ảnh đại
# diện) và để biết ai đã từng dùng; việc phân tách lịch sử vẫn dựa vào
# `conversations.user_id`, nên xoá bảng này không làm mất hội thoại của ai.
users = Table(
    "users",
    metadata,
    # Chính là `sub` của Google — cố định suốt đời tài khoản, khác với email.
    Column("id", String(64), primary_key=True),
    Column("email", String(255), nullable=False, default=""),
    Column("name", String(255), nullable=False, default=""),
    Column("picture", Text, nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
)

_engine: Optional[Engine] = None


def _chuan_hoa_url(raw: str) -> str:
    """Đưa chuỗi kết nối về dạng SQLAlchemy hiểu được.

    Neon/Render/Supabase đều đưa chuỗi bắt đầu bằng `postgres://` hoặc
    `postgresql://`, nhưng cả hai đều khiến SQLAlchemy đi tìm driver psycopg2
    (bản cũ, phải biên dịch từ C). Dự án cài psycopg 3 nên phải ghi rõ
    `postgresql+psycopg://`. Đây là lỗi deploy kinh điển: chạy ngon trên máy,
    lên server báo `ModuleNotFoundError: No module named 'psycopg2'`.
    """
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    if raw.startswith("postgresql://"):
        raw = "postgresql+psycopg://" + raw[len("postgresql://") :]
    return raw


def get_engine() -> Engine:
    """Engine dùng chung cho cả tiến trình. Tạo một lần, tự tạo bảng nếu chưa có."""
    global _engine
    if _engine is not None:
        return _engine

    raw = settings.database_url
    if raw:
        _engine = create_engine(
            _chuan_hoa_url(raw),
            # Neon tự ngắt kết nối nhàn rỗi. Không có pre_ping thì request đầu
            # tiên sau lúc rảnh sẽ chết với "server closed the connection".
            pool_pre_ping=True,
            pool_size=3,
            max_overflow=2,
            pool_recycle=280,
        )
    else:
        duong_dan = ROOT_DIR / "conversations.db"
        _engine = create_engine(
            f"sqlite:///{duong_dan}",
            # FastAPI chạy endpoint đồng bộ trong threadpool -> mỗi request một
            # thread khác nhau. SQLite mặc định cấm dùng connection chéo thread.
            connect_args={"check_same_thread": False},
        )

    metadata.create_all(_engine)
    return _engine


def _bay_gio() -> datetime:
    return datetime.now(timezone.utc)


def luu_nguoi_dung(ho_so: Dict[str, Any]) -> None:
    """Ghi/cập nhật hồ sơ sau mỗi lần đăng nhập.

    Không dùng cú pháp UPSERT riêng của từng database (`ON CONFLICT` của
    Postgres, `INSERT OR REPLACE` của SQLite) vì hai bên viết khác nhau — cả
    file này giữ đúng một câu lệnh chạy được trên cả hai. Đăng nhập là việc
    hiếm nên thêm một lượt SELECT ở đây không đáng kể.
    """
    uid = str(ho_so.get("sub") or "").strip()
    if not uid:
        return

    bay_gio = _bay_gio()
    engine = get_engine()
    with engine.begin() as conn:
        da_co = conn.execute(select(users.c.id).where(users.c.id == uid)).first()
        gia_tri = {
            "email": ho_so.get("email", "") or "",
            "name": ho_so.get("name", "") or "",
            "picture": ho_so.get("picture", "") or "",
            "last_seen_at": bay_gio,
        }
        if da_co:
            conn.execute(users.update().where(users.c.id == uid).values(**gia_tri))
        else:
            conn.execute(users.insert().values(id=uid, created_at=bay_gio, **gia_tri))


def _iso(gia_tri: Any) -> str:
    """datetime -> chuỗi ISO. SQLite trả về datetime chưa gắn múi giờ, gắn UTC vào."""
    if isinstance(gia_tri, datetime):
        if gia_tri.tzinfo is None:
            gia_tri = gia_tri.replace(tzinfo=timezone.utc)
        return gia_tri.isoformat()
    return str(gia_tri or "")


def dat_tieu_de(cau_hoi: str) -> str:
    """Tiêu đề hội thoại suy ra từ câu hỏi đầu tiên."""
    gon = " ".join((cau_hoi or "").split())
    if not gon:
        return "Hội thoại mới"
    if len(gon) <= DO_DAI_TIEU_DE:
        return gon
    return gon[:DO_DAI_TIEU_DE].rstrip() + "..."


def _rut_gon_extras(extras: Optional[dict]) -> Optional[str]:
    """Chuỗi JSON để ghi xuống database, đã bỏ ảnh quá nặng."""
    if not extras:
        return None
    ban_sao = dict(extras)
    anh = ban_sao.get("annotated_image_base64")
    if anh and len(anh) > MAX_ANH_LUU_BYTES:
        ban_sao.pop("annotated_image_base64", None)
        ban_sao["annotated_image_skipped"] = True
    return json.dumps(ban_sao, ensure_ascii=False)


def _doc_extras(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        gia_tri = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return gia_tri if isinstance(gia_tri, dict) else {}


# --------------------------------------------------------------------------- #
# Hội thoại
# --------------------------------------------------------------------------- #
def tao_hoi_thoai(user_id: str, title: str = "") -> Dict[str, Any]:
    now = _bay_gio()
    ban_ghi = {
        "id": uuid.uuid4().hex,
        "user_id": user_id,
        "title": title or "Hội thoại mới",
        "pinned": False,
        "created_at": now,
        "updated_at": now,
    }
    with get_engine().begin() as conn:
        conn.execute(conversations.insert().values(**ban_ghi))
    return _dang_hoi_thoai(ban_ghi, so_tin_nhan=0)


def _dang_hoi_thoai(hang: Any, so_tin_nhan: Optional[int] = None) -> Dict[str, Any]:
    lay = hang.get if isinstance(hang, dict) else (lambda k: getattr(hang, k))
    ket_qua = {
        "id": lay("id"),
        "title": lay("title"),
        "pinned": bool(lay("pinned")),
        "created_at": _iso(lay("created_at")),
        "updated_at": _iso(lay("updated_at")),
    }
    if so_tin_nhan is not None:
        ket_qua["message_count"] = so_tin_nhan
    return ket_qua


def danh_sach_hoi_thoai(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Hội thoại của một người: ghim lên trước, rồi mới tới mới nhất."""
    dem = (
        select(messages.c.conversation_id, func.count().label("so_tin_nhan"))
        .group_by(messages.c.conversation_id)
        .subquery()
    )
    cau_lenh = (
        select(conversations, dem.c.so_tin_nhan)
        .select_from(conversations.outerjoin(dem, dem.c.conversation_id == conversations.c.id))
        .where(conversations.c.user_id == user_id)
        .order_by(conversations.c.pinned.desc(), conversations.c.updated_at.desc())
        .limit(limit)
    )
    with get_engine().connect() as conn:
        return [
            _dang_hoi_thoai(hang, so_tin_nhan=int(hang.so_tin_nhan or 0))
            for hang in conn.execute(cau_lenh)
        ]


def lay_hoi_thoai(conversation_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """None = không có, hoặc có nhưng của người khác (cùng một kết quả, cố ý).

    Trả 404 cho cả hai trường hợp để người lạ không dò được id nào đang tồn tại.
    """
    cau_lenh = select(conversations).where(
        conversations.c.id == conversation_id, conversations.c.user_id == user_id
    )
    with get_engine().connect() as conn:
        hang = conn.execute(cau_lenh).first()
    return _dang_hoi_thoai(hang) if hang else None


def doi_ten_hoi_thoai(conversation_id: str, user_id: str, title: str) -> bool:
    cau_lenh = (
        update(conversations)
        .where(conversations.c.id == conversation_id, conversations.c.user_id == user_id)
        .values(title=title[:200], updated_at=_bay_gio())
    )
    with get_engine().begin() as conn:
        return conn.execute(cau_lenh).rowcount > 0


def ghim_hoi_thoai(conversation_id: str, user_id: str, pinned: bool) -> bool:
    cau_lenh = (
        update(conversations)
        .where(conversations.c.id == conversation_id, conversations.c.user_id == user_id)
        .values(pinned=pinned)
    )
    with get_engine().begin() as conn:
        return conn.execute(cau_lenh).rowcount > 0


def xoa_hoi_thoai(conversation_id: str, user_id: str) -> bool:
    """Xoá hội thoại và mọi tin nhắn của nó.

    Xoá tin nhắn bằng tay chứ không dựa vào ON DELETE CASCADE: SQLite mặc định
    TẮT ràng buộc khoá ngoại, nên cascade im lặng không chạy và để lại tin nhắn
    mồ côi — chạy ngon trên Postgres, phình database trên máy dev.
    """
    with get_engine().begin() as conn:
        co_that = conn.execute(
            select(conversations.c.id).where(
                conversations.c.id == conversation_id,
                conversations.c.user_id == user_id,
            )
        ).first()
        if not co_that:
            return False
        conn.execute(delete(messages).where(messages.c.conversation_id == conversation_id))
        conn.execute(delete(conversations).where(conversations.c.id == conversation_id))
    return True


# --------------------------------------------------------------------------- #
# Tin nhắn
# --------------------------------------------------------------------------- #
def them_tin_nhan(
    conversation_id: str,
    role: str,
    content: str,
    extras: Optional[dict] = None,
) -> Dict[str, Any]:
    now = _bay_gio()
    with get_engine().begin() as conn:
        conn.execute(
            messages.insert().values(
                conversation_id=conversation_id,
                role=role,
                content=content or "",
                extras=_rut_gon_extras(extras),
                created_at=now,
            )
        )
        # Sidebar sắp xếp theo updated_at nên hội thoại vừa nhắn phải nhảy lên đầu.
        conn.execute(
            update(conversations)
            .where(conversations.c.id == conversation_id)
            .values(updated_at=now)
        )
    return {"role": role, "content": content, "extras": extras or {}, "created_at": _iso(now)}


def lay_tin_nhan(conversation_id: str) -> List[Dict[str, Any]]:
    cau_lenh = (
        select(messages)
        .where(messages.c.conversation_id == conversation_id)
        .order_by(messages.c.id.asc())
    )
    with get_engine().connect() as conn:
        return [
            {
                "role": hang.role,
                "content": hang.content,
                "extras": _doc_extras(hang.extras),
                "created_at": _iso(hang.created_at),
            }
            for hang in conn.execute(cau_lenh)
        ]
