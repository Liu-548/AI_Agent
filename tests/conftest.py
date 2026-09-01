"""Cách ly toàn bộ test khỏi file `.env` và biến môi trường của từng máy.

Vì sao cần file này:
`app/core/config.py` gọi `load_dotenv()` ngay khi import, nên nếu không chặn thì
mọi test đọc `settings` sẽ ăn theo `.env` của người đang chạy. Hậu quả: test xanh
trên máy chưa tạo `.env` và đỏ trên máy đã tạo — đúng loại lỗi khiến cả nhóm mất
niềm tin vào bộ test. Ví dụ thật: ai đặt `IMAGE_DESCRIBER_RETURN_DIRECT=true`
trong `.env` sẽ làm đỏ một test hợp đồng, dù code hoàn toàn đúng.

conftest.py được pytest import TRƯỚC mọi test module, nên việc vô hiệu hoá
`load_dotenv` ở đây diễn ra trước khi `app.core.config` kịp chạy lần đầu.
"""

from __future__ import annotations

import os

# Mọi biến môi trường mà app/core/config.py đọc. Thêm biến mới -> thêm vào đây.
APP_ENV_VARS = (
    "LLM_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "OPENAI_API_KEY",
    "LLM_PROVIDER",
    "LLM_BASE_URL",
    "OPENAI_BASE_URL",
    "MODEL_SUPERVISOR",
    "MODEL_RESEARCH",
    "MODEL_VISION",
    "MODEL_DESCRIBE",
    "MODEL_UTILITY",
    "MODEL_AGENT",
    "ARXIV_TOP_K",
    "ARXIV_MAX_CHARS",
    "WIKIPEDIA_TOP_K",
    "WIKIPEDIA_MAX_CHARS",
    "WIKIPEDIA_USER_AGENT",
    "RESEARCH_MAX_SEARCHES",
    "YOLO_WEIGHTS",
    "VISION_DETAIL",
    "IMAGE_DESCRIBER_RETURN_DIRECT",
    "RECURSION_LIMIT",
)


def _vo_hieu_hoa_dotenv() -> None:
    """Biến load_dotenv thành no-op để test không đọc .env của máy đang chạy."""
    try:
        import dotenv
    except ImportError:  # pragma: no cover - môi trường không cài python-dotenv
        return
    dotenv.load_dotenv = lambda *args, **kwargs: False


def _xoa_bien_moi_truong_cua_du_an() -> None:
    """Xoá biến người dùng lỡ export sẵn trong shell (vd $env:OPENAI_API_KEY)."""
    for ten in APP_ENV_VARS:
        os.environ.pop(ten, None)


_vo_hieu_hoa_dotenv()
_xoa_bien_moi_truong_cua_du_an()
