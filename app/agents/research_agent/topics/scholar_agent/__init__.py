"""scholar_agent — agent chủ đề tìm bài báo khoa học. File này CHỈ re-export (CT-04)."""

from app.agents.research_agent.topics.scholar_agent.agent import (
    TOPIC_DESCRIPTION,
    TOPIC_NAME,
    build_scholar_agent,
)
from app.agents.research_agent.topics.scholar_agent.tools import default_scholar_tools

__all__ = ["TOPIC_NAME", "TOPIC_DESCRIPTION", "build_scholar_agent", "default_scholar_tools"]
