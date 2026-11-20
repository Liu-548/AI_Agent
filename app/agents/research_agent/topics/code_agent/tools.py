"""Tool lá của code_agent: github_search (repo) + stackoverflow_search (hỏi đáp lập trình).

Cả hai API đều dùng được KHÔNG cần key:
- GitHub search: ~10 request/phút/IP khi không xác thực -> SearchBudget đủ chặn.
  shortcut: chưa gửi token GitHub; nếu hay dính 403 thì thêm GITHUB_TOKEN vào config.py.
- Stack Exchange: ~300 request/ngày/IP không key. Endpoint /search/excerpts trả sẵn
  đoạn trích văn bản thuần, đỡ phải bóc HTML của body.

Nhãn: [github: owner/repo] và [stackoverflow: <question_id>] — ngắn, model chép đúng.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Dict, List

from app.agents.research_agent.profiles import SearchProfile
from app.agents.research_agent.tools import SearchBudget
from app.agents.research_agent.topics.web_tool import cat, get_json, make_web_tool

GITHUB_URL = "https://api.github.com/search/repositories"
SO_URL = "https://api.stackexchange.com/2.3/search/excerpts"


def dinh_dang_github(data: Dict, limit: int, max_chars: int) -> List[str]:
    khoi = []
    for r in (data.get("items") or [])[:limit]:
        khoi.append(
            f"Label: [github: {r['full_name']}]\n"
            f"Description: {cat(r.get('description'), max_chars)}\n"
            f"Language: {r.get('language') or '-'} | Stars: {r.get('stargazers_count', 0)} | "
            f"Last push: {(r.get('pushed_at') or '')[:10]}"
            + (" | ARCHIVED" if r.get("archived") else "")
            + f"\nURL: {r.get('html_url', '')}"
        )
    return khoi


def dinh_dang_stackoverflow(data: Dict, limit: int, max_chars: int) -> List[str]:
    """Một câu hỏi = một khối; câu trả lời trùng question_id được gộp vào khối của nó."""
    theo_cau_hoi: Dict[int, Dict] = {}
    for it in data.get("items") or []:
        qid = it.get("question_id")
        if qid is None:
            continue
        muc = theo_cau_hoi.setdefault(qid, {"title": it.get("title", ""), "doan": [], "it": it})
        loai = "Accepted answer" if it.get("is_accepted") else it.get("item_type", "question").capitalize()
        muc["doan"].append(f"{loai} (score {it.get('score', 0)}): {cat(html.unescape(it.get('excerpt', '')), max_chars)}")
        if len(theo_cau_hoi) >= limit:
            break
    khoi = []
    for qid, muc in theo_cau_hoi.items():
        it = muc["it"]
        ngay = datetime.fromtimestamp(it.get("creation_date", 0), tz=timezone.utc).date().isoformat()
        khoi.append(
            f"Label: [stackoverflow: {qid}]\n"
            f"Title: {html.unescape(muc['title'])}\n"
            f"Tags: {', '.join(it.get('tags') or [])} | Answered: {'yes' if it.get('is_answered') else 'no'} | "
            f"Asked/posted: {ngay}\n"
            + "\n".join(muc["doan"])
            + f"\nURL: https://stackoverflow.com/q/{qid}"
        )
    return khoi


def make_github_tool(budget: SearchBudget, limit: int = 3, max_chars: int = 300):
    return make_web_tool(
        budget, name="github_search", error_code="GITHUB_UNAVAILABLE",
        description=(
            "Search GitHub repositories (open-source libraries, frameworks, tools). Use to find "
            "which project does something, its language, popularity and activity. Input: short "
            "English keywords. Returns Label, Description, Language, Stars, Last push, URL."
        ),
        search=lambda q: dinh_dang_github(
            get_json(GITHUB_URL, {"q": q, "sort": "stars", "per_page": limit},
                     {"Accept": "application/vnd.github+json"}),
            limit, max_chars,
        ),
    )


def make_stackoverflow_tool(budget: SearchBudget, limit: int = 3, max_chars: int = 300):
    return make_web_tool(
        budget, name="stackoverflow_search", error_code="STACKOVERFLOW_UNAVAILABLE",
        description=(
            "Search Stack Overflow questions and answers. Use for error messages, 'how do I ... "
            "in <language/library>' and common pitfalls. Input: short English keywords or the "
            "key part of an error message. Returns Label, Title, Tags, answer excerpts, URL."
        ),
        search=lambda q: dinh_dang_stackoverflow(
            get_json(SO_URL, {"q": q, "site": "stackoverflow", "order": "desc",
                              "sort": "relevance", "pagesize": limit * 3}),
            limit, max_chars,
        ),
    )


def default_code_tools(budget: SearchBudget, profile: SearchProfile) -> List:
    n, c = profile.max_results, profile.abstract_chars
    return [make_stackoverflow_tool(budget, n, c), make_github_tool(budget, n, c)]
