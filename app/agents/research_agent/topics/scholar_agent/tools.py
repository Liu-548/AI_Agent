"""Tool lá của scholar_agent: paper_search, pubmed_search, doi_lookup."""

from __future__ import annotations

from typing import List

from app.agents.research_agent.paper_tools import make_paper_tools
from app.agents.research_agent.profiles import SearchProfile
from app.agents.research_agent.tools import SearchBudget


def default_scholar_tools(budget: SearchBudget, profile: SearchProfile) -> List:
    """Ba tool dùng chung sổ lượt `budget` và giới hạn của `profile`."""
    return make_paper_tools(budget, profile)
