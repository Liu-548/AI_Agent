"""Gói một agent chủ đề thành MỘT tool cho research lead (agents-as-tools).

Nhìn từ lead, agent chủ đề chỉ là một tool nhận `text` (câu con tự đủ nghĩa) và trả
về kết quả. Bên trong tool là cả một ReAct agent con chạy tới khi xong.

Hai luồng dữ liệu tách nhau (quyết định D9, response_format="content_and_artifact"):
- content  : chuỗi JSON GỌN — thứ duy nhất LLM của lead đọc. Nhẹ để không phình
             context, không dính 400 output_parse_failed, không vượt 8K TPM.
- artifact : dict ĐẦY ĐỦ (bằng chứng, vết thực thi) — không gửi cho LLM nhưng nằm
             trong ToolMessage.artifact của state, để grounding tầng 2 và UI đọc.

Tool KHÔNG BAO GIỜ raise: mọi lỗi thành chuỗi "ERROR: <MÃ> | ...".

File này cố tình KHÔNG dùng `from __future__ import annotations`: LangChain đọc
kiểu của tham số (Annotated[..., InjectedState]) từ chữ ký hàm để biết tham số
nào được tiêm, và đọc trực tiếp từ annotation thật thì chắc chắn hơn từ chuỗi.
"""

import json
import logging
import re
import time
from typing import Annotated, Any, Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import InjectedToolCallId, StructuredTool
from langgraph.prebuilt import InjectedState

from app.agents.research_agent.grounding_policy import apply_grounding_policy
from app.agents.research_agent.profiles import SearchProfile
from app.agents.research_agent.tools import SearchBudget
from app.agents.research_agent.topics.budget import check_topic_budget
from app.core.contracts import tool_error
from app.core.grounding import NHAN_RE
from app.core.pretty import message_text

log = logging.getLogger(__name__)

TIEN_TO_KHONG_DU = "KHONG DU DU LIEU:"
_LOI_TOOL_RE = re.compile(r"^ERROR:\s*([A-Z0-9_]+)")
# Chuỗi giống API key: che đi trước khi đưa thông điệp lỗi của provider ra ngoài.
_KEY_RE = re.compile(r"(?:gsk_|sk-|AIza|AQ\.)[A-Za-z0-9_\-\.]{8,}")


def _che_key(text: str) -> str:
    return _KEY_RE.sub("***", text or "")


def dung_vet(messages: List) -> List[Dict[str, Any]]:
    """Vết thực thi của agent chủ đề (SPEC §5.13): tool_call -> tool_result -> final."""
    vet: List[Dict[str, Any]] = []

    def them(**kw):
        vet.append({"step": len(vet) + 1, **kw})

    for m in messages:
        if isinstance(m, AIMessage):
            if m.tool_calls:
                for c in m.tool_calls:
                    dau_vao = json.dumps((c.get("args") or {}), ensure_ascii=False)
                    them(kind="tool_call", tool=c["name"], input=dau_vao[:200])
            else:
                them(kind="final", output_chars=len(message_text(m.content)))
        elif isinstance(m, ToolMessage):
            noi_dung = message_text(m.content)
            khop = _LOI_TOOL_RE.match(noi_dung)
            them(
                kind="tool_result",
                tool=m.name,
                output_chars=len(noi_dung),
                error_code=khop.group(1) if khop else None,
            )
    return vet


def _loi_khong_chay(ten: str, text: str, code: str, message: str, profile: SearchProfile) -> Tuple[str, dict]:
    """Cặp (content, artifact) cho lần gọi bị từ chối / hỏng trước khi có kết quả."""
    content = tool_error(code, message)
    artifact = {
        "topic": ten, "sub_question": text, "profile": profile.name, "status": "error",
        "error": content, "answer_raw": "", "answer_final": "", "evidence_text": "",
        "grounding_report": {"removed": 0, "missing_source": 0, "violations": []},
        "trace": [], "usage": {"llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0},
    }
    log.info("topic=%s status=error code=%s", ten, code)
    return content, artifact


def make_topic_tool(spec, *, profile: SearchProfile, model=None, ten_chu_de=None) -> StructuredTool:
    """Dựng tool cho một TopicSpec.

    ten_chu_de: tên mọi tool chủ đề của lead (để TopicBudget đếm chung); mặc định
    chỉ gồm chính spec này.
    """
    ten_chu_de = set(ten_chu_de or [spec.name])

    def _run(
        text: str,
        state: Annotated[Optional[dict], InjectedState] = None,
        tool_call_id: Annotated[str, InjectedToolCallId] = "",
    ) -> Tuple[str, dict]:
        # 1. Đầu vào rỗng.
        if not text or not text.strip():
            return _loi_khong_chay(spec.name, text or "", "EMPTY_QUERY", "Cần một câu con để giao cho agent chủ đề.", profile)
        text = text.strip()

        # 2. TopicBudget: trần số lần gọi + chặn gọi trùng, đếm từ state của lead.
        tu_choi = check_topic_budget(
            (state or {}).get("messages", []), ten_chu_de, spec.name, text,
            profile.max_topic_calls, tool_call_id,
        )
        if tu_choi is not None:
            ma = _LOI_TOOL_RE.match(tu_choi).group(1)
            return _loi_khong_chay(spec.name, text, ma, tu_choi.split("|", 1)[1].strip(), profile)

        # 3. Mỗi lần gọi có SearchBudget MỚI (trần = max_searches_per_topic của profile).
        try:
            ngan_sach = SearchBudget(max_calls=profile.max_searches_per_topic)
            agent = spec.build(model=model, tools=spec.default_tools(ngan_sach, profile))
        except Exception as exc:  # thiếu key / thiếu MODEL_RESEARCH_TOPIC...
            return _loi_khong_chay(
                spec.name, text, "TOPIC_AGENT_FAILED",
                f"{type(exc).__name__}: {_che_key(str(exc))[:200]}", profile,
            )

        # 4. Chạy agent con.
        bat_dau = time.perf_counter()
        try:
            ket_qua = agent.invoke(
                {"messages": [HumanMessage(content=text)]},
                config={"recursion_limit": profile.inner_recursion_limit},
            )
        except Exception as exc:
            from langgraph.errors import GraphRecursionError

            if isinstance(exc, GraphRecursionError):
                return _loi_khong_chay(spec.name, text, "TOPIC_RECURSION_LIMIT",
                                       f"Agent chủ đề vượt {profile.inner_recursion_limit} bước.", profile)
            ten_loi = type(exc).__name__
            if "ratelimit" in ten_loi.lower() or "429" in str(exc):
                return _loi_khong_chay(spec.name, text, "LLM_RATE_LIMITED",
                                       "role research_topic — run python -m app.main --config", profile)
            return _loi_khong_chay(spec.name, text, "TOPIC_AGENT_FAILED",
                                   f"{ten_loi}: {_che_key(str(exc))[:200]}", profile)
        thoi_gian_ms = int((time.perf_counter() - bat_dau) * 1000)

        # 5. Thu kết quả.
        messages = ket_qua.get("messages", [])
        tra_loi_cuoi = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        answer_raw = message_text(tra_loi_cuoi.content).strip() if tra_loi_cuoi else ""
        evidence_text = "\n".join(message_text(m.content) for m in messages if isinstance(m, ToolMessage))

        # 6. GROUNDING TẦNG 1: xoá câu MA_BIA / NHAN_BIA ngay trong agent chủ đề.
        if not answer_raw:
            answer_raw = f"{TIEN_TO_KHONG_DU} topic agent returned no answer"
        answer_final, bao_cao = apply_grounding_policy(answer_raw, evidence_text)
        status = "no_data" if answer_final.strip().startswith(TIEN_TO_KHONG_DU) else "ok"
        nhan = list(dict.fromkeys(m.group(0) for m in NHAN_RE.finditer(answer_final)))

        usage = {
            "llm_calls": sum(isinstance(m, AIMessage) for m in messages),
            "tool_calls": sum(isinstance(m, ToolMessage) for m in messages),
            "elapsed_ms": thoi_gian_ms,
        }
        log.info(
            "topic=%s status=%s llm_calls=%d tool_calls=%d elapsed_ms=%d grounding_removed=%d",
            spec.name, status, usage["llm_calls"], usage["tool_calls"], thoi_gian_ms, bao_cao["removed"],
        )

        # 7. content (gọn, cho LLM của lead) + artifact (đầy đủ, ở lại trong state).
        content = json.dumps(
            {
                "topic": spec.name, "status": status, "sub_question": text,
                "answer": answer_final, "labels": nhan,
                "grounding": {"removed": bao_cao["removed"], "missing_source": bao_cao["missing_source"]},
            },
            ensure_ascii=False,
        )
        artifact = {
            "topic": spec.name, "sub_question": text, "profile": profile.name, "status": status,
            "answer_raw": answer_raw, "answer_final": answer_final, "evidence_text": evidence_text,
            "grounding_report": bao_cao, "trace": dung_vet(messages), "usage": usage,
        }
        return content, artifact

    return StructuredTool.from_function(
        func=_run,
        name=spec.name,
        description=spec.description,
        return_direct=False,
        response_format="content_and_artifact",
    )
