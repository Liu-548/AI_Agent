"""Tools bọc các sub-agents (Research & Vision) để Supervisor gọi trực tiếp."""

from __future__ import annotations

from typing import Optional
from langchain_core.tools import tool

# Import các hàm khởi tạo agent sẵn có trong dự án
from app.agents.research_agent.agent import build_research_agent
from app.agents.vision_agent.agent import build_vision_agent


@tool
def research_tool(query: str) -> str:
    """Useful for searching scientific papers, arXiv, Wikipedia, or retrieving technical research information.
    Input should be a clear research query.
    """
    # Khởi tạo instance của Research Agent và thực thi
    agent = build_research_agent()
    result = agent.invoke({"messages": [("user", query)]})
    return result["messages"][-1].content


@tool
def vision_tool(query: str, image_path: Optional[str] = None) -> str:
    """Useful for analyzing images, object detection/counting with YOLO, or visual description.
    Input requires user query and optionally the local image path.
    """
    agent = build_vision_agent()
    input_payload = {"messages": [("user", query)]}
    if image_path:
        input_payload["image_path"] = image_path

    result = agent.invoke(input_payload)
    return result["messages"][-1].content


# Tập hợp danh sách các tools cho Supervisor
SUPERVISOR_TOOLS = [research_tool, vision_tool]