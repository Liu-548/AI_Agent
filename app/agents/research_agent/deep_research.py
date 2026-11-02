"""Tìm kiếm chuyên sâu (deep research): một câu hỏi -> một file báo cáo .md có trích dẫn.

Khác research agent thường (vòng ReAct: LLM tự quyết gọi tool gì, bao nhiêu lần), ở
đây THỨ TỰ BƯỚC DO CODE QUYẾT ĐỊNH bằng StateGraph của LangGraph. LLM chỉ làm từng
việc nhỏ trong mỗi bước, nên không lặp truy vấn và hội thoại không phình ra:

    plan -> search -> notes --(thiếu dữ liệu, còn vòng)--> search
                        \\----(đủ / hết vòng)-----------> write

- plan   : 1 lượt LLM tách câu hỏi thành tối đa N câu hỏi con tiếng Anh.
- search : KHÔNG gọi LLM. Mỗi câu hỏi con -> paper_search (arXiv/OpenAlex/S2, đã khử
           trùng) + wikipedia_search, chung một SearchBudget nên truy vấn trùng bị chặn.
- notes  : 1 lượt LLM cho mỗi câu hỏi con: ghi chú có nhãn nguồn, hoặc "TIM_THEM: <từ khoá>"
           để tìm bù (trần số vòng nằm trong code, không nằm trong prompt).
- write  : 1 lượt LLM viết báo cáo, rồi grounding_policy xoá câu có nguồn bịa.

Ghi file .md là việc của Python (render_markdown), không phải tool của LLM: nội dung đã
nằm trong state, chỉ còn định dạng, và nhờ vậy test offline được bằng model giả.
N và số vòng tìm bù lấy từ SearchProfile (eco/standard/full).

Chạy thử:  python -m app.agents.research_agent.deep_research "rotary positional encoding" --mode eco
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, TypedDict

from app.agents.research_agent.grounding_policy import apply_grounding_policy
from app.agents.research_agent.profiles import SearchProfile, get_profile
from app.core.grounding import TIEU_DE_NGUON_RE, bao_cao, kiem_tra_grounding, tach_danh_sach_nguon
from app.core.pretty import message_text

# runs/ đã nằm trong .gitignore nên báo cáo sinh ra không lẫn vào git.
THU_MUC_BAO_CAO = Path(__file__).resolve().parents[3] / "runs" / "research"
TIM_THEM_RE = re.compile(r"^\s*TIM_THEM\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
KHONG_DU = "KHONG DU DU LIEU"

PLAN_PROMPT = """Split the research question below into at most {n} self-contained ENGLISH
sub-questions that together cover it (e.g. definition/background, methods, results or
comparisons, limitations). Each must be understandable without the original question.
Output ONLY the sub-questions, one per line, no numbering, nothing else.

QUESTION: {question}"""

NOTES_PROMPT = """You take research notes for ONE sub-question, using ONLY the search results below.

SUB-QUESTION: {sub_question}

SEARCH RESULTS:
{evidence}

