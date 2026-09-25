"""Research lead — ReAct agent điều phối các agent chủ đề (chế độ RESEARCH_ARCH=topics).

Nhìn từ supervisor, nó VẪN là node `research_agent` như cũ (cùng tên, cùng factory).
Bên trong, các "tool" của lead là các agent chủ đề (scholar_agent, explainer_agent...).

Grounding chạy HAI TẦNG:
- Tầng 1 ở topic_tool: xoá câu bịa ngay trong từng agent chủ đề.
- Tầng 2 ở đây (post_model_hook): lead tổng hợp có thể làm rơi hoặc bịa nhãn, nên
  câu trả lời CUỐI của lead lại được đối chiếu với bằng chứng nằm trong
  ToolMessage.artifact của các agent chủ đề.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.research_agent.agent import AGENT_NAME
from app.agents.research_agent.grounding_policy import DONG_DAC_BIET, apply_grounding_policy
from app.agents.research_agent.profiles import SearchProfile, get_profile
from app.agents.research_agent.prompts import RESEARCH_LEAD_PROMPT_TEMPLATE
from app.agents.research_agent.topics import TOPIC_SPECS, build_topic_tools
from app.core.pretty import message_text

log = logging.getLogger(__name__)

GHI_CHU_DA_LUOC_BO = "(Đã lược bỏ {n} câu có nguồn không xác minh được.)"
GHI_CHU_KHONG_NGUON = "(Câu trả lời này không dựa trên nguồn đã tra cứu.)"


def render_lead_prompt(specs, profile: SearchProfile) -> str:
    """Điền danh sách chủ đề (sinh từ registry) và trần số lần gọi vào template."""
    danh_sach = "\n".join(f"- {s.name}: {s.description}" for s in specs)
    return RESEARCH_LEAD_PROMPT_TEMPLATE.format(
        topic_list=danh_sach, max_topic_calls=profile.max_topic_calls
    )


def bang_chung_cua_luot_hien_tai(messages: List) -> Optional[str]:
    """Nối evidence_text của mọi ToolMessage agent chủ đề nằm SAU HumanMessage cuối.

    None = lượt này lead chưa gọi agent chủ đề nào.
    """
    sau_cuoi: List = []
    for m in messages:
        if isinstance(m, HumanMessage):
            sau_cuoi = []
        else:
            sau_cuoi.append(m)
    phan = [
        m.artifact["evidence_text"]
        for m in sau_cuoi
        if isinstance(m, ToolMessage)
        and isinstance(m.artifact, dict)
        and m.artifact.get("evidence_text") is not None
    ]
    return "\n".join(phan) if phan else None


def grounding_hook(state: dict) -> dict:
    """GROUNDING TẦNG 2 — chạy sau mỗi lượt gọi model của lead.

    Chỉ xử lý câu trả lời CUỐI (AIMessage không còn tool_calls). Câu có nguồn bịa bị
    xoá; AIMessage được thay bằng bản sạch, GIỮ NGUYÊN id nên reducer add_messages
    thay thế chứ không nối thêm. Báo cáo ghi vào response_metadata["grounding"]
    (không ghi additional_kwargs, vì trường đó có thể bị gửi ngược cho provider).
    """
    cuoi = state["messages"][-1]
    if not isinstance(cuoi, AIMessage) or cuoi.tool_calls:
        return {}
    tra_loi = message_text(cuoi.content)
    if not tra_loi.strip():
        return {}

    bang_chung = bang_chung_cua_luot_hien_tai(state["messages"])
    sach, bao_cao = apply_grounding_policy(tra_loi, bang_chung or "")

    ghi_chu = []
    if not sach.strip().startswith(DONG_DAC_BIET):
        if bao_cao["removed"]:
            ghi_chu.append(GHI_CHU_DA_LUOC_BO.format(n=bao_cao["removed"]))
        if bang_chung is None:
            ghi_chu.append(GHI_CHU_KHONG_NGUON)
    if ghi_chu:
        sach = sach.rstrip() + "\n" + "\n".join(ghi_chu)

    log.info(
        "lead grounding: removed=%d missing_source=%d co_bang_chung=%s",
        bao_cao["removed"], bao_cao["missing_source"], bang_chung is not None,
    )
    moi = cuoi.model_copy(update={
        "content": sach,
        "response_metadata": {**(cuoi.response_metadata or {}), "grounding": bao_cao},
    })
    return {"messages": [moi]}


def build_research_lead(model=None, tools: Optional[List] = None, prompt: Optional[str] = None,
                        profile: Optional[SearchProfile] = None):
    """Dựng research lead. Cùng chữ ký DI (model/tools/prompt) như mọi factory của dự án.

    model=None  -> LLM của vai trò "research" (giữ nguyên vai trò cũ, D8).
    tools=None  -> mỗi agent chủ đề trong TOPIC_SPECS thành một tool (chúng tự lấy
                   LLM của vai trò "research_topic").
    """
    from langgraph.prebuilt import create_react_agent

    profile = profile or get_profile()
    if model is None:
        from app.core.llm import get_llm

        model = get_llm("research")
    if tools is None:
        tools = build_topic_tools(profile)
    if prompt is None:
        prompt = render_lead_prompt(TOPIC_SPECS, profile)

    return create_react_agent(
        model=model,
        tools=tools,
        prompt=prompt,
        name=AGENT_NAME,  # "research_agent" (IF-02): supervisor không thấy khác biệt
        post_model_hook=grounding_hook,
    )
