"""In trạng thái agent khi stream — bản dùng chung cho cả 3 agent.

Lưu ý quan trọng về LangChain 1.x: `AIMessage.content` không còn luôn là `str`.
Với model thinking (Gemini 3) nó là **danh sách content block**, ví dụ:

    [{'type': 'text', 'text': '...', 'extras': {'signature': 'Er0BCroB...'}}]

Nếu cứ in thẳng `content` ra thì người dùng thấy nguyên cái list Python kèm `\\n`
thoát chuỗi, không đọc được. Mọi chỗ cần "chữ" phải đi qua `message_text()`.
"""

from __future__ import annotations

from typing import Any, List


def message_text(content: Any) -> str:
    """Gộp content của một message thành chuỗi thuần, bỏ qua block không phải text.

    Chấp nhận: str | list[str | dict] | None. Không bao giờ raise.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        phan_chu: List[str] = []
        for block in content:
            if isinstance(block, str):
                phan_chu.append(block)
            elif isinstance(block, dict):
                # Bỏ qua block suy luận nội bộ ('thinking'/'reasoning') — chỉ lấy chữ.
                if block.get("type") in (None, "text") and isinstance(block.get("text"), str):
                    phan_chu.append(block["text"])
        return "\n".join(p for p in phan_chu if p)
    return str(content)


def _chuan_hoa(message: Any) -> Any:
    """Trả về bản sao message với content đã gộp thành chuỗi, để pretty_repr đọc được."""
    content = getattr(message, "content", None)
    if not isinstance(content, list):
        return message
    try:
        return message.model_copy(update={"content": message_text(content)})
    except Exception:
        return message


def pretty_print_message(message: Any, indent: bool = False) -> None:
    pretty = _chuan_hoa(message).pretty_repr(html=False)
    if not indent:
        print(pretty)
        return
    print("\n".join("\t" + line for line in pretty.split("\n")))


def pretty_print_messages(update: Any, last_message: bool = False) -> None:
    from langchain_core.messages import convert_to_messages

    is_subgraph = False
    if isinstance(update, tuple):
        ns, update = update
        if len(ns) == 0:
            return
        graph_id = ns[-1].split(":")[0]
        print(f"Update from subgraph {graph_id}:\n")
        is_subgraph = True

    if not isinstance(update, dict):
        return

    for node_name, node_update in update.items():
        if not isinstance(node_update, dict) or "messages" not in node_update:
            continue
        label = f"Update from node {node_name}:"
        print(("\t" + label if is_subgraph else label) + "\n")
        messages = convert_to_messages(node_update["messages"])
        if last_message:
            messages = messages[-1:]
        for m in messages:
            pretty_print_message(m, indent=is_subgraph)
        print("\n")


def get_final_messages(last_chunk: Any) -> List[Any]:
    """Lấy messages từ chunk cuối của .stream() mà không sợ KeyError.

    Chunk cuối không chắc đến từ node 'supervisor' (có thể từ subgraph).
    """
    if last_chunk is None:
        return []
    if isinstance(last_chunk, tuple):
        _, last_chunk = last_chunk
    if not isinstance(last_chunk, dict):
        return []
    if "supervisor" in last_chunk and isinstance(last_chunk["supervisor"], dict):
        return last_chunk["supervisor"].get("messages", [])
    for node_update in last_chunk.values():
        if isinstance(node_update, dict) and "messages" in node_update:
            return node_update["messages"]
    return []


def final_text(last_chunk: Any) -> str:
    """Câu trả lời cuối cùng, dạng chuỗi đọc được."""
    messages = get_final_messages(last_chunk)
    if not messages:
        return ""
    last = messages[-1]
    content = last.get("content") if isinstance(last, dict) else getattr(last, "content", None)
    return message_text(content)
