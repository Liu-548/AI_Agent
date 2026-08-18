"""Test lớp hiển thị — chống hồi quy lỗi 'in ra nguyên list Python'.

LangChain 1.x trả content dạng danh sách content block khi chạy model thinking
(Gemini 3). Nếu quên gộp lại, người dùng thấy `[{'type': 'text', 'text': '...\\n...'}]`
thay vì câu trả lời.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage

from app.core.pretty import final_text, get_final_messages, message_text

BLOCK_GEMINI = [
    {
        "type": "text",
        "text": "### RoPE\nLà phương pháp mã hoá vị trí.",
        "extras": {"signature": "Er0BCroBARFNMg9kPinVoZUG"},
    }
]


def test_content_chuoi_giu_nguyen():
    assert message_text("xin chào") == "xin chào"


def test_content_dang_block_duoc_gop_thanh_chu():
    assert message_text(BLOCK_GEMINI) == "### RoPE\nLà phương pháp mã hoá vị trí."


def test_bo_qua_block_suy_luan_va_chu_ky():
    content = [
        {"type": "thinking", "thinking": "người dùng muốn tìm paper..."},
        {"type": "text", "text": "Đây là kết quả."},
    ]
    assert message_text(content) == "Đây là kết quả."


def test_content_rong_hoac_none():
    assert message_text([]) == ""
    assert message_text(None) == ""


def test_final_text_tra_ve_chu_chu_khong_phai_list():
    chunk = {"agent": {"messages": [AIMessage(content=BLOCK_GEMINI, name="research_agent")]}}
    ket_qua = final_text(chunk)
    assert ket_qua.startswith("### RoPE")
    assert "'type'" not in ket_qua and "extras" not in ket_qua


def test_final_text_uu_tien_node_supervisor():
    chunk = {
        "research_agent": {"messages": [AIMessage(content="của agent con")]},
        "supervisor": {"messages": [AIMessage(content="của supervisor")]},
    }
    assert final_text(chunk) == "của supervisor"


def test_get_final_messages_khong_vo_khi_chunk_la_tuple():
    chunk = (("ns:1",), {"agent": {"messages": [AIMessage(content="ok")]}})
    assert len(get_final_messages(chunk)) == 1
