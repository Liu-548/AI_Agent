"""openalex_search (RESEARCH_ARCH=single) phải gửi OPENALEX_API_KEY khi .env có key.

Từ 02/2026 OpenAlex bắt buộc key; trước đây đường single không gửi key nên luôn bị 429
dù người dùng đã điền key. Không gọi mạng: requests.get là hàm giả.
"""

from __future__ import annotations

import importlib


class _Resp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"results": []}


def _goi(monkeypatch, key):
    monkeypatch.setenv("OPENALEX_API_KEY", key)
    import app.core.config as cfg

    importlib.reload(cfg)
    from app.agents.research_agent import tools

    da_goi = {}

    def _get(url, params=None, timeout=None):
        da_goi.update(params or {})
        return _Resp()

    monkeypatch.setattr("requests.get", _get)
    tools.tim_openalex("pm2.5 hanoi", top_k=2, mailto="x@example.com")
    return da_goi


def test_co_key_thi_gui_kem(monkeypatch):
    assert _goi(monkeypatch, "abc123")["api_key"] == "abc123"


def test_khong_co_key_thi_nhu_cu(monkeypatch):
    assert "api_key" not in _goi(monkeypatch, "")
