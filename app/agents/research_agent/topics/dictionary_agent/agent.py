"""dictionary_agent — chủ đề "từ vựng tiếng Anh": nghĩa, phát âm, từ loại, ví dụ, từ đồng nghĩa.

Tên thư mục = TOPIC_NAME = tên tool = name= của create_react_agent (giống CT-05).
"""

from __future__ import annotations

from typing import List, Optional

from app.agents.research_agent.topics.dictionary_agent.prompts import DICTIONARY_AGENT_PROMPT

TOPIC_NAME = "dictionary_agent"
TOPIC_DESCRIPTION = (
    "Use for ENGLISH WORDS: meaning of a word or idiom, pronunciation (IPA), part of speech, "
    "example sentences, synonyms and antonyms. Returns a short cited answer from the Free "
    "Dictionary API (Wiktionary data) and Wikipedia. Do NOT use to explain a scientific or "
    "technical concept in depth (explainer_agent) or to translate long text."
)


def build_dictionary_agent(model=None, tools: Optional[List] = None, prompt: Optional[str] = None):
    """model=None -> LLM vai trò "research_topic"; tools=None -> dictionary_lookup + wikipedia."""
    from langgraph.prebuilt import create_react_agent

    if model is None:
        from app.core.llm import get_llm

        model = get_llm("research_topic")
    if tools is None:
        from app.agents.research_agent.profiles import get_profile
        from app.agents.research_agent.tools import SearchBudget
        from app.agents.research_agent.topics.dictionary_agent.tools import default_dictionary_tools

        profile = get_profile()
        tools = default_dictionary_tools(SearchBudget(max_calls=profile.max_searches_per_topic), profile)

    return create_react_agent(model=model, tools=tools, prompt=prompt or DICTIONARY_AGENT_PROMPT, name=TOPIC_NAME)
