"""Resolve display labels for the agent and model used in a response."""

from __future__ import annotations

from collections.abc import Iterable

from app.core.config import Settings

_AGENT_DETAILS = {
    "research_agent": ("Research", "research"),
    "vision_agent": ("Vision", "vision"),
}
_SUPERVISOR_TOOL_TO_AGENT = {
    "research_agent_tool": "research_agent",
    "vision_agent_tool": "vision_agent",
}


def agent_model_details(
    agent_key: str, tool_names: Iterable[str], config: Settings
) -> list[tuple[str, str, str]]:
    """Return (agent label, provider, model) tuples for the completed request."""
    if agent_key == "__supervisor__":
        used_tools = set(tool_names)
        selected = [
            agent_name
            for tool_name, agent_name in _SUPERVISOR_TOOL_TO_AGENT.items()
            if tool_name in used_tools
        ]
        if not selected:
            return [_details_for_role("Supervisor", "supervisor", config)]
    else:
        selected = [agent_key]

    details = []
    for agent_name in selected:
        agent_label, role = _AGENT_DETAILS[agent_name]
        details.append(_details_for_role(agent_label, role, config))
    return details


def _details_for_role(
    agent_label: str, role: str, config: Settings
) -> tuple[str, str, str]:
    provider, model = config.split_model(getattr(config, f"model_{role}"))
    return agent_label, provider, model
