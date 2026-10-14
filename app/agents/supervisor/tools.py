"""Tools bọc các sub-agents (Research & Vision) để Supervisor gọi trực tiếp."""

from __future__ import annotations

import re
from typing import Any, Optional, Tuple

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from app.agents.research_agent.agent import build_research_agent
from app.agents.vision_agent.agent import build_vision_agent
from app.agents.vision_agent.image_utils import extract_image_ref
from app.agents.vision_agent.tools import can_dem_vat_the, tra_loi_truc_tiep
from app.agents.vision_agent.topics import chon_chu_de, dung_chu_de
from app.core.contracts import tool_error

# Bí danh ảnh trong bộ nhớ hội thoại: "IMG3" (xem app/image_memory.py). Tầng web
# liệt kê ảnh cho supervisor bằng mã này thay vì đường dẫn file dài, rồi đưa một
# hàm đổi mã -> file qua config["configurable"]["image_resolver"].
_BI_DANH_RE = re.compile(r"\bIMG[\s_#-]?(\d{1,3})\b", re.IGNORECASE)
# Supervisor đôi khi chỉ truyền "3", "#3" hay "Ảnh 3" vào image_path.
_CHI_SO_RE = re.compile(
    r"^\s*(?:image|ảnh|anh|hình|hinh)?\s*#?\s*(\d{1,3})\s*$", re.IGNORECASE
)

# Quản lý Singleton instance để tránh rebuild agent mỗi lần gọi tool
_research_agent_instance = None
_vision_agent_instance = None


def get_research_agent():
    """Tái sử dụng instance của Research Agent."""
    global _research_agent_instance
    if _research_agent_instance is None:
        _research_agent_instance = build_research_agent()
    return _research_agent_instance


def get_vision_agent():
    """Tái sử dụng instance của Vision Agent."""
    global _vision_agent_instance
    if _vision_agent_instance is None:
        _vision_agent_instance = build_vision_agent()
    return _vision_agent_instance


def reset_sub_agent_instances():
    """Reset lại các singleton instances (dùng cho pytest/mocking)."""
    global _research_agent_instance, _vision_agent_instance
    _research_agent_instance = None
    _vision_agent_instance = None


def _chay_agent_con(agent, query: str, config: Optional[dict] = None):
    """Chạy agent con, trả (câu trả lời cuối, artifact cho web UI).

    artifact KHÔNG gửi cho LLM của supervisor (response_format="content_and_artifact"),
    chỉ nằm trong ToolMessage.artifact để app/api.py đọc: kết quả tool bên trong
    agent con (ảnh khoanh vùng của YOLO...), các agent chủ đề đã chạy, bằng chứng.
    Không có lớp này thì supervisor-as-tool "nuốt" hết, UI chỉ thấy câu trả lời trần.
    """
    from langchain_core.messages import ToolMessage

    from app.core.pretty import message_text

    result = agent.invoke({"messages": [("user", query)]})
    chuyen_ket_qua_tool_con(result, config)
    messages = result.get("messages", []) if isinstance(result, dict) else []
    if not messages:
        return str(result), {}
    tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
    topics, bang_chung = [], []
    for m in tool_msgs:
        a = m.artifact if isinstance(m.artifact, dict) else {}
        if "topic" in a:  # agent chủ đề của research lead (RESEARCH_ARCH=topics)
            topics.append({
                "topic": a["topic"], "status": a.get("status"), "sub_question": a.get("sub_question", ""),
                "usage": a.get("usage", {}), "removed": (a.get("grounding_report") or {}).get("removed", 0),
            })
            bang_chung.append(a.get("evidence_text") or "")
        else:
            bang_chung.append(message_text(m.content))
    artifact = {
        "tool_outputs": {m.name: message_text(m.content) for m in tool_msgs if m.name},
        "topics": topics,
        "evidence": "\n".join(bang_chung),
        "grounding": (getattr(messages[-1], "response_metadata", None) or {}).get("grounding"),
    }
    return message_text(messages[-1].content), artifact


def so_bi_danh(query: str, image_path: Optional[str]) -> Optional[int]:
    """Số thứ tự ảnh nếu supervisor gọi ảnh bằng bí danh (IMG3, "3", "#3"...)."""
    if image_path:
        khop = _BI_DANH_RE.search(image_path) or _CHI_SO_RE.match(image_path)
    else:
        khop = _BI_DANH_RE.search(query or "")
    return int(khop.group(1)) if khop else None


def chon_chu_de_cho_anh(query: str, so_anh: Optional[int], config: Optional[dict]) -> Optional[str]:
    """Chủ đề cho lượt nhìn ảnh này; None khi VISION_TOPICS tắt (hành vi như cũ)."""
    from app.core import config as app_config

    if not app_config.settings.vision_topics:
        return None
    giai = ((config or {}).get("configurable") or {}).get("image_resolver")
    chu_de_anh = None
    if so_anh is not None and giai is not None and hasattr(giai, "chu_de"):
        chu_de_anh = giai.chu_de(so_anh)
    return chon_chu_de(query, chu_de_anh)


