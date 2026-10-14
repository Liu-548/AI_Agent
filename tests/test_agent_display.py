from app.core.agent_display import agent_model_details
from app.core.config import Settings


def test_direct_research_display_uses_configured_groq_model():
    config = Settings(model_research="groq:meta/llama-model")

    assert agent_model_details("research_agent", set(), config) == [
        ("Research", "groq", "meta/llama-model")
    ]


def test_supervisor_displays_each_agent_actually_invoked():
    config = Settings(
        model_research="groq:meta/llama-model",
        model_vision="google:gemini-vision",
    )

    assert agent_model_details(
        "__supervisor__",
        {"vision_agent_tool", "research_agent_tool"},
        config,
    ) == [
        ("Research", "groq", "meta/llama-model"),
        ("Vision", "google", "gemini-vision"),
    ]


def test_supervisor_without_subagent_displays_its_own_model():
    config = Settings(model_supervisor="groq:meta/llama-supervisor")

    assert agent_model_details("__supervisor__", set(), config) == [
        ("Supervisor", "groq", "meta/llama-supervisor")
    ]
