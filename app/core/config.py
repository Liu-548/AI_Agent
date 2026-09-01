"""Cấu hình tập trung — MỌI biến môi trường chỉ được đọc ở file này.

Quy tắc (xem QUY_TAC_THIET_KE.md, Bảng 5):
- Không os.getenv() rải rác trong code agent/tool.
- Không hard-code API key ở bất kỳ đâu.

Cấu hình LAI (hybrid): mỗi vai trò có thể chạy trên một nhà cung cấp khác nhau,
khai báo ngay trong tên model theo cú pháp `provider:model`:

    MODEL_SUPERVISOR=groq:llama-3.3-70b-versatile
    MODEL_DESCRIBE=google:gemini-3.5-flash-lite

Không ghi tiền tố thì dùng LLM_PROVIDER làm mặc định.
Lý do tồn tại cơ chế này: Groq cho hạn mức miễn phí lớn gấp hàng chục lần Gemini
nhưng phần đọc ảnh của đồ án lại cần model đa phương thức ổn định của Google.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
DOTENV_PATH = ROOT_DIR / ".env"

# Nạp .env — và GHI LẠI kết quả. Trước đây chỗ này nuốt lỗi im lặng, khiến khi
# chạy nhầm Python hệ thống (chưa cài python-dotenv) thì .env không được đọc và
# hệ thống báo "thiếu key" trong khi key vẫn nằm nguyên trong file.
DOTENV_LOADED = False
DOTENV_PROBLEM = ""
try:
    from dotenv import load_dotenv

    DOTENV_LOADED = bool(load_dotenv(DOTENV_PATH))
    if not DOTENV_LOADED and DOTENV_PATH.exists():
        DOTENV_PROBLEM = f"Không đọc được {DOTENV_PATH}"
except ImportError:  # pragma: no cover
    if DOTENV_PATH.exists():
        DOTENV_PROBLEM = (
            "Có file .env nhưng THIẾU thư viện python-dotenv nên không nạp được.\n"
            "     Gần như chắc chắn bạn đang chạy nhầm Python hệ thống thay vì venv.\n"
            "     Sửa: kích hoạt venv (.venv\\Scripts\\Activate.ps1) rồi chạy lại."
        )


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_int(key: str, default: int) -> int:
    raw = _env(key)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    raw = _env(key).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _env_float(key: str, default: float) -> float:
    raw = _env(key)
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


# --------------------------------------------------------------------------- #
# Nhà cung cấp
# --------------------------------------------------------------------------- #
PROVIDER_GOOGLE = "google"   # SDK native của Google (langchain-google-genai)
PROVIDER_GROQ = "groq"       # giao thức OpenAI, endpoint của Groq
PROVIDER_OPENAI = "openai"   # giao thức OpenAI (OpenAI thật, Ollama, ...)
PROVIDERS = (PROVIDER_GOOGLE, PROVIDER_GROQ, PROVIDER_OPENAI)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GEMINI_OPENAI_COMPAT_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Key Gemini đời mới (từ 06/2026) bắt đầu bằng "AQ." thay cho "AIza".
# Key AQ. chạy tốt trên đường native nhưng bị từ chối trên đường tương thích OpenAI.
GEMINI_AUTH_KEY_PREFIX = "AQ."
GEMINI_LEGACY_KEY_PREFIX = "AIza"

_TRANG_LAY_KEY = {
    PROVIDER_GOOGLE: "https://aistudio.google.com/apikey",
    PROVIDER_GROQ: "https://console.groq.com/keys",
    PROVIDER_OPENAI: "https://platform.openai.com/api-keys",
}
_TEN_BIEN_KEY = {
    PROVIDER_GOOGLE: "GEMINI_API_KEY",
    PROVIDER_GROQ: "GROQ_API_KEY",
    PROVIDER_OPENAI: "OPENAI_API_KEY",
}


@dataclass(frozen=True)
class Settings:
    # --- Nhà cung cấp mặc định (dùng khi MODEL_* không ghi tiền tố) ---
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", PROVIDER_GROQ).lower())

    # --- Key theo từng nhà cung cấp ---
    # LLM_API_KEY là key của nhà cung cấp MẶC ĐỊNH, dùng khi biến riêng bỏ trống.
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY"))
    google_api_key: str = field(
        default_factory=lambda: _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY")
    )
    groq_api_key: str = field(default_factory=lambda: _env("GROQ_API_KEY"))
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))

    # Chỉ dùng cho provider "openai" (Ollama, OpenAI thật, endpoint lạ).
    llm_base_url: str = field(
        default_factory=lambda: _env("LLM_BASE_URL") or _env("OPENAI_BASE_URL")
    )

    # --- Model theo vai trò, cú pháp "provider:model" ---
    #
    # NĂM vai trò trỏ tới NĂM model khác nhau là quyết định có chủ đích: hạn mức
    # miễn phí tính riêng theo từng model, dồn hai vai trò vào một model là tự
    # cắt đôi số lượt chạy mỗi ngày.
    #
    # Bố trí lai: đường TEXT (supervisor + research) chạy Groq vì hạn mức lớn
    # (~1.000 req/ngày/model); đường ẢNH chạy Gemini vì Groq không có model đa
    # phương thức ổn định. Đường ảnh dù sao cũng bị chặn ở ~20 req/ngày của
    # Gemini nên để cả vòng ReAct của Vision Agent bên đó luôn cho gọn.
    #
    # LƯU Ý: Groq khai tử llama-3.3-70b-versatile và llama-3.1-8b-instant cho
    # free tier từ 16/08/2026, thay bằng openai/gpt-oss-120b và -20b. Trước khi
    # đổi model, chạy `python -m app.main --models` để lấy danh sách THẬT thay vì
    # tin tài liệu.
    model_supervisor: str = field(
        default_factory=lambda: _env("MODEL_SUPERVISOR", "groq:openai/gpt-oss-120b")
    )
    model_research: str = field(
        default_factory=lambda: _env("MODEL_RESEARCH", "groq:openai/gpt-oss-20b")
    )
    model_vision: str = field(
        default_factory=lambda: _env("MODEL_VISION", "google:gemini-3.5-flash")
    )
    model_describe: str = field(
        default_factory=lambda: _env("MODEL_DESCRIBE", "google:gemini-3.5-flash-lite")
    )
    model_utility: str = field(
        default_factory=lambda: _env("MODEL_UTILITY", "google:gemini-3.1-flash-lite")
    )
    temperature: float = 0.0

    # --- Research tools ---
    arxiv_top_k: int = field(default_factory=lambda: _env_int("ARXIV_TOP_K", 2))
    arxiv_max_chars: int = field(default_factory=lambda: _env_int("ARXIV_MAX_CHARS", 1000))
    wikipedia_top_k: int = field(default_factory=lambda: _env_int("WIKIPEDIA_TOP_K", 2))
    wikipedia_max_chars: int = field(default_factory=lambda: _env_int("WIKIPEDIA_MAX_CHARS", 2000))
    wikipedia_user_agent: str = field(
        default_factory=lambda: _env(
            "WIKIPEDIA_USER_AGENT", "VisualAgenticAI/1.0 (contact: team@example.com)"
        )
    )

    # Trần số lượt tìm kiếm cho MỘT câu hỏi. Đây là dây phanh của vòng ReAct:
    # ở temperature 0, khi kết quả không như ý model gặp lại đúng bối cảnh cũ
    # nên ra đúng quyết định cũ -> gọi lặp một truy vấn -> hội thoại phình to
    # -> Groq trả 400 output_parse_failed. Xem app/agents/research_agent/tools.py.
    research_max_searches: int = field(
        default_factory=lambda: _env_int("RESEARCH_MAX_SEARCHES", 6)
    )

    # --- Vision tools ---
    # yolo11n.pt (~5MB) đủ cho dev; yolo11x.pt (~109MB) chỉ dùng khi cần độ chính xác.
    yolo_weights: str = field(default_factory=lambda: _env("YOLO_WEIGHTS", "yolo11n.pt"))
    yolo_conf: float = field(default_factory=lambda: _env_float("YOLO_CONF", 0.25))
    # Ngưỡng NMS: 2 khung cùng loại vật thể chồng nhau quá tỉ lệ này (IoU) sẽ bị
    # gộp/loại còn 1 khung tốt nhất. Mặc định ultralytics là 0.7 (khá lỏng), dễ
    # để lọt 2 khung trên cùng 1 vật thể khi ảnh có nhiều đối tượng sát nhau
    # (mặt chó chụm lại, đám đông...). Hạ xuống 0.45 để loại trùng lặp mạnh hơn.
    yolo_iou: float = field(default_factory=lambda: _env_float("YOLO_IOU", 0.45))
    # Mặc định TẮT: chỉ lưu thêm ảnh có vẽ khung khi thật sự cần xem trực quan,
    # tránh sinh file "_detected.jpg" rác mỗi lần chạy câu hỏi đếm vật thể.
    draw_detections_enabled: bool = field(
        default_factory=lambda: _env_bool("DRAW_DETECTIONS", False)
    )
    # `detail` là tham số RIÊNG của OpenAI. Để rỗng là bỏ hẳn trường này khỏi payload.
    vision_detail: str = field(default_factory=lambda: _env("VISION_DETAIL"))
    # Xem Bảng 3 mục IF-06: mặc định False để ReAct loop không bị cắt ngang.
    image_describer_return_direct: bool = field(
        default_factory=lambda: _env_bool("IMAGE_DESCRIBER_RETURN_DIRECT", False)
    )

    # --- Runtime ---
    recursion_limit: int = field(default_factory=lambda: _env_int("RECURSION_LIMIT", 50))

    # ----------------------------------------------------------------- #
    # Tách "provider:model" và lấy key tương ứng
    # ----------------------------------------------------------------- #
    def split_model(self, spec: str) -> Tuple[str, str]:
        """'groq:llama-3.3-70b' -> ('groq', 'llama-3.3-70b').

        Không có tiền tố -> dùng LLM_PROVIDER. Cẩn thận: tên model của Groq có
        thể chứa dấu '/' (openai/gpt-oss-120b) nhưng không chứa ':', nên tách
        theo dấu ':' đầu tiên là an toàn.
        """
        spec = (spec or "").strip()
        if ":" in spec:
            provider, _, model = spec.partition(":")
            provider = provider.strip().lower()
            if provider in PROVIDERS:
                return provider, model.strip()
        return self.llm_provider, spec

    def api_key_for(self, provider: str) -> str:
        """Key của một nhà cung cấp. Raise kèm hướng dẫn nếu thiếu."""
        rieng = {
            PROVIDER_GOOGLE: self.google_api_key,
            PROVIDER_GROQ: self.groq_api_key,
            PROVIDER_OPENAI: self.openai_api_key,
        }.get(provider, "")
        key = rieng or (self.llm_api_key if provider == self.llm_provider else "")

        if not key or key.endswith("..."):
            bien = _TEN_BIEN_KEY.get(provider, "LLM_API_KEY")
            trang = _TRANG_LAY_KEY.get(provider, "")
            them = f"\n  LƯU Ý: {DOTENV_PROBLEM}" if DOTENV_PROBLEM else ""
            raise RuntimeError(
                f"Thiếu API key cho nhà cung cấp {provider!r}.\n"
                f"  1. Lấy key tại {trang}\n"
                f"  2. Điền vào dòng {bien}= trong .env "
                "(không dấu ngoặc kép, không khoảng trắng)\n"
                "  3. Kiểm tra lại: python -m app.main --config" + them
            )

        # Chặn sớm tổ hợp sai thay vì để 401 khó hiểu nổ ra giữa graph.
        if (
            provider == PROVIDER_OPENAI
            and "googleapis.com" in self.llm_base_url
            and key.startswith(GEMINI_AUTH_KEY_PREFIX)
        ):
            raise RuntimeError(
                "Key Gemini đời mới (AQ.) bị từ chối trên endpoint tương thích OpenAI.\n"
                "  Sửa: dùng tiền tố google: trong MODEL_* (vd google:gemini-3.5-flash-lite)."
            )
        return key

    def base_url_for(self, provider: str) -> str:
        if provider == PROVIDER_GROQ:
            return GROQ_BASE_URL
        if provider == PROVIDER_OPENAI:
            return self.llm_base_url
        return ""

    # ----------------------------------------------------------------- #
    # Chẩn đoán (không lộ nội dung key)
    # ----------------------------------------------------------------- #
    @property
    def provider_name(self) -> str:
        return f"mặc định={self.llm_provider}"

    def key_kind(self, provider: str) -> str:
        try:
            k = self.api_key_for(provider)
        except RuntimeError:
            return "thiếu"
        if k.startswith(GEMINI_AUTH_KEY_PREFIX):
            return f"Gemini Auth key (AQ.), {len(k)} ký tự"
        if k.startswith(GEMINI_LEGACY_KEY_PREFIX):
            return f"Gemini Standard key (AIza) — hết hạn 09/2026, {len(k)} ký tự"
        if k.startswith("gsk_"):
            return f"Groq key (gsk_), {len(k)} ký tự"
        if k.startswith("sk-"):
            return f"OpenAI key (sk-), {len(k)} ký tự"
        return f"không rõ định dạng, {len(k)} ký tự"

    def mo_ta_cau_hinh(self) -> str:
        """Bảng tóm tắt vai trò -> provider/model, dùng cho `--config`."""
        dong = []
        for vai_tro, spec in (
            ("supervisor", self.model_supervisor),
            ("research", self.model_research),
            ("vision", self.model_vision),
            ("describe", self.model_describe),
            ("utility", self.model_utility),
        ):
            provider, model = self.split_model(spec)
            dong.append(f"  {vai_tro:<11} {provider:<7} {model}")
        providers = sorted({self.split_model(s)[0] for s in (
            self.model_supervisor, self.model_research, self.model_vision,
            self.model_describe, self.model_utility,
        )})
        dong.append("")
        for p in providers:
            dong.append(f"  key[{p}]: {self.key_kind(p)}")

        import sys

        dong.append("")
        dong.append(f"  python : {sys.executable}")
        trong_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
        dong.append(f"  venv   : {'có' if trong_venv else 'KHÔNG (đang dùng Python hệ thống)'}")
        if DOTENV_LOADED:
            dong.append(f"  .env   : đã nạp ({DOTENV_PATH})")
        elif DOTENV_PROBLEM:
            dong.append(f"  .env   : LỖI — {DOTENV_PROBLEM}")
        else:
            dong.append(f"  .env   : không có ({DOTENV_PATH})")
        return "\n".join(dong)


settings = Settings()