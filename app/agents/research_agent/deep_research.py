"""Tìm kiếm chuyên sâu (deep research): một câu hỏi -> một file báo cáo .md có trích dẫn.

Khác research lead (vòng ReAct: LLM tự quyết gọi agent nào, bao nhiêu lần), ở đây THỨ
TỰ BƯỚC DO CODE QUYẾT ĐỊNH bằng StateGraph. Các agent chủ đề (news, scholar, economy...)
vẫn là người đi tìm, deep research chỉ là người điều phối có kỷ luật:

    plan -> research --(có câu hỏi con thiếu dữ liệu, còn vòng)--> refine -> research
                     \\---(đủ / hết vòng)----------------------------------> write

- plan    : 1 lượt LLM tách câu hỏi thành tối đa N câu hỏi con tiếng Anh, MỖI câu gắn
            với một agent chủ đề ("news_agent | ..."). Mỗi Ý của câu hỏi gốc có ít nhất
            một câu hỏi con, nên câu dài nhiều ý không bị gộp làm một.
- research: KHÔNG gọi LLM trực tiếp. Mỗi câu hỏi con -> tool của agent chủ đề tương ứng
            (make_topic_tool: agent con tự tìm, grounding tầng 1 đã chạy bên trong).
- refine  : 1 lượt LLM cho MỌI câu hỏi con không có dữ liệu: đổi cách hỏi hoặc đổi
            agent (vd. scholar -> news). Trần số vòng nằm trong code, không trong prompt.
- write   : 1 lượt LLM viết báo cáo, trích bằng NHÃN nguồn như agent con; grounding_policy
            xoá câu có nhãn bịa, rồi so_hoa_trich_dan() đổi nhãn thành [1] [2] + NGUỒN
            bằng code (LLM tự đánh số hay lệch).

Vì sao đổi (11/2026): bản cũ chỉ tìm paper_search + wikipedia, nên câu hỏi tin tức
("bê bối của CEO Nvidia") chỉ vớ được một trang Wikipedia lệch đề -> báo cáo hụt.

Ghi file .md là việc của Python (render_markdown), không phải tool của LLM.
N và số vòng tìm bù lấy từ SearchProfile (eco/standard/full).

Chạy thử:  python -m app.agents.research_agent.deep_research "rotary positional encoding" --mode eco
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TypedDict

from app.agents.research_agent.grounding_policy import apply_grounding_policy
from app.agents.research_agent.profiles import SearchProfile, get_profile
from app.core.grounding import NHAN_RE, TIEU_DE_NGUON_RE, bao_cao, kiem_tra_grounding, tach_danh_sach_nguon
from app.core.pretty import message_text

# runs/ đã nằm trong .gitignore nên báo cáo sinh ra không lẫn vào git.
THU_MUC_BAO_CAO = Path(__file__).resolve().parents[3] / "runs" / "research"
KHONG_DU = "KHONG DU DU LIEU"
CHO_HAN_MUC_GIAY = 20  # chờ trước khi thử lại một agent bị LLM_RATE_LIMITED (test đặt 0)
# Dòng kế hoạch: "news_agent | Who is ...?" ; dòng tìm bù: "2 | news_agent | ...".
DONG_KE_HOACH_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])?\s*([a-z_]+_agent)\s*\|\s*(.+)$")
DONG_TIM_BU_RE = re.compile(r"^\s*(\d+)\s*\|\s*([a-z_]+_agent)\s*\|\s*(.+)$")
MA_TIN_RE = re.compile(r"gn-[0-9a-f]{8}")

PLAN_PROMPT = """You plan a research report. Today is {today}.
Split the user's question into at most {n} self-contained ENGLISH sub-questions and give each
one to the ONE specialist agent best suited to answer it.

AGENTS:
{topic_list}

RULES:
- FIRST give every separate part of the question its own sub-question: "the scandal of X"
  and "who is the new CEO of Y" are two parts -> two sub-questions, even if the same agent
  answers both.
- THEN use the remaining slots (this is an IN-DEPTH report: aim for {n} sub-questions) to go
  deeper into the parts the user asked about: timeline and key dates, official statements
  and responses, reactions (market, regulators, public), consequences and what happens next.
- ORDER: the one-per-part sub-questions come FIRST, in the order of the question; the
  deeper sub-questions come after them.
- Never add sub-questions about things the user did not ask about.
- Each sub-question names the people, organisations, places and years from the question,
  so it is understandable on its own, and is short enough to be a search query.
- Events, people or companies in the news, scandals, appointments, anything recent ->
  news_agent. Research papers and scientific evidence -> scholar_agent.

Output ONLY lines of this exact form, nothing else:
<agent name> | <sub-question>

QUESTION: {question}"""

REFINE_PROMPT = """These sub-questions of a research plan found NO data. For each one, propose ONE new
attempt: a simpler wording (key names + key words, like a headline) and/or a better agent.

AGENTS:
{topic_list}

FAILED (number | agent | sub-question):
{failed}

Output ONLY lines of this exact form, nothing else (skip a number if nothing else can work):
<number> | <agent name> | <new sub-question>"""

WRITE_PROMPT = """You write an in-depth research report. LANGUAGE: write EVERYTHING -- headings, summary
and every bullet -- in the language of QUESTION (Vietnamese WITH full diacritics if the
question is Vietnamese, even if typed without them). The notes are in English: TRANSLATE
them; never leave an English sentence in a Vietnamese report. Use ONLY the notes below;
every fact must come from them.

QUESTION: {question}

NOTES (one block per sub-question, written by specialist agents; each fact ends with its
source label in square brackets):
{notes}

OUTPUT FORMAT -- markdown, exactly these parts, in this order, nothing before or after:

## Tóm tắt
<3 to 6 sentences answering EVERY part of the question directly. For each part the notes do
not cover, write one sentence saying so, without a label.>

## 1. <short title for the first sub-question, AT MOST 6 words, in the report language>
<3 to 8 bullets starting with "- ": concrete facts -- who, what, when (dates), where, which
outlet or paper says so, numbers.>

(one numbered section per sub-question block)

