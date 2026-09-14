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


@tool("research_agent_tool")
def research_tool(query: str) -> str:
    """Useful for searching scientific papers, arXiv, Wikipedia, or retrieving technical research information.
    Input should be a clear research query.
    """
    agent = get_research_agent()
    result = agent.invoke({"messages": [("user", query)]})
    if isinstance(result, dict) and "messages" in result:
        return result["messages"][-1].content
    return str(result)


@tool("vision_agent_tool")
def vision_tool(query: str, image_path: Optional[str] = None) -> str:
    """Useful for analyzing images, object detection/counting with YOLO, or visual description.
    Input should be a clear query describing what to analyze or detect.
    """
    agent = get_vision_agent()

    # Ghép image_path vào query nếu Supervisor truyền riêng biệt
    full_query = query
    if image_path and image_path not in query:
        full_query = f"{query} Image: {image_path}"

    result = agent.invoke({"messages": [("user", full_query)]})
    if isinstance(result, dict) and "messages" in result:
        return result["messages"][-1].content
    return str(result)


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