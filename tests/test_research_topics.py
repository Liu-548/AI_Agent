"""Test cho chế độ "topics" của Research Agent (registry, topic tool, lead, profile...).

Toàn bộ chạy OFFLINE: model giả + HTTP giả. Không gọi LLM, không tốn hạn mức.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.core import config


def _dung_settings(monkeypatch, **thay_doi):
    """Đổi cấu hình cho một test: settings là frozen nên dựng bản mới bằng replace()."""
    monkeypatch.setattr(config, "settings", replace(config.settings, **thay_doi))


# --------------------------------------------------------------------------- #
# Profile
# --------------------------------------------------------------------------- #
def test_profile_mac_dinh_la_standard():
    from app.agents.research_agent.profiles import get_profile

    p = get_profile()
    assert p.name == "standard"
    assert (p.max_topic_calls, p.max_searches_per_topic, p.max_results) == (2, 3, 5)


@pytest.mark.parametrize(
    "mode,topic_calls,searches", [("eco", 1, 2), ("standard", 2, 3), ("full", 3, 5)]
)
def test_profile_theo_research_mode(monkeypatch, mode, topic_calls, searches):
    from app.agents.research_agent.profiles import get_profile

    _dung_settings(monkeypatch, research_mode=mode)
    p = get_profile()
    assert (p.name, p.max_topic_calls, p.max_searches_per_topic) == (mode, topic_calls, searches)


def test_profile_gia_tri_la_bao_loi_ro(monkeypatch):
    from app.agents.research_agent.profiles import get_profile

    _dung_settings(monkeypatch, research_mode="turbo")
    with pytest.raises(RuntimeError, match="RESEARCH_MODE"):
        get_profile()


def test_research_max_searches_ghi_de_khi_duoc_dat(monkeypatch):
    from app.agents.research_agent.profiles import get_profile

    # Không đặt -> giữ số của profile, dù mặc định của biến cũ là 6.
    assert get_profile().max_searches_per_topic == 3
    _dung_settings(monkeypatch, research_max_searches=1, research_max_searches_set=True)
    assert get_profile().max_searches_per_topic == 1


def test_research_arch_gia_tri_la_bao_loi_ro(monkeypatch):
    _dung_settings(monkeypatch, research_arch="mesh")
    with pytest.raises(RuntimeError, match="RESEARCH_ARCH"):
        config.settings.research_arch_hop_le()


def test_vai_tro_research_topic_da_dang_ky():
    from app.core.llm import _MODEL_SPEC_BY_ROLE

    assert "research_topic" in _MODEL_SPEC_BY_ROLE
    assert "research_topic" in config.settings.mo_ta_cau_hinh()
