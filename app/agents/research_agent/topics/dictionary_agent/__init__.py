"""dictionary_agent — agent chủ đề từ vựng tiếng Anh. File này CHỈ re-export (CT-04)."""

from app.agents.research_agent.topics.dictionary_agent.agent import (
    TOPIC_DESCRIPTION,
    TOPIC_NAME,
    build_dictionary_agent,
)
from app.agents.research_agent.topics.dictionary_agent.tools import default_dictionary_tools

__all__ = ["TOPIC_NAME", "TOPIC_DESCRIPTION", "build_dictionary_agent", "default_dictionary_tools"]
