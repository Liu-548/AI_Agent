"""Tool lá của news_agent: news_search (Google News RSS, không cần key) + wikipedia_search cũ.

Vì sao Google News RSS: miễn phí, không key, có kết quả mới theo ngày, trả về tiêu đề +
tên báo + ngày đăng — đủ cho câu hỏi kiểu "phỏng vấn của Elon Musk năm 2026". Không thêm
thư viện: requests + xml.etree của stdlib.

Nhãn trích dẫn là mã ngắn `gn-xxxxxxxx` (8 ký tự đầu sha1 của link): link Google News dài
~250 ký tự, bắt LLM chép nguyên văn thì dễ sai một ký tự và grounding sẽ xoá câu đúng.
Web UI đổi mã này lại thành link + tiêu đề bài (app/api.py, _link_tin_tuc).
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Dict, List

from app.agents.research_agent.profiles import SearchProfile
from app.agents.research_agent.tools import SearchBudget, make_wikipedia_tool
from app.core.contracts import tool_error

RSS_URL = "https://news.google.com/rss/search"
_CO_DAU_RE = re.compile(r"[^\x00-\x7f]")


def ma_tin(link: str) -> str:
    return "gn-" + hashlib.sha1(link.encode("utf-8")).hexdigest()[:8]


def _phien_ban(text: str) -> Dict[str, str]:
    """Câu có ký tự ngoài ASCII (tiếng Việt có dấu) -> bản tin Việt Nam, còn lại bản Mỹ."""
    if _CO_DAU_RE.search(text):
        return {"hl": "vi", "gl": "VN", "ceid": "VN:vi"}
    return {"hl": "en-US", "gl": "US", "ceid": "US:en"}


def doc_rss(xml_bytes: bytes, limit: int) -> List[Dict[str, str]]:
    """XML RSS -> list bài {id, title, source, date, url}. Tách riêng để test bằng fixture."""
    bai = []
    for item in ET.fromstring(xml_bytes).iter("item"):
        link = (item.findtext("link") or "").strip()
        title = (item.findtext("title") or "").strip()
        source = (item.findtext("source") or "").strip()
        if not link or not title:
            continue
        # Google gắn " - Tên báo" vào cuối tiêu đề; đã có trường source nên bỏ đi.
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        try:
            date = parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
        except (TypeError, ValueError):
            date = ""
        bai.append({"id": ma_tin(link), "title": title, "source": source, "date": date, "url": link})
        if len(bai) >= limit:
            break
    return bai


def dinh_dang(bai: List[Dict[str, str]]) -> str:
    """Khuôn cố định — app/api.py đọc ngược bằng TIN_RE, đổi ở đây thì đổi cả ở đó."""
    return "\n\n".join(
        f"Label: [news: {b['id']}]\nTitle: {b['title']}\nSource: {b['source']} | Published: {b['date']}\nURL: {b['url']}"
        for b in bai
    )


def make_news_tool(budget: SearchBudget, limit: int = 8):
    import requests
    from langchain_core.tools import StructuredTool

    def _run(text: str) -> str:
        if not text or not text.strip():
            return tool_error("EMPTY_QUERY", "Cần một truy vấn để tìm tin tức.")
        tu_choi = budget.xin_luot("news_search", text)
        if tu_choi is not None:
            return tu_choi
        try:
            r = requests.get(
                RSS_URL, params={"q": text.strip(), **_phien_ban(text)}, timeout=15,
                headers={"User-Agent": "Mozilla/5.0 (VisualAgenticAI research assistant)"},
            )
            r.raise_for_status()
            bai = doc_rss(r.content, limit)
        except Exception as exc:  # noqa: BLE001 - tool không raise
            return tool_error("NEWS_UNAVAILABLE", type(exc).__name__)
        if not bai:
            return f"No news found for: {text.strip()}"
        return dinh_dang(bai)

    return StructuredTool.from_function(
        func=_run,
        name="news_search",
        description=(
            "Search recent news articles (Google News) about a person, company or event. "
            "Input: a short headline-style query. Returns Label, Title, Source, Published, URL."
        ),
    )


def default_news_tools(budget: SearchBudget, profile: SearchProfile) -> List:
    return [make_news_tool(budget, limit=profile.max_results + 3), make_wikipedia_tool(budget=budget)]
