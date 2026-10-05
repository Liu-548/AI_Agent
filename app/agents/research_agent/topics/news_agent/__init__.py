"""news_agent — agent chủ đề tin tức / sự kiện gần đây. File này CHỈ re-export (CT-04)."""

from app.agents.research_agent.topics.news_agent.agent import (
    TOPIC_DESCRIPTION,
    TOPIC_NAME,
    build_news_agent,
)
from app.agents.research_agent.topics.news_agent.tools import default_news_tools

__all__ = ["TOPIC_NAME", "TOPIC_DESCRIPTION", "build_news_agent", "default_news_tools"]
