"""Registry của các agent con.

ĐÂY LÀ FILE DUY NHẤT phải sửa khi thêm/bớt agent. Mỗi thành viên chỉ thêm đúng
MỘT dòng vào AGENT_SPECS -> merge conflict nếu có cũng chỉ ở một dòng, giải quyết
trong 10 giây. Supervisor và prompt của supervisor đọc registry này, không hard-code
tên agent ở chỗ nào khác.

Mỗi agent là một GÓI (thư mục) tự chứa: agent.py + tools.py + prompts.py.
Tên thư mục PHẢI trùng AGENT_NAME (quy tắc CT-05).

Supervisor cố ý KHÔNG có mặt ở đây: nó điều phối registry này chứ không phải một
phần tử của nó (đưa vào sẽ tạo vòng lặp import).
"""

from __future__ import annotations

from typing import Dict, List

from app.core.contracts import AgentSpec

from .research_agent import (
    AGENT_DESCRIPTION as RESEARCH_DESCRIPTION,
    AGENT_NAME as RESEARCH_NAME,
    build_research_agent,
)
from .vision_agent import (
    AGENT_DESCRIPTION as VISION_DESCRIPTION,
    AGENT_NAME as VISION_NAME,
    build_vision_agent,
)

AGENT_SPECS: List[AgentSpec] = [
    AgentSpec(RESEARCH_NAME, RESEARCH_DESCRIPTION, build_research_agent),
    AgentSpec(VISION_NAME, VISION_DESCRIPTION, build_vision_agent),
    # AgentSpec(CODE_NAME, CODE_DESCRIPTION, build_code_agent),   # <- agent thứ 3 thêm ở đây
]

AGENT_SPECS_BY_NAME: Dict[str, AgentSpec] = {s.name: s for s in AGENT_SPECS}


def build_all_agents(model=None) -> List:
    """Khởi tạo tất cả agent con trong registry."""
    return [spec.builder(model=model) for spec in AGENT_SPECS]


def agent_catalog() -> str:
    """Sinh phần mô tả agent để chèn vào prompt của supervisor."""
    return "\n".join(f"- {s.name}: {s.description}" for s in AGENT_SPECS)


__all__ = [
    "AGENT_SPECS",
    "AGENT_SPECS_BY_NAME",
    "build_all_agents",
    "agent_catalog",
    "build_research_agent",
    "build_vision_agent",
]