def chuyen_ket_qua_tool_con(result: Any, config: Optional[dict]) -> None:
    """Đưa kết quả các tool BÊN TRONG agent con ra ngoài cho tầng web.

    Supervisor chỉ thấy câu trả lời cuối của `vision_agent_tool`; kết quả thô của
    `detect_and_count_objects` (số đếm, khung, ảnh khoanh vùng) và lỗi của tool con
    (vd YOLO chưa cài) nằm trong tin nhắn của agent con và bị mất. Tầng web đưa vào
    `config["configurable"]["tool_sink"]` một dict; ở đây ghi vào đó theo tên tool.
    Không có dict (CLI, test cũ) thì không làm gì. Gọi cùng một tool nhiều lần: giữ lần
    sau cùng.
    """
    kho = ((config or {}).get("configurable") or {}).get("tool_sink")
    if kho is None or not isinstance(result, dict):
        return
    for tin in result.get("messages") or []:
        ten = getattr(tin, "name", None)
        if getattr(tin, "type", None) == "tool" and ten:
            noi_dung = getattr(tin, "content", "")
            kho[ten] = noi_dung if isinstance(noi_dung, str) else str(noi_dung)


def thu_tra_loi_truc_tiep(query: str, image_path: Optional[str]) -> Optional[str]:
    """Thử trả lời bằng MỘT lượt model nhìn ảnh. None = hãy đi đường agent cũ.

    Đi đường cũ khi: VISION_DIRECT tắt, câu hỏi cần đếm / phát hiện vật thể (phải
    qua YOLO), không tìm được ảnh, hoặc lượt gọi model lỗi. Hàm KHÔNG raise: đường
    nhanh chỉ là phần tăng tốc, không được làm hỏng câu trả lời đang có.
    """
    from app.core import config as app_config

    if not app_config.settings.vision_direct or can_dem_vat_the(query):
        return None
    try:
        ref = image_path or extract_image_ref(query)
        if not ref:
            return None
        cau_hoi = query.replace(ref, "").strip() or query
        ket_qua = tra_loi_truc_tiep(ref, cau_hoi)
    except Exception:  # noqa: BLE001
        return None
    return None if ket_qua.startswith("ERROR:") else ket_qua


def giai_bi_danh_anh(
    query: str, image_path: Optional[str], config: Optional[dict]
) -> Tuple[Optional[str], Optional[str]]:
    """Đổi bí danh ảnh (IMG3) thành đường dẫn file thật.

    Trả (image_path, lỗi). Không có hàm đổi trong config (CLI, khách vãng lai),
    hoặc supervisor truyền thẳng đường dẫn/URL thật -> trả nguyên image_path,
    hành vi y như trước khi có bộ nhớ ảnh.
    """
    giai = ((config or {}).get("configurable") or {}).get("image_resolver")
    if giai is None:
        return image_path, None

    so = so_bi_danh(query, image_path)
    if so is None:
        return image_path, None

    duong_dan = giai(so)
    if not duong_dan:
        return None, tool_error(
            "IMAGE_NOT_IN_MEMORY",
            f"IMG{so} is not available any more (unknown id, or the stored file is gone). "
            "Use only ids listed in IMAGE MEMORY, or ask the user to send the image again.",
        )
    return duong_dan, None


@tool("research_agent_tool", response_format="content_and_artifact")
def research_tool(query: str):
    """Use for ANY information question: scientific papers (arXiv, OpenAlex...), explanations
    of concepts (Wikipedia), and recent news, interviews or events (news search).
    Input should be a clear, self-contained question.
    """
    return _chay_agent_con(get_research_agent(), query)


@tool("vision_agent_tool", response_format="content_and_artifact")
def vision_tool(
    query: str, image_path: Optional[str] = None, config: RunnableConfig = None
):
    """Useful for analyzing images, object detection/counting with YOLO, or visual description.
    Input should be a clear query describing what to analyze or detect.
    `image_path` is the image to look at: an id from IMAGE MEMORY such as "IMG3",
    or a file path / URL exactly as the user gave it. One image per call.
    """
    so_anh = so_bi_danh(query, image_path)
    image_path, loi = giai_bi_danh_anh(query, image_path, config)
    if loi:
        return loi, {}

    # Ghép image_path vào query nếu Supervisor truyền riêng biệt
    full_query = query
    if image_path and image_path not in query:
        full_query = f"{query} Image: {image_path}"

    # Chủ đề ảnh: lời dặn riêng cho lượt nhìn ảnh (xem topics.py). Không có chủ đề
    # trong hồ sơ (khách vãng lai, ảnh cũ) thì chỉ dựa vào câu hỏi, rồi đến "chung".
    with dung_chu_de(chon_chu_de_cho_anh(query, so_anh, config)):
        # Đường nhanh: một lượt model nhìn ảnh và trả lời luôn (xem VISION_DIRECT).
        nhanh = thu_tra_loi_truc_tiep(query, image_path)
        if nhanh is not None:
            return nhanh, {}
        return _chay_agent_con(get_vision_agent(), full_query, config)


def make_sub_agent_tool(agent: Any) -> BaseTool:
    """Bọc động một agent (LangGraph CompiledGraph hoặc object) thành một LangChain Tool hợp lệ.
    
    Phục vụ cho việc test contract cũ và hỗ trợ truyền `agents=[...]` vào build_supervisor.
    """
    if isinstance(agent, BaseTool):
        return agent

    agent_name = getattr(agent, "name", None) or getattr(agent, "__name__", "sub_agent")
    tool_name = f"{agent_name}_tool" if not agent_name.endswith("_tool") else agent_name

    @tool(tool_name)
    def dynamic_sub_agent_tool(query: str) -> str:
        """Forward query to the sub-agent and return the final response text."""
        if hasattr(agent, "invoke"):
            res = agent.invoke({"messages": [("user", query)]})
            if isinstance(res, dict) and "messages" in res:
                return res["messages"][-1].content
            return str(res)
        return f"Agent {agent_name} executed."

    return dynamic_sub_agent_tool


# Tập hợp danh sách các tools mặc định cho Supervisor
SUPERVISOR_TOOLS = [research_tool, vision_tool]