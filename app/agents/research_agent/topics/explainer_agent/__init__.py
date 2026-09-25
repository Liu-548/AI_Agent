"""explainer_agent — agent chủ đề giải thích khái niệm. File này CHỈ re-export (CT-04)."""

from app.agents.research_agent.topics.explainer_agent.agent import (
    TOPIC_DESCRIPTION,
    TOPIC_NAME,
    build_explainer_agent,
)
from app.agents.research_agent.topics.explainer_agent.tools import default_explainer_tools

__all__ = ["TOPIC_NAME", "TOPIC_DESCRIPTION", "build_explainer_agent", "default_explainer_tools"]