Write 2 to 6 bullets. Each bullet starts with "- ", states ONE fact from the results and ends
with the label of its source in square brackets, copied character by character from a
"Label:" line (e.g. [http://arxiv.org/abs/2104.09864v5] or [doi: 10.1234/abc]); for a
Wikipedia result use [wikipedia: <the Page name>]. Never write a fact or a label that is not
in the results.
{fallback}"""

FALLBACK_TIM_THEM = """If the results are off-topic or too thin to answer the sub-question, write instead ONE
line and nothing else:
TIM_THEM: <a better 2-6 word English keyword query>"""

FALLBACK_HET_VONG = f"""If the results cannot answer the sub-question at all, write exactly one line and nothing else:
{KHONG_DU}"""

WRITE_PROMPT = """You write a research report in the language of the user's question (Vietnamese WITH
full diacritics if the question is Vietnamese, even if typed without them). Use ONLY the
notes below; every fact must come from them.

QUESTION: {question}

NOTES (one block per sub-question; each fact ends with its source label in brackets):
{notes}

OUTPUT FORMAT -- markdown, exactly these parts, in this order, nothing before or after:

## Tóm tắt
<3 to 5 sentences answering the question directly, each ending with a citation number like [1].
If some part of the question is not covered by the notes, say so in one sentence without a number.>

## 1. <short title for the first sub-question, AT MOST 5 words>
<2 to 6 bullets starting with "- "; every bullet is one sentence ending with a citation number.>

(one numbered section per sub-question block)

NGUỒN
[1] <one label copied exactly from the notes, WITHOUT its square brackets>
[2] ...

RULES:
- EVERY sentence ends with its OWN citation number; one number at the end of a paragraph is
  not enough. A sentence you cannot attach a citation number to must be DELETED, not softened.
- In the text cite ONLY with numbers [1] [2]; never put a URL or a label in the text.
- Number sources in order of first use. Every number used has its own NGUỒN line; list only
  cited sources.
- Copy labels exactly. NEVER create, shorten, fix or guess a label.
- Keep technical terms, paper titles and author names in English.
- No greeting, no closing remark, no explanation of how you worked.
- LANGUAGE: the notes are in English, but the report must be in the language of QUESTION
  (Vietnamese with full diacritics for a Vietnamese question). Translate, do not copy."""


class DeepState(TypedDict, total=False):
    question: str
    sub_questions: List[str]
    queries: Dict[int, str]    # câu hỏi con cần tìm ở lượt search tới -> truy vấn
    evidence: Dict[int, str]   # kết quả tool tích luỹ của từng câu hỏi con
    notes: Dict[int, str]      # "" = không đủ dữ liệu
    rounds_left: int
    report: str
    grounding: dict


def default_deep_tools(profile: SearchProfile) -> list:
    """paper_search + wikipedia_search dùng chung MỘT sổ lượt, trần theo profile."""
    from app.agents.research_agent.paper_tools import make_paper_tools
    from app.agents.research_agent.tools import SearchBudget, make_wikipedia_tool

    budget = SearchBudget(max_calls=profile.deep_sub_questions * 2 * (profile.deep_refine_rounds + 1))
    return [make_paper_tools(budget, profile)[0], make_wikipedia_tool(budget=budget)]


def build_deep_research(model=None, tools: Optional[list] = None, profile: Optional[SearchProfile] = None):
    """Dựng graph. DI như mọi factory: model=None -> get_llm, tools=None -> tool thật.

    plan dùng vai trò "research"; notes/write dùng "research_topic" (thường là model lớn hơn:
    chép nhãn nguồn và giữ luật trích dẫn cần model tuân lệnh tốt).
    """
    from langgraph.graph import END, START, StateGraph

    profile = profile or get_profile()
    if model is None:
        from app.core.llm import get_llm

        planner = get_llm("research")
        note_taker = writer = get_llm("research_topic")
    else:
        planner = writer = note_taker = model
    tools = default_deep_tools(profile) if tools is None else tools

    def hoi(llm, prompt: str) -> str:
        return message_text(llm.invoke(prompt).content).strip()

    def plan(state: DeepState) -> dict:
        dong = hoi(planner, PLAN_PROMPT.format(n=profile.deep_sub_questions, question=state["question"]))
        cau = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", d).strip() for d in dong.splitlines()]
        cau = [c for c in cau if c][: profile.deep_sub_questions] or [state["question"]]
        return {"sub_questions": cau, "queries": dict(enumerate(cau)), "evidence": {}, "notes": {},
                "rounds_left": profile.deep_refine_rounds}

    def search(state: DeepState) -> dict:
        evidence = dict(state["evidence"])
        for i, q in state["queries"].items():
            phan = [evidence.get(i, "")] + [str(t.invoke(q)) for t in tools]
            evidence[i] = "\n\n".join(p for p in phan if p)
        return {"evidence": evidence}

    def notes(state: DeepState) -> dict:
        ghi_chu, queries = dict(state["notes"]), {}
        con_vong = state["rounds_left"] > 0
        for i in state["queries"]:
            out = hoi(note_taker, NOTES_PROMPT.format(
                sub_question=state["sub_questions"][i], evidence=state["evidence"][i],
                fallback=FALLBACK_TIM_THEM if con_vong else FALLBACK_HET_VONG,
            ))
            them = TIM_THEM_RE.search(out)
            if them and con_vong:
                queries[i] = them.group(1).strip()
            ghi_chu[i] = "" if them or out.upper().startswith(KHONG_DU) else out
        return {"notes": ghi_chu, "queries": queries,
                "rounds_left": state["rounds_left"] - (1 if queries else 0)}

    def write(state: DeepState) -> dict:
        co = [i for i in range(len(state["sub_questions"])) if state["notes"].get(i)]
        if not co:
            return {"report": f"{KHONG_DU}: không tìm được nguồn nào trả lời được câu hỏi.",
                    "grounding": {"removed": 0, "missing_source": 0, "violations": []}}
        khoi = "\n\n".join(f"Sub-question {n}: {state['sub_questions'][i]}\n{state['notes'][i]}"
                           for n, i in enumerate(co, 1))
        bai = hoi(writer, WRITE_PROMPT.format(question=state["question"], notes=khoi))
        bai = re.sub(r"【(\d{1,3})】", r"[\1]", bai)  # gpt-oss hay viết 【1】
        sach, bc = apply_grounding_policy(bai, "\n\n".join(state["evidence"].values()))
        return {"report": sach, "grounding": bc}

    g = StateGraph(DeepState)
    for ten, fn in (("plan", plan), ("search", search), ("notes", notes), ("write", write)):
        g.add_node(ten, fn)
    g.add_edge(START, "plan")
    g.add_edge("plan", "search")
    g.add_edge("search", "notes")
    g.add_conditional_edges("notes", lambda s: "search" if s["queries"] else "write", ["search", "write"])
    g.add_edge("write", END)
    return g.compile()


def render_markdown(state: DeepState, mode: str, ngay: Optional[datetime] = None) -> str:
    """State -> nội dung file .md. Thuần Python, không gọi LLM."""
    ngay = ngay or datetime.now()
    bc = state.get("grounding") or {}
    than = state.get("report", "")
    con_lai = kiem_tra_grounding(than, ["\n\n".join(state.get("evidence", {}).values())])
    than_md = "\n".join("## Tài liệu tham khảo" if TIEU_DE_NGUON_RE.match(d) else d for d in than.splitlines())
    da_tra = [f"{n}. {q}" + ("" if state["notes"].get(i) else " — *không đủ dữ liệu*")
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
    """Chạy cả quy trình, ghi file .md, trả {markdown, path, filename, report, sub_questions, grounding}."""
    profile = get_profile(mode)
    state = build_deep_research(model=model, tools=tools, profile=profile).invoke({"question": question})
    md = render_markdown(state, profile.name)
    thu_muc = Path(out_dir or THU_MUC_BAO_CAO)
    thu_muc.mkdir(parents=True, exist_ok=True)
    path = thu_muc / f"research_{datetime.now():%Y%m%d_%H%M%S}_{_slug(question)}.md"
    path.write_text(md, encoding="utf-8")
    return {"markdown": md, "path": str(path), "filename": path.name, "report": state["report"],
            "sub_questions": state["sub_questions"], "grounding": state.get("grounding", {}),
            "mode": profile.name}


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
