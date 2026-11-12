"""Bấm "Dừng" rồi sửa câu hỏi: lượt đã dừng KHÔNG được lưu vào lịch sử hội thoại.

Server không ngắt được lượt đang gọi model, nên trình duyệt gửi /api/ask/cancel với mã
lượt; khi lượt đó chạy xong, server bỏ kết quả thay vì lưu câu hỏi viết lộn (câu đó sẽ
bị gửi kèm làm ngữ cảnh cho các câu sau).
"""

from __future__ import annotations

from langchain_core.messages import AIMessage

from tests.test_image_memory import he  # noqa: F401


def test_luot_da_huy_khong_duoc_luu(he):  # noqa: F811
    he.model.kich_ban(AIMessage(content="Câu trả lời cho câu viết lộn."))
    assert he.client.post("/api/ask/cancel", data={"request_id": "luot-1"}).json() == {"cancelled": "luot-1"}
    r = he.client.post("/api/ask", data={"question": "cau viet lon", "request_id": "luot-1"}, headers=he.headers)
    assert r.status_code == 200 and r.json()["cancelled"] is True
    assert "conversation_id" not in r.json()
    # gửi lại câu đã sửa (mã lượt mới) -> lưu bình thường, lịch sử chỉ có câu đã sửa
    he.model.kich_ban(AIMessage(content="Trả lời câu đã sửa."))
    r2 = he.client.post("/api/ask", data={"question": "cau da sua", "request_id": "luot-2"}, headers=he.headers)
    cid = r2.json()["conversation_id"]
    tin = he.store.lay_tin_nhan(cid)
    assert [t["content"] for t in tin] == ["cau da sua", "Trả lời câu đã sửa."]


def test_khong_co_ma_luot_thi_nhu_cu(he):  # noqa: F811
    he.model.kich_ban(AIMessage(content="Ok."))
    r = he.client.post("/api/ask", data={"question": "xin chao"}, headers=he.headers)
    assert r.json()["answer"] == "Ok." and r.json()["conversation_id"]
