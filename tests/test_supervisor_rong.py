"""Supervisor trả về RỖNG khi hội thoại dài ("(không có nội dung trả về)").

Gặp thật 05/11/2026: hội thoại 7 ảnh, nhiều bảng số liệu lớn -> gpt-oss-120b đốt hết
ngân sách token vào suy nghĩ ẩn, không gọi tool, không trả lời. Mở hội thoại mới thì
hết. Hai lớp sửa (KHÔNG đổi reasoning_effort của supervisor: nhóm đã cố ý giữ
nguyên, xem NHATKY_PHAT_TRIEN_RESEARCH_AGENT.md; lượt rỗng giờ được ghi log
finish_reason/token để có bằng chứng trước khi bàn lại):
  1. Câu trả lời CŨ gửi lại làm lịch sử bị rút gọn (HISTORY_MAX_CHARS).
  2. Vẫn rỗng mà chưa gọi tool nào -> thử lại MỘT lần với lịch sử ngắn; vẫn rỗng thì
     báo câu dễ hiểu thay vì "(không có nội dung trả về)".
"""

from __future__ import annotations

from langchain_core.messages import AIMessage

from tests.test_image_memory import he  # noqa: F401


def test_rut_gon_tra_loi_cu():
    from app import api

    ngan = "Có 2 con chó."
    assert api._rut_gon_tra_loi_cu(ngan, 700) == ngan
    bang = "Số liệu:\n" + "\n".join(f"| {n} | {n % 10}.0 |" for n in range(1990, 2024))
    gon = api._rut_gon_tra_loi_cu(bang, 120)
    assert len(gon) < 200 and gon.startswith("Số liệu:")
    assert gon.endswith("…(câu trả lời cũ đã được rút gọn)")
    assert api._rut_gon_tra_loi_cu(bang, 0) == bang  # 0 = không cắt


def test_lich_su_gui_lai_da_rut_gon(he):  # noqa: F811
    bang_dai = "Bảng:\n" + "\n".join(f"| Năm {n} | tỉ lệ lạm phát 1.0 % |" for n in range(1960, 2024))
    he.model.kich_ban(AIMessage(content=bang_dai))
    he.gui("Đọc biểu đồ giúp mình")
    he.model.kich_ban(AIMessage(content="Ok."))
    he.gui("Năm nào cao nhất?")
    tin_cu = [m for m in he.model.da_nhan[0] if m.type == "ai"]
    assert tin_cu and len(tin_cu[-1].content) < len(bang_dai)
    assert "đã được rút gọn" in tin_cu[-1].content


def test_rong_thi_thu_lai_voi_lich_su_ngan(he):  # noqa: F811
    he.model.kich_ban(AIMessage(content="Lượt đầu."))
    he.gui("Câu một")
    he.model.kich_ban(AIMessage(content=""), AIMessage(content="Trả lời sau khi thử lại."))
    tra_loi = he.gui("Câu hai")
    assert tra_loi["answer"] == "Trả lời sau khi thử lại."
    assert len(he.model.da_nhan) == 2  # đúng một lần thử lại


def test_van_rong_thi_bao_cau_de_hieu(he):  # noqa: F811
    he.model.kich_ban(AIMessage(content="Lượt đầu."))
    he.gui("Câu một")
    he.model.kich_ban(AIMessage(content=""), AIMessage(content=""))
    tra_loi = he.gui("Câu hai")
    assert "Cuộc trò chuyện mới" in tra_loi["answer"]