CITATIONS -- the program turns your labels into numbers [1] [2] and builds the source list:
- END EVERY SENTENCE AND EVERY BULLET with the label(s) of the note fact(s) it uses, copied
  character by character in square brackets, INCLUDING the prefix: [news: gn-1a2b3c4d],
  [http://arxiv.org/abs/2104.09864v5], [wikipedia: Page name], [worldbank: VNM/FP.CPI.TOTL.ZG].
- Use the label of the note that actually states that fact; never move a label to a fact
  it does not support. A sentence you cannot attach a label to must be DELETED -- except a
  sentence saying that a part of the question is NOT covered: that one gets NO label.
- Do NOT write numbers like [1], do NOT write a source list, never put a URL in the text.
- NEVER create, shorten, fix or guess a label.

CONTENT RULES:
- Report what the SOURCES say and attribute it ("Reuters reports...", "according to ...").
  Allegations stay allegations; never turn a claim into a confirmed fact.
- If the notes are about a DIFFERENT event or person than the one asked about (e.g. a spying
  case when the user asked about an affair), say so explicitly instead of presenting it as the
  asked event.
- Keep technical terms, paper titles, outlet names and person names as written in the notes.
- No greeting, no closing remark, no explanation of how you worked."""


def so_hoa_trich_dan(bai: str) -> str:
    """Nhãn nguồn trong bài -> số [1] [2] theo thứ tự xuất hiện + dòng NGUỒN cuối bài.

    Làm bằng code chứ không bắt LLM tự đánh số: LLM hay đánh lệch (Tóm tắt dùng [5] cho
    một nguồn, mục bên dưới lại dùng [5] cho nguồn khác). Mã tin trần "gn-xxxxxxxx" được
    thêm lại tiền tố "news: " để UI đổi thành link bài báo.
    """
    than = bai.splitlines()
    cat_o = next((i for i, d in enumerate(than) if TIEU_DE_NGUON_RE.match(d)), None)
    than = "\n".join(than[:cat_o] if cat_o is not None else than).rstrip()
    so: Dict[str, int] = {}

    def doi(m: "re.Match") -> str:
        nhan = m.group(1).strip()
        if nhan.isdigit():
            return m.group(0)
        if MA_TIN_RE.fullmatch(nhan):
            nhan = "news: " + nhan
        so.setdefault(nhan, len(so) + 1)
        return f"[{so[nhan]}]"

    than = NHAN_RE.sub(doi, than)
    if not so:
        return than
    return than + "\n\nNGUỒN\n" + "\n".join(f"[{n}] {nhan}" for nhan, n in so.items())


class DeepState(TypedDict, total=False):
    question: str
    sub_questions: List[str]
    topics: Dict[int, str]     # câu hỏi con -> agent chủ đề (lần thử gần nhất)
    queries: Dict[int, str]    # câu hỏi con cần tra ở lượt research tới -> câu giao cho agent
    evidence: Dict[int, str]   # bằng chứng thô (kết quả tool lá) tích luỹ của từng câu hỏi con
    notes: Dict[int, str]      # câu trả lời đã grounding của agent; "" = không đủ dữ liệu
    trace: List[dict]          # mỗi lần gọi agent một dòng (cho UI và file .md)
    rounds_left: int
    report: str
    grounding: dict


def default_deep_tools(profile: SearchProfile, model=None) -> list:
    """Mỗi agent chủ đề thành một tool. Mỗi lần gọi có SearchBudget riêng (topic_tool lo)."""
    from app.agents.research_agent.topics import TOPIC_SPECS, make_topic_tool

    return [make_topic_tool(s, profile=profile, model=model) for s in TOPIC_SPECS]


def danh_sach_chu_de(tools: list) -> str:
    """Dòng mô tả agent cho prompt: lấy từ chính tool (description = TopicSpec.description)."""
    return "\n".join(f"- {t.name}: {getattr(t, 'description', '')}" for t in tools)


def tach_ke_hoach(text: str, ten_hop_le: List[str], mac_dinh: str, n: int) -> List[Tuple[str, str]]:
    """Output của PLAN_PROMPT -> [(agent, câu hỏi con)]. Tên agent lạ / thiếu "|" -> mac_dinh."""
    ke_hoach = []
    for dong in text.splitlines():
        dong = dong.strip()
        if not dong:
            continue
        m = DONG_KE_HOACH_RE.match(dong)
        if m:
            ten, cau = m.group(1), m.group(2).strip()
            ke_hoach.append((ten if ten in ten_hop_le else mac_dinh, cau))
        else:
            ke_hoach.append((mac_dinh, re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", dong)))
    return [(t, c) for t, c in ke_hoach if c][:n]


def goi_chu_de(tool, cau_hoi: str) -> dict:
    """Gọi tool agent chủ đề như lead gọi -> {status, answer, evidence, usage, removed, error}."""
    msg = tool.invoke({"name": tool.name, "args": {"text": cau_hoi}, "id": "deep", "type": "tool_call"})
    noi_dung = message_text(getattr(msg, "content", msg))
    artifact = getattr(msg, "artifact", None) or {}
    try:
        data = json.loads(noi_dung)
    except (TypeError, ValueError):  # "ERROR: CODE | ..." từ _loi_khong_chay
        return {"status": "error", "answer": "", "evidence": "", "error": noi_dung,
                "usage": artifact.get("usage", {}), "removed": 0}
    return {
        "status": data.get("status", "error"),
        "answer": data.get("answer", "") if data.get("status") == "ok" else "",
        "evidence": artifact.get("evidence_text", ""),
        "usage": artifact.get("usage", {}),
        "removed": (data.get("grounding") or {}).get("removed", 0),
        "error": "",
    }


def build_deep_research(model=None, tools: Optional[list] = None, profile: Optional[SearchProfile] = None):
    """Dựng graph. DI như mọi factory: model=None -> get_llm, tools=None -> tool của mọi agent chủ đề.

    plan/refine dùng vai trò "research"; write dùng "research_topic" (chép nhãn nguồn và
    giữ luật trích dẫn cần model tuân lệnh tốt). Agent chủ đề tự lấy LLM của chúng.
    """
    from langgraph.graph import END, START, StateGraph

    profile = profile or get_profile()
    if model is None:
        from app.core.llm import get_llm

        planner = get_llm("research")
        writer = get_llm("research_topic")
    else:
        planner = writer = model
    tools = default_deep_tools(profile) if tools is None else tools
    theo_ten = {t.name: t for t in tools}
    mo_ta = danh_sach_chu_de(tools)
    mac_dinh = "news_agent" if "news_agent" in theo_ten else tools[0].name

    def hoi(llm, prompt: str) -> str:
        return message_text(llm.invoke(prompt).content).strip()

    def plan(state: DeepState) -> dict:
        out = hoi(planner, PLAN_PROMPT.format(
            today=f"{datetime.now():%Y-%m-%d}", n=profile.deep_sub_questions,
            topic_list=mo_ta, question=state["question"],
        ))
        ke_hoach = tach_ke_hoach(out, list(theo_ten), mac_dinh, profile.deep_sub_questions) \
            or [(mac_dinh, state["question"])]
        return {"sub_questions": [c for _, c in ke_hoach], "topics": {i: t for i, (t, _) in enumerate(ke_hoach)},
                "queries": {i: c for i, (_, c) in enumerate(ke_hoach)}, "evidence": {}, "notes": {},
                "trace": [], "rounds_left": profile.deep_refine_rounds}

    def research(state: DeepState) -> dict:
        evidence, notes, trace = dict(state["evidence"]), dict(state["notes"]), list(state["trace"])
        rounds_left = state["rounds_left"]
        for i, cau in state["queries"].items():
            ten = state["topics"][i]
            kq = goi_chu_de(theo_ten[ten], cau)
            if "LLM_RATE_LIMITED" in kq["error"]:
                # Groq tính hạn mức theo PHÚT: các agent chạy liền nhau dễ chạm trần -> chờ, thử lại 1 lần.
                time.sleep(CHO_HAN_MUC_GIAY)
                kq = goi_chu_de(theo_ten[ten], cau)
            evidence[i] = "\n\n".join(p for p in (evidence.get(i, ""), kq["evidence"]) if p)
            notes[i] = kq["answer"]
            trace.append({"topic": ten, "status": kq["status"], "sub_question": cau,
                          "usage": kq["usage"], "removed": kq["removed"],
                          **({"error": kq["error"][:200]} if kq["error"] else {})})
            if "LLM_RATE_LIMITED" in kq["error"]:
                rounds_left = 0  # vẫn hết hạn mức: không gọi thêm, viết từ những gì đã có
                break
        return {"evidence": evidence, "notes": notes, "trace": trace, "queries": {}, "rounds_left": rounds_left}

    def can_tim_bu(state: DeepState) -> str:
        thieu = [i for i in range(len(state["sub_questions"])) if not state["notes"].get(i)]
        return "refine" if thieu and state["rounds_left"] > 0 else "write"

    def refine(state: DeepState) -> dict:
        thieu = [i for i in range(len(state["sub_questions"])) if not state["notes"].get(i)]
        out = hoi(planner, REFINE_PROMPT.format(
            topic_list=mo_ta,
            failed="\n".join(f"{i + 1} | {state['topics'][i]} | {state['sub_questions'][i]}" for i in thieu),
        ))
        topics, queries = dict(state["topics"]), {}
        for dong in out.splitlines():
            m = DONG_TIM_BU_RE.match(dong)
            if not m:
                continue
            i, ten, cau = int(m.group(1)) - 1, m.group(2), m.group(3).strip()
            if i in thieu and ten in theo_ten and cau:
                topics[i], queries[i] = ten, cau
        return {"topics": topics, "queries": queries, "rounds_left": state["rounds_left"] - 1}

    def write(state: DeepState) -> dict:
        co = [i for i in range(len(state["sub_questions"])) if state["notes"].get(i)]
        if not co:
            return {"report": f"{KHONG_DU}: không tìm được nguồn nào trả lời được câu hỏi.",
                    "grounding": {"removed": 0, "missing_source": 0, "violations": []}}
        khoi = "\n\n".join(f"Sub-question {n} ({state['topics'][i]}): {state['sub_questions'][i]}\n{state['notes'][i]}"
                           for n, i in enumerate(co, 1))
        bai = hoi(writer, WRITE_PROMPT.format(question=state["question"], notes=khoi))
        bai = re.sub(r"【([^【】\n]{1,300})】", r"[\1]", bai)  # gpt-oss hay viết 【...】 thay vì [...]
        bai = re.sub(r"\[(gn-[0-9a-f]{8})\]", r"[news: \1]", bai)  # mã tin trần -> nhãn đủ
        # Grounding chấm từng câu TRƯỚC khi đánh số (câu có nhãn bịa bị xoá), rồi mới đánh số.
        sach, bc = apply_grounding_policy(bai, "\n\n".join(state["evidence"].values()))
        return {"report": so_hoa_trich_dan(sach), "grounding": bc}

    g = StateGraph(DeepState)
    for ten, fn in (("plan", plan), ("research", research), ("refine", refine), ("write", write)):
        g.add_node(ten, fn)
    g.add_edge(START, "plan")
    g.add_edge("plan", "research")
    g.add_conditional_edges("research", can_tim_bu, ["refine", "write"])
    g.add_conditional_edges("refine", lambda s: "research" if s["queries"] else "write", ["research", "write"])
    g.add_edge("write", END)
    return g.compile()


def render_markdown(state: DeepState, mode: str, ngay: Optional[datetime] = None) -> str:
    """State -> nội dung file .md. Thuần Python, không gọi LLM."""
    ngay = ngay or datetime.now()
    bc = state.get("grounding") or {}
    than = state.get("report", "")
    con_lai = kiem_tra_grounding(than, ["\n\n".join(state.get("evidence", {}).values())])
    than_md = "\n".join("## Tài liệu tham khảo" if TIEU_DE_NGUON_RE.match(d) else d for d in than.splitlines())
    topics = state.get("topics") or {}
    da_tra = [f"{n}. `{topics.get(i, '?')}` {q}" + ("" if state["notes"].get(i) else " — *không đủ dữ liệu*")
              for n, (i, q) in enumerate(enumerate(state["sub_questions"]), 1)]
    kiem_tra = [bao_cao(con_lai)]
    if bc.get("removed"):
        kiem_tra.append(f"\nĐã lược bỏ {bc['removed']} câu có nguồn không xác minh được:")
        kiem_tra += [f"  - {v['code']}: {v['sentence'][:110]}" for v in bc.get("violations", [])]
    return "\n".join([
        "---",
        f"query: {json.dumps(state['question'], ensure_ascii=False)}",
        f"date: {ngay:%Y-%m-%d %H:%M}",
        f"mode: {mode}",
        f"sources: {len(tach_danh_sach_nguon(than)[1])}",
        f"grounding: removed={bc.get('removed', 0)} missing_source={bc.get('missing_source', 0)}",
        "---", "",
        f"# {state['question']}", "",
        than_md, "",
        "## Câu hỏi con đã tra", *da_tra, "",
        "## Kiểm tra nguồn", "```", *kiem_tra, "```", "",
    ])


def _slug(text: str) -> str:
    s = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "research"


def run_deep_research(question: str, mode: Optional[str] = None, model=None,
                      tools: Optional[list] = None, out_dir: Optional[Path] = None) -> dict:
    """Chạy cả quy trình, ghi file .md, trả {markdown, path, filename, report, sub_questions,
    grounding, trace, evidence}. `evidence` (bằng chứng thô) để API dựng link_map cho tin tức."""
    profile = get_profile(mode)
    state = build_deep_research(model=model, tools=tools, profile=profile).invoke({"question": question})
    md = render_markdown(state, profile.name)
    thu_muc = Path(out_dir or THU_MUC_BAO_CAO)
    thu_muc.mkdir(parents=True, exist_ok=True)
    path = thu_muc / f"research_{datetime.now():%Y%m%d_%H%M%S}_{_slug(question)}.md"
    path.write_text(md, encoding="utf-8")
    return {"markdown": md, "path": str(path), "filename": path.name, "report": state["report"],
            "sub_questions": state["sub_questions"], "grounding": state.get("grounding", {}),
            "mode": profile.name, "trace": state.get("trace", []),
            "evidence": "\n\n".join(state.get("evidence", {}).values())}


if __name__ == "__main__":
    import argparse
    import sys

    from app.core.config import RESEARCH_MODES

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252
    ap = argparse.ArgumentParser(description="Tìm kiếm chuyên sâu -> file báo cáo .md")
    ap.add_argument("question")
    ap.add_argument("--mode", choices=RESEARCH_MODES, help="mặc định theo RESEARCH_MODE trong .env")
    a = ap.parse_args()
    kq = run_deep_research(a.question, a.mode)
    print(kq["markdown"])
    print(f"Đã ghi: {kq['path']}")
