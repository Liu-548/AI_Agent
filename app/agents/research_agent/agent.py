"""Research Agent — ReAct agent tra cứu arXiv + OpenAlex + Wikipedia.

Hợp đồng bắt buộc (xem QUY_TAC_THIET_KE.md, Bảng 3):
    AGENT_NAME, AGENT_DESCRIPTION, build_research_agent(model=None, tools=None, prompt=None)

Hai kiến trúc bên trong, chọn bằng RESEARCH_ARCH (mặc định "single"):
    single : MỘT ReAct agent với các tool tìm kiếm (hành vi gốc, không đổi).
    topics : research lead điều phối các agent chủ đề (scholar_agent, explainer_agent...).
Supervisor không thấy sự khác biệt: cả hai đều là node `research_agent`.
"""

from __future__ import annotations

from typing import List, Optional

from app.agents.research_agent.prompts import RESEARCH_AGENT_PROMPT

# PHẢI trùng tên thư mục chứa file này (quy tắc CT-05).
AGENT_NAME = "research_agent"
AGENT_DESCRIPTION = (
    "Use for research-related tasks: finding scientific papers on arXiv and OpenAlex "
    "(all fields, not just CS/physics), and looking up concepts/definitions on "
    "Wikipedia. Cannot see images. Always reports back in Vietnamese, as a short "
    "TOM TAT / CHI TIET / NGUON summary with numbered citations."
)


def build_research_agent(model=None, tools: Optional[List] = None, prompt: Optional[str] = None):
    """Điểm vào duy nhất theo hợp đồng IF-01/IF-03. Rẽ nhánh theo RESEARCH_ARCH.

    Đọc cấu hình LÚC GỌI (không import settings ở đầu file) để test đổi được kiến trúc.
    """
    from app.core import config

    if config.settings.research_arch_hop_le() == "topics":
        from app.agents.research_agent.lead import build_research_lead

        return build_research_lead(model=model, tools=tools, prompt=prompt)
    return _build_single_agent(model=model, tools=tools, prompt=prompt)


def _build_single_agent(model=None, tools: Optional[List] = None, prompt: Optional[str] = None):
    """Trả về một CompiledStateGraph chạy vòng lặp ReAct.

    model=None  -> LLM của vai trò "research" (cần LLM_API_KEY).
    tools=None  -> arxiv_search + openalex_search + wikipedia_search.
    """
    from langgraph.prebuilt import create_react_agent

    if model is None:
        from app.core.llm import get_llm

        model = get_llm("research")
    if tools is None:
        from app.agents.research_agent.tools import default_research_tools

        tools = default_research_tools()

    return create_react_agent(
        model=model,
        tools=tools,
        prompt=prompt or RESEARCH_AGENT_PROMPT,
        name=AGENT_NAME,
    )
