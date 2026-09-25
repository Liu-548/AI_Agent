"""TopicBudget — trần số lần research lead được gọi agent chủ đề cho MỘT câu hỏi.

Đặt trong CODE chứ không chỉ trong prompt: ở temperature 0 model hay lặp lại đúng
quyết định cũ (bài học của SearchBudget), nhắc trong prompt thì nó lờ được, còn
tool từ chối thì nó không lặp được.

Không dùng biến toàn cục. Bộ đếm được tính lại MỖI LẦN từ lịch sử tin nhắn của
lead (state), chỉ xét phần nằm SAU HumanMessage cuối cùng — nên câu hỏi mới thì
đếm lại từ đầu mà không cần cơ chế reset nào.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.contracts import tool_error
from app.core.pretty import message_text

# Lần gọi bị từ chối thì không tính vào ngân sách (nếu tính, một lần gọi trùng sẽ
# ăn mất lượt của một lần gọi hợp lệ về sau).
_TIEN_TO_BI_TU_CHOI = ("ERROR: TOPIC_BUDGET_EXCEEDED", "ERROR: TOPIC_DUPLICATE_CALL")


def _chuan_hoa(text: str) -> str:
    return " ".join((text or "").lower().split())


def cac_lan_goi_truoc(
    messages: List, ten_chu_de: Iterable[str], tool_call_id: str = ""
) -> List[Tuple[str, str]]:
    """[(tên chủ đề, câu con đã chuẩn hoá)] của các lần gọi ĐÃ được chấp nhận trước lần gọi hiện tại.

    Dựa vào tool_call của AIMessage (không phải ToolMessage) để cũng thấy được
    các lần gọi nằm CÙNG một lượt với lần hiện tại — ToolNode chạy chúng song
    song, lúc đó ToolMessage của lần kia chưa tồn tại.
    """
    ten_chu_de = set(ten_chu_de)
    sau_cuoi: List = []
    for m in messages or []:
        if isinstance(m, HumanMessage):
            sau_cuoi = []
        else:
            sau_cuoi.append(m)

    da_tra_loi = {
        m.tool_call_id: message_text(m.content)
        for m in sau_cuoi
        if isinstance(m, ToolMessage)
    }
    truoc: List[Tuple[str, str]] = []
    for m in sau_cuoi:
        if not isinstance(m, AIMessage):
            continue
        for lan_goi in m.tool_calls:
            if lan_goi["name"] not in ten_chu_de:
                continue
            if tool_call_id and lan_goi["id"] == tool_call_id:
                return truoc  # tới chính lần gọi đang xét: phía sau không tính
            if da_tra_loi.get(lan_goi["id"], "").startswith(_TIEN_TO_BI_TU_CHOI):
                continue
            truoc.append((lan_goi["name"], _chuan_hoa((lan_goi.get("args") or {}).get("text", ""))))
    return truoc


def check_topic_budget(
    messages: List,
    ten_chu_de: Iterable[str],
    ten: str,
    text: str,
    max_topic_calls: int,
    tool_call_id: str = "",
) -> Optional[str]:
    """None = cho gọi. Chuỗi "ERROR: ..." = từ chối (trả thẳng cho lead, không chạy agent con)."""
    truoc = cac_lan_goi_truoc(messages, ten_chu_de, tool_call_id)
    if len(truoc) >= max_topic_calls:
        return tool_error(
            "TOPIC_BUDGET_EXCEEDED",
            f"Đã gọi {len(truoc)}/{max_topic_calls} agent chủ đề cho câu hỏi này. "
            "DỪNG gọi tool và tổng hợp từ kết quả đã có; nói rõ phần nào chưa được tra.",
        )
    if (ten, _chuan_hoa(text)) in truoc:
        return tool_error(
            "TOPIC_DUPLICATE_CALL",
            f"Đã gọi {ten} với đúng câu con này. Kết quả nằm ngay phía trên trong hội thoại.",
        )
    return None
