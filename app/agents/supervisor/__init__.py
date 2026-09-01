"""Gói Supervisor — TOÀN BỘ code điều phối nằm trong thư mục này.

    agent.py    build_supervisor()
    prompts.py  SUPERVISOR_PROMPT_TEMPLATE

Chủ sở hữu: người phụ trách Supervisor Agent.
"""

from app.agents.supervisor.agent import SUPERVISOR_NAME, build_supervisor
from app.agents.supervisor.prompts import SUPERVISOR_PROMPT_TEMPLATE

__all__ = ["SUPERVISOR_NAME", "build_supervisor", "SUPERVISOR_PROMPT_TEMPLATE"]
