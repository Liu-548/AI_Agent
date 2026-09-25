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


# --------------------------------------------------------------------------- #
# Chính sách grounding (tầng 1 và tầng 2 dùng chung)
# --------------------------------------------------------------------------- #
BANG_CHUNG = """[1] Title: RoFormer: Enhanced Transformer with Rotary Position Embedding
    Label: [http://arxiv.org/abs/2104.09864v5]
    Other IDs: doi:10.1016/j.neucom.2023.127063 | openalex:W3155807546
    Published: 2021-04-20
"""
CAU_DUNG = "RoPE encodes absolute position with a rotation matrix [http://arxiv.org/abs/2104.09864v5]."
CAU_BIA = "A later work extends this idea to long contexts [http://arxiv.org/abs/2305.13052v1]."
CAU_KHONG_NHAN = "This technique is widely adopted in modern language models today."


def test_policy_xoa_cau_ma_arxiv_bia():
    from app.agents.research_agent.grounding_policy import apply_grounding_policy

    sach, bao_cao = apply_grounding_policy(f"{CAU_DUNG}\n{CAU_BIA}", BANG_CHUNG)
    assert sach == CAU_DUNG
    assert bao_cao["removed"] == 1
    assert bao_cao["violations"][0]["code"] == "MA_BIA"


def test_policy_cau_khong_nhan_duoc_giu_chi_dem():
    from app.agents.research_agent.grounding_policy import apply_grounding_policy

    goc = f"{CAU_DUNG}\n{CAU_KHONG_NHAN}"
    sach, bao_cao = apply_grounding_policy(goc, BANG_CHUNG)
    assert sach == goc
    assert (bao_cao["removed"], bao_cao["missing_source"]) == (0, 1)


def test_policy_xoa_het_thi_tra_khong_du_du_lieu():
    from app.agents.research_agent.grounding_policy import apply_grounding_policy

    sach, bao_cao = apply_grounding_policy(CAU_BIA, BANG_CHUNG)
    assert sach.startswith("KHONG DU DU LIEU:")
    assert bao_cao["removed"] == 1


@pytest.mark.parametrize("dong", ["KHONG DU DU LIEU: no papers found", "CAN_LAM_RO: Ban muon tim Mercury nao?"])
def test_policy_dong_dac_biet_di_qua_nguyen_ven(dong):
    from app.agents.research_agent.grounding_policy import apply_grounding_policy

    assert apply_grounding_policy(dong, "") == (dong, {"removed": 0, "missing_source": 0, "violations": []})


def test_policy_dang_so_bo_nguon_bia_va_cau_trich_no():
    from app.agents.research_agent.grounding_policy import apply_grounding_policy

    goc = (
        "TÓM TẮT\n"
        "RoPE encodes absolute position with a rotation matrix [1].\n"
        "\n"
        "CHI TIẾT\n"
        "- A later work extends this idea to long contexts [2].\n"
        "\n"
        "NGUỒN\n"
        "[1] http://arxiv.org/abs/2104.09864v5\n"
        "[2] http://arxiv.org/abs/2305.13052v1"
    )
    sach, bao_cao = apply_grounding_policy(goc, BANG_CHUNG)
    assert "2305.13052" not in sach and "[2]" not in sach
    assert "[1] http://arxiv.org/abs/2104.09864v5" in sach
    assert bao_cao["removed"] == 1


def test_policy_nhan_doi_dung_va_bia():
    from app.agents.research_agent.grounding_policy import apply_grounding_policy

    dung = "The model was published in a journal [doi: 10.1016/j.neucom.2023.127063]."
    bia = "The model was also cited elsewhere [doi: 10.9999/bia.dat]."
    assert apply_grounding_policy(dung, BANG_CHUNG)[0] == dung
    assert apply_grounding_policy(f"{dung}\n{bia}", BANG_CHUNG)[0] == dung
