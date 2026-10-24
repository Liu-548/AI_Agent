"""code_agent — agent chủ đề lập trình. File này CHỈ re-export (CT-04)."""

from app.agents.research_agent.topics.code_agent.agent import (
    TOPIC_DESCRIPTION,
    TOPIC_NAME,
    build_code_agent,
)
from app.agents.research_agent.topics.code_agent.tools import default_code_tools

__all__ = ["TOPIC_NAME", "TOPIC_DESCRIPTION", "build_code_agent", "default_code_tools"]
