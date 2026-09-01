"""Test lớp cấu hình LLM: tách provider:model, chọn đúng client, báo lỗi rõ ràng.

Không gọi mạng, không cần key thật.
"""

from __future__ import annotations

import importlib

import pytest

# Key giả GHÉP TỪ MẢNH — test test_khong_hardcode_api_key_trong_source quét cả
# thư mục tests/ và sẽ báo đỏ nếu thấy chuỗi liền trông giống key thật.
KEY_GEMINI = "AQ." + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
KEY_GROQ = "gsk_" + "abcdefghijklmnopqrstuvwxyz0123456789"
KEY_OPENAI = "sk-" + "proj-abcdefghijklmnopqrstuvwxyz"
COMPAT_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

BIEN = (
    "LLM_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY",
    "LLM_PROVIDER", "LLM_BASE_URL", "OPENAI_BASE_URL", "VISION_DETAIL",
    "MODEL_SUPERVISOR", "MODEL_RESEARCH", "MODEL_VISION", "MODEL_DESCRIBE", "MODEL_UTILITY",
)


def _reload(monkeypatch, **env):
    for k in BIEN:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import app.core.config as cfg
    import app.core.llm as llm_mod

    importlib.reload(cfg)
    importlib.reload(llm_mod)
    return cfg.settings, llm_mod


# --------------------------- tách provider:model --------------------------- #
def test_tach_tien_to_provider(monkeypatch):
    settings, _ = _reload(monkeypatch, GROQ_API_KEY=KEY_GROQ)
    assert settings.split_model("groq:llama-3.3-70b-versatile") == (
        "groq",
        "llama-3.3-70b-versatile",
    )
    assert settings.split_model("google:gemini-3.5-flash-lite") == (
        "google",
        "gemini-3.5-flash-lite",
    )


def test_ten_model_co_dau_gach_cheo_van_tach_dung(monkeypatch):
    """Model của Groq có dạng openai/gpt-oss-120b — dấu '/' không được nhầm là provider."""
    settings, _ = _reload(monkeypatch, GROQ_API_KEY=KEY_GROQ)
    assert settings.split_model("groq:openai/gpt-oss-120b") == ("groq", "openai/gpt-oss-120b")


def test_khong_co_tien_to_thi_dung_provider_mac_dinh(monkeypatch):
    settings, _ = _reload(monkeypatch, LLM_PROVIDER="google", LLM_API_KEY=KEY_GEMINI)
    assert settings.split_model("gemini-3.6-flash") == ("google", "gemini-3.6-flash")


def test_tien_to_la_khong_hop_le_thi_coi_nhu_khong_co(monkeypatch):
    settings, _ = _reload(monkeypatch, LLM_PROVIDER="groq", GROQ_API_KEY=KEY_GROQ)
    assert settings.split_model("meta:llama-x") == ("groq", "meta:llama-x")


# --------------------------- chọn đúng client ------------------------------ #
def test_cau_hinh_lai_dung_hai_client_khac_nhau(monkeypatch):
    """Điểm mấu chốt của phương án lai: chữ chạy Groq, ảnh chạy Google."""
    _, llm_mod = _reload(
        monkeypatch,
        GROQ_API_KEY=KEY_GROQ,
        GEMINI_API_KEY=KEY_GEMINI,
        MODEL_RESEARCH="groq:openai/gpt-oss-120b",
        MODEL_DESCRIBE="google:gemini-3.5-flash-lite",
    )
    assert type(llm_mod.get_llm("research")).__name__ == "ChatOpenAI"
    assert type(llm_mod.get_llm("describe")).__name__ == "ChatGoogleGenerativeAI"


def test_groq_dung_dung_base_url(monkeypatch):
    settings, llm_mod = _reload(monkeypatch, GROQ_API_KEY=KEY_GROQ, MODEL_RESEARCH="groq:x")
    assert "api.groq.com" in settings.base_url_for("groq")
    assert "api.groq.com" in str(llm_mod.get_llm("research").openai_api_base)


def test_van_chay_duoc_openai_that(monkeypatch):
    _, llm_mod = _reload(
        monkeypatch,
        OPENAI_API_KEY=KEY_OPENAI,
        MODEL_RESEARCH="openai:gpt-4o-mini",
        LLM_BASE_URL="https://api.openai.com/v1",
    )
    assert type(llm_mod.get_llm("research")).__name__ == "ChatOpenAI"


# --------------------------- lỗi cấu hình ---------------------------------- #
def test_thieu_key_bao_dung_ten_bien_va_trang_lay_key(monkeypatch):
    settings, _ = _reload(monkeypatch, GROQ_API_KEY=KEY_GROQ)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        settings.api_key_for("google")
    with pytest.raises(RuntimeError, match="aistudio.google.com"):
        settings.api_key_for("google")


def test_key_AQ_cong_endpoint_tuong_thich_openai_bi_chan_som(monkeypatch):
    settings, _ = _reload(monkeypatch, OPENAI_API_KEY=KEY_GEMINI, LLM_BASE_URL=COMPAT_URL)
    with pytest.raises(RuntimeError, match="AQ"):
        settings.api_key_for("openai")


def test_role_khong_hop_le_bao_loi(monkeypatch):
    _, llm_mod = _reload(monkeypatch, GROQ_API_KEY=KEY_GROQ)
    with pytest.raises(ValueError, match="role"):
        llm_mod.get_llm("agent")


def test_provider_khong_hop_le_bao_loi(monkeypatch):
    _, llm_mod = _reload(
        monkeypatch, LLM_PROVIDER="mistral", LLM_API_KEY=KEY_GROQ, MODEL_RESEARCH="abc"
    )
    with pytest.raises(ValueError, match="cung c"):
        llm_mod.get_llm("research")


def test_mo_ta_cau_hinh_khong_lo_key(monkeypatch):
    settings, _ = _reload(monkeypatch, GROQ_API_KEY=KEY_GROQ, GEMINI_API_KEY=KEY_GEMINI)
    mo_ta = settings.mo_ta_cau_hinh()
    assert "supervisor" in mo_ta and "describe" in mo_ta
    assert KEY_GROQ not in mo_ta and KEY_GEMINI not in mo_ta
