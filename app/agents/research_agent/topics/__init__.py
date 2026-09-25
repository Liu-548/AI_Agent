"""Các agent chủ đề của research lead. File này CHỈ re-export (quy tắc CT-04)."""

from app.agents.research_agent.topics.registry import TOPIC_SPECS, TopicSpec, build_topic_tools
from app.agents.research_agent.topics.topic_tool import make_topic_tool

__all__ = ["TOPIC_SPECS", "TopicSpec", "build_topic_tools", "make_topic_tool"]
