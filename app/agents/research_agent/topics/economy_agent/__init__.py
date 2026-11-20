"""economy_agent — agent chủ đề kinh tế vĩ mô và tỷ giá. File này CHỈ re-export (CT-04)."""

from app.agents.research_agent.topics.economy_agent.agent import TOPIC_DESCRIPTION, TOPIC_NAME, build_economy_agent
from app.agents.research_agent.topics.economy_agent.tools import default_economy_tools

__all__ = ["TOPIC_NAME", "TOPIC_DESCRIPTION", "build_economy_agent", "default_economy_tools"]
