"""culture_agent — chủ đề "sách, văn chương, âm nhạc" (Phase 5 trong SPEC §13).

Tên thư mục = TOPIC_NAME = tên tool = name= của create_react_agent (giống CT-05).

Quy tắc cứng của chủ đề này: KHÔNG chép lời bài hát hay đoạn văn có bản quyền. Đặt ở
hai lớp như grounding: prompt dặn, và gioi_han_trich_dan() cắt bằng code mọi trích dẫn
nguyên văn dài — vì nhắc trong prompt thì model vẫn có lúc lờ đi (TRUOC_KHI_CHAY Phần 7).
"""

from __future__ import annotations

import re
from typing import List, Optional

from app.agents.research_agent.topics.culture_agent.prompts import CULTURE_AGENT_PROMPT

TOPIC_NAME = "culture_agent"
TOPIC_DESCRIPTION = (
    "Use for BOOKS, LITERATURE and MUSIC: authors, novels, poems, songs, albums, artists, "
    "who wrote or performed something, when it was published or released, what a work is "
    "about. Returns a short cited answer from Open Library, MusicBrainz and Wikipedia. Never "
    "returns lyrics or long passages. Do NOT use for celebrity news (news_agent)."
)

# Trích nguyên văn tối đa (số từ) — tác phẩm công cộng cũng chỉ được trích ngắn (SPEC §13).
MAX_TU_TRICH = 12
_TRICH_RE = re.compile(r"[\"“]([^\"“”\n]+)[\"”]")


def gioi_han_trich_dan(answer: str) -> str:
    """Thay mọi đoạn trong ngoặc kép dài hơn MAX_TU_TRICH từ bằng "[long quote removed]".

    shortcut: chỉ bắt trích dẫn CÓ ngoặc kép; lời bài hát chép trần không ngoặc thì vẫn
    dựa vào prompt + grounding (câu không có nhãn nguồn). Muốn chặt hơn thì so n-gram
    với một kho lời bài hát — không làm vì không có kho hợp pháp miễn phí.
    """
    return _TRICH_RE.sub(
        lambda m: m.group(0) if len(m.group(1).split()) <= MAX_TU_TRICH else "[long quote removed]",
        answer or "",
    )


def build_culture_agent(model=None, tools: Optional[List] = None, prompt: Optional[str] = None):
    """model=None -> LLM vai trò "research_topic"; tools=None -> book_search + music_search + wikipedia."""
    from langgraph.prebuilt import create_react_agent

    if model is None:
        from app.core.llm import get_llm

        model = get_llm("research_topic")
    if tools is None:
        from app.agents.research_agent.profiles import get_profile
        from app.agents.research_agent.tools import SearchBudget
        from app.agents.research_agent.topics.culture_agent.tools import default_culture_tools

        profile = get_profile()
        tools = default_culture_tools(SearchBudget(max_calls=profile.max_searches_per_topic), profile)

    return create_react_agent(model=model, tools=tools, prompt=prompt or CULTURE_AGENT_PROMPT, name=TOPIC_NAME)
