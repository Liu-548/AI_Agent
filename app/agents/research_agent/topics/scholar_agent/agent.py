"""scholar_agent — chủ đề "tìm, lọc và trích bài báo khoa học" (mọi lĩnh vực, kể cả y sinh).

Tên thư mục = TOPIC_NAME = tên tool = name= của create_react_agent (giống CT-05).
Lĩnh vực không phải là ranh giới giữa các agent: y sinh chỉ là một tool (pubmed_search)
mà agent này gọi thêm khi câu hỏi thuộc y sinh.
"""

from __future__ import annotations

from typing import List, Optional

from app.agents.research_agent.topics.scholar_agent.prompts import SCHOLAR_AGENT_PROMPT

TOPIC_NAME = "scholar_agent"
TOPIC_DESCRIPTION = (
    "Use to FIND, compare or cite scholarly papers (journal articles, conference papers, "
    "preprints) in any research field, including biomedical. Returns a short cited summary "
    "of the most relevant papers. Do NOT use for plain definitions or explanations of a "
    "concept; use explainer_agent for that."
)


def build_scholar_agent(model=None, tools: Optional[List] = None, prompt: Optional[str] = None):
    """Trả về một CompiledStateGraph ReAct.

    model=None -> LLM của vai trò "research_topic".
    tools=None -> paper_search + pubmed_search + doi_lookup với profile hiện hành.
    """
    from langgraph.prebuilt import create_react_agent

    if model is None:
        from app.core.llm import get_llm

        model = get_llm("research_topic")
    if tools is None:
        from app.agents.research_agent.profiles import get_profile
        from app.agents.research_agent.tools import SearchBudget
        from app.agents.research_agent.topics.scholar_agent.tools import default_scholar_tools

        profile = get_profile()
        tools = default_scholar_tools(SearchBudget(max_calls=profile.max_searches_per_topic), profile)

    return create_react_agent(
        model=model,
        tools=tools,
        prompt=prompt or SCHOLAR_AGENT_PROMPT,
        name=TOPIC_NAME,
    )
