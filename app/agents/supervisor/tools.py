"""Tools bọc các sub-agents (Research & Vision) để Supervisor gọi trực tiếp."""

from __future__ import annotations

from typing import Any, Optional
from langchain_core.tools import BaseTool, tool

from app.agents.research_agent.agent import build_research_agent
from app.agents.vision_agent.agent import build_vision_agent

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


def _chay_agent_con(agent, query: str):
    """Chạy agent con, trả (câu trả lời cuối, artifact cho web UI).

    artifact KHÔNG gửi cho LLM của supervisor (response_format="content_and_artifact"),
    chỉ nằm trong ToolMessage.artifact để app/api.py đọc: kết quả tool bên trong
    agent con (ảnh khoanh vùng của YOLO...), các agent chủ đề đã chạy, bằng chứng.
    Không có lớp này thì supervisor-as-tool "nuốt" hết, UI chỉ thấy câu trả lời trần.
    """
    from langchain_core.messages import ToolMessage

    from app.core.pretty import message_text

    result = agent.invoke({"messages": [("user", query)]})
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


@tool("research_agent_tool", response_format="content_and_artifact")
def research_tool(query: str):
    """Use for ANY information question: scientific papers (arXiv, OpenAlex...), explanations
    of concepts (Wikipedia), and recent news, interviews or events (news search).
    Input should be a clear, self-contained question.
    """
    return _chay_agent_con(get_research_agent(), query)


@tool("vision_agent_tool", response_format="content_and_artifact")
def vision_tool(query: str, image_path: Optional[str] = None):
    """Useful for analyzing images, object detection/counting with YOLO, or visual description.
    Input should be a clear query describing what to analyze or detect.
    """
    # Ghép image_path vào query nếu Supervisor truyền riêng biệt
    full_query = query
    if image_path and image_path not in query:
        full_query = f"{query} Image: {image_path}"
    return _chay_agent_con(get_vision_agent(), full_query)


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