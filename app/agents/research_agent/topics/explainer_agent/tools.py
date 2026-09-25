"""Tool lá của explainer_agent: TÁI DÙNG wikipedia_search và arxiv_search cũ.

Cùng tên, cùng hành vi với chế độ "single"; điểm mới duy nhất là chúng dùng sổ lượt
`budget` của lần gọi chủ đề này (make_*_tool đã nhận budget sẵn nên không phải sửa tools.py).
"""

from __future__ import annotations

from typing import List

from app.agents.research_agent.profiles import SearchProfile
from app.agents.research_agent.tools import SearchBudget, make_arxiv_tool, make_wikipedia_tool


def default_explainer_tools(budget: SearchBudget, profile: SearchProfile) -> List:
    return [make_wikipedia_tool(budget=budget), make_arxiv_tool(budget=budget)]
