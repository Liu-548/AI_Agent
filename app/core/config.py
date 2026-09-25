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

# Giá trị hợp lệ của RESEARCH_ARCH / RESEARCH_MODE.
RESEARCH_ARCHS = ("single", "topics")
RESEARCH_MODES = ("eco", "standard", "full")

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
    # Vai trò thứ SÁU: các agent chủ đề (scholar_agent, explainer_agent) nằm bên
    # trong research lead. Tách sổ hạn mức khỏi "research" để lead và agent chủ đề
    # không ăn chung một model. Để TRỐNG được khi RESEARCH_ARCH=single (không dùng).
    model_research_topic: str = field(default_factory=lambda: _env("MODEL_RESEARCH_TOPIC"))
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
    openalex_top_k: int = field(default_factory=lambda: _env_int("OPENALEX_TOP_K", 2))
    openalex_max_chars: int = field(default_factory=lambda: _env_int("OPENALEX_MAX_CHARS", 1000))
    # OpenAlex khong bat buoc mailto, nhung co no thi vao "polite pool": nhanh va
    # on dinh hon (it bi rate-limit khi tai cao). Mac dinh la placeholder, KHONG
    # phai email that cua nguoi dung -- doi trong .env neu muon dung email that.
    openalex_mailto: str = field(
        default_factory=lambda: _env("OPENALEX_MAILTO", "team@example.com")
    )

    # Trần số lượt tìm kiếm cho MỘT câu hỏi. Đây là dây phanh của vòng ReAct:
    # ở temperature 0, khi kết quả không như ý model gặp lại đúng bối cảnh cũ
    # nên ra đúng quyết định cũ -> gọi lặp một truy vấn -> hội thoại phình to
    # -> Groq trả 400 output_parse_failed. Xem app/agents/research_agent/tools.py.
    research_max_searches: int = field(
        default_factory=lambda: _env_int("RESEARCH_MAX_SEARCHES", 6)
    )
    # Có ai đặt RESEARCH_MAX_SEARCHES không? Chế độ "topics" chỉ ghi đè trần của
    # SearchProfile khi biến này được đặt thật, không phải khi đang dùng mặc định 6.
    research_max_searches_set: bool = field(
        default_factory=lambda: bool(_env("RESEARCH_MAX_SEARCHES"))
    )

    # --- Research nhiều agent chủ đề ---
    # "single": một ReAct agent như cũ (mặc định). "topics": research lead điều
    # phối các agent chủ đề. Xem docs/research-topics/SPEC_RESEARCH_TOPICS.md.
    research_arch: str = field(default_factory=lambda: _env("RESEARCH_ARCH", "single").lower())
    # eco | standard | full: bộ giới hạn tìm kiếm (SearchProfile), chỉ có nghĩa
    # khi RESEARCH_ARCH=topics.
    research_mode: str = field(default_factory=lambda: _env("RESEARCH_MODE", "standard").lower())
    # OpenAlex bắt buộc key từ 02/2026 (miễn phí). Thiếu key -> bỏ qua nguồn này.
    openalex_api_key: str = field(default_factory=lambda: _env("OPENALEX_API_KEY"))
    # Không có key vẫn chạy nhưng hay dính 429.
    semantic_scholar_api_key: str = field(
        default_factory=lambda: _env("SEMANTIC_SCHOLAR_API_KEY")
    )
    # Tăng hạn mức PubMed (E-utilities). Không bắt buộc.
    ncbi_api_key: str = field(default_factory=lambda: _env("NCBI_API_KEY"))

    # Cac model "gpt-oss" cua Groq la reasoning model: mac dinh Groq tu dat
    # reasoning_effort=medium, va model dot GAN HET ngan sach token mac dinh
    # (2048) vao phan suy nghi AN, khong con cho de in cau tra loi -> tra loi
    # bi cat ngang giua chung (finish_reason=length, content rong).
    # Da kiem chung: dat "low" thi finish_reason=stop, reasoning_tokens giam
    # tu ~2046 xuong ~28, tong token/luot goi giam manh (2048+ -> ~500).
    # Chi ap dung cho vai tro "research" (xem app/core/llm.py) va chi khi model
    # thuc su la gpt-oss -- de trong ("") de tat neu doi sang model khac.
    research_reasoning_effort: str = field(
        default_factory=lambda: _env("RESEARCH_REASONING_EFFORT", "low")
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

    # --- Lưu trữ hội thoại (chỉ web UI dùng, CLI không đụng tới) ---
    #
    # Để TRỐNG -> dùng file SQLite ngay trong repo (dev trên máy, không cần mạng).
    # Khi deploy PHẢI trỏ sang Postgres ngoài, vì Render free tier xoá sạch ổ đĩa
    # mỗi lần restart/deploy: file SQLite nằm trên server sẽ bốc hơi cùng lịch sử
    # hội thoại của người dùng. Dạng chuỗi:
    #   postgresql+psycopg://user:pass@host/dbname?sslmode=require
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))

    # Số LƯỢT hỏi-đáp cũ được gửi lại cho agent khi người dùng hỏi tiếp trong một
    # hội thoại. Đây là dây phanh chi phí: mỗi lượt gửi lại là thêm token cho MỌI
    # lần gọi LLM của lượt mới (supervisor + agent con + tổng hợp). Để quá cao vừa
    # đốt hạn mức vừa dễ dính 400 output_parse_failed vì hội thoại phình to.
    history_max_turns: int = field(default_factory=lambda: _env_int("HISTORY_MAX_TURNS", 6))

    # --- Đăng nhập bằng Google (tuỳ chọn) ---
    # Client ID lấy ở Google Cloud Console. Đây là giá trị CÔNG KHAI, nằm ngay
    # trong HTML gửi xuống trình duyệt — không phải bí mật, không cần giấu.
    google_client_id: str = field(default_factory=lambda: _env("GOOGLE_CLIENT_ID"))

    # Khoá để KÝ phiếu đăng nhập của chính hệ thống này (không phải của Google).
    # Đây MỚI là bí mật: ai biết nó có thể tự ký phiếu và mạo danh người khác.
    # Để trống -> tắt đăng nhập, web chạy chế độ ẩn danh như cũ.
    session_secret: str = field(default_factory=lambda: _env("SESSION_SECRET"))

    # Số ngày một lần đăng nhập còn hiệu lực trước khi phải đăng nhập lại.
    session_days: int = field(default_factory=lambda: _env_int("SESSION_DAYS", 30))

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

    def research_arch_hop_le(self) -> str:
        """RESEARCH_ARCH đã kiểm tra. Giá trị lạ -> báo lỗi rõ thay vì chạy sai âm thầm."""
        if self.research_arch not in RESEARCH_ARCHS:
            raise RuntimeError(
                f"RESEARCH_ARCH={self.research_arch!r} không hợp lệ. Chọn một trong "
                f"{list(RESEARCH_ARCHS)} (sửa trong .env, rồi kiểm tra: python -m app.main --config)."
            )
        return self.research_arch

    def research_mode_hop_le(self) -> str:
        """RESEARCH_MODE đã kiểm tra, cùng cách báo lỗi với research_arch_hop_le()."""
        if self.research_mode not in RESEARCH_MODES:
            raise RuntimeError(
                f"RESEARCH_MODE={self.research_mode!r} không hợp lệ. Chọn một trong "
                f"{list(RESEARCH_MODES)} (sửa trong .env, rồi kiểm tra: python -m app.main --config)."
            )
        return self.research_mode

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

    def mo_ta_database(self) -> str:
        """Mô tả nơi lưu hội thoại, KHÔNG in mật khẩu trong chuỗi kết nối."""
        raw = self.database_url
        if not raw:
            return "sqlite (mặc định, file trong repo) — KHÔNG bền khi deploy"
        if "://" not in raw:
            return "chuỗi DATABASE_URL sai định dạng"
        scheme, _, phan_con_lai = raw.partition("://")
        # Chuỗi Postgres có dạng user:mat_khau@host/db — cắt lấy phần sau '@'
        # để không bao giờ in mật khẩu ra màn hình hay log.
        host = phan_con_lai.split("@")[-1].split("/")[0]
        return f"{scheme} @ {host}" if host else f"{scheme} (file cục bộ)"

    def dang_nhap_bat(self) -> bool:
        """Chỉ bật đăng nhập khi có ĐỦ cả hai: Client ID để hỏi Google người này
        là ai, và khoá bí mật để tự ký phiếu đăng nhập. Thiếu một trong hai mà
        vẫn bật thì hoặc không đăng nhập được, hoặc phiếu ai cũng giả được."""
        return bool(self.google_client_id and self.session_secret)

    def mo_ta_dang_nhap(self) -> str:
        """Mô tả trạng thái đăng nhập, KHÔNG in khoá bí mật ra màn hình."""
        if self.dang_nhap_bat():
            return "Google (mỗi người thấy lịch sử của mình)"
        if self.google_client_id and not self.session_secret:
            return "TẮT — có GOOGLE_CLIENT_ID nhưng THIẾU SESSION_SECRET"
        if self.session_secret and not self.google_client_id:
            return "TẮT — có SESSION_SECRET nhưng THIẾU GOOGLE_CLIENT_ID"
        return "ẩn danh (lịch sử theo từng trình duyệt)"

    def mo_ta_cau_hinh(self) -> str:
        """Bảng tóm tắt vai trò -> provider/model, dùng cho `--config`."""
        dong = []
        for vai_tro, spec in (
            ("supervisor", self.model_supervisor),
            ("research", self.model_research),
            ("vision", self.model_vision),
            ("describe", self.model_describe),
            ("utility", self.model_utility),
            ("research_topic", self.model_research_topic),
        ):
            provider, model = self.split_model(spec)
            dong.append(f"  {vai_tro:<14} {provider:<7} {model or '(chưa đặt)'}")
        providers = sorted({self.split_model(s)[0] for s in (
            self.model_supervisor, self.model_research, self.model_vision,
            self.model_describe, self.model_utility,
            self.model_research_topic or self.model_research,
        )})
        dong.append("")
        for p in providers:
            dong.append(f"  key[{p}]: {self.key_kind(p)}")

        import sys

        dong.append("")
        dong.append(f"  python : {sys.executable}")
        trong_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
        dong.append(f"  venv   : {'có' if trong_venv else 'KHÔNG (đang dùng Python hệ thống)'}")
        dong.append(f"  research: arch={self.research_arch} mode={self.research_mode}")
        dong.append(f"  db     : {self.mo_ta_database()}")
        dong.append(f"  login  : {self.mo_ta_dang_nhap()}")
        if DOTENV_LOADED:
            dong.append(f"  .env   : đã nạp ({DOTENV_PATH})")
        elif DOTENV_PROBLEM:
            dong.append(f"  .env   : LỖI — {DOTENV_PROBLEM}")
        else:
            dong.append(f"  .env   : không có ({DOTENV_PATH})")
        return "\n".join(dong)


settings = Settings()
