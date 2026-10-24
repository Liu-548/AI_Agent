"""travel_agent — agent chủ đề du lịch và địa điểm. File này CHỈ re-export (CT-04)."""

from app.agents.research_agent.topics.travel_agent.agent import (
    TOPIC_DESCRIPTION,
    TOPIC_NAME,
    build_travel_agent,
)
from app.agents.research_agent.topics.travel_agent.tools import default_travel_tools

__all__ = ["TOPIC_NAME", "TOPIC_DESCRIPTION", "build_travel_agent", "default_travel_tools"]
