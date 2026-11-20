"""weather_agent — agent chủ đề thời tiết. File này CHỈ re-export (CT-04)."""

from app.agents.research_agent.topics.weather_agent.agent import TOPIC_DESCRIPTION, TOPIC_NAME, build_weather_agent
from app.agents.research_agent.topics.weather_agent.tools import default_weather_tools

__all__ = ["TOPIC_NAME", "TOPIC_DESCRIPTION", "build_weather_agent", "default_weather_tools"]
