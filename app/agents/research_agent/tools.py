"""Tool của Research Agent: arxiv_search + wikipedia_search.

Mọi tool đều theo hợp đồng ở app/contracts.py:
- nhận đúng một tham số `text: str`
- trả về `str`
- KHÔNG raise: lỗi -> chuỗi "ERROR: <code> | <message>"
"""

from __future__ import annotations

from typing import List, Optional, Set, Tuple

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.contracts import tool_error


class SearchInput(BaseModel):
    text: str = Field(description="The search query / topic to look up.")


# --------------------------------------------------------------------------- #
# Sổ lượt tìm kiếm — cái chặn vòng lặp ReAct
# --------------------------------------------------------------------------- #
class SearchBudget:
    """Sổ ghi lượt tìm kiếm, dùng CHUNG cho mọi tool của một Research Agent.

    Vì sao cần: vòng ReAct chạy ở temperature 0. Khi kết quả trả về không như ý,
    model gặp lại đúng bối cảnh cũ nên ra đúng quyết định cũ -> gọi lại y hệt một
    truy vấn, lặp vô hạn. Hội thoại phình to rồi Groq trả 400 output_parse_failed.

    Chặn ở tầng tool là cách chắc chắn nhất: nhắc trong prompt thì model có thể
    lờ đi, còn tool từ chối thì nó không lặp được. Kiểm tra được bằng test
    thường, không cần gọi mạng và không tốn hạn mức.
    """

    def __init__(self, max_calls: Optional[int] = None):
        self.max_calls = max_calls if max_calls is not None else settings.research_max_searches
        self.tong_luot = 0
        self.da_goi: Set[Tuple[str, str]] = set()

    @staticmethod
    def _chuan_hoa(query: str) -> str:
        return " ".join(query.lower().split())

    def xin_luot(self, ten_tool: str, query: str) -> Optional[str]:
        """None = cho phép gọi. Chuỗi = thông điệp trả thẳng cho model, không gọi mạng."""
        khoa = (ten_tool, self._chuan_hoa(query))
        if khoa in self.da_goi:
            return (
                f"DA TIM TRUY VAN NAY ROI ({ten_tool}: {query!r}). Kết quả nằm ngay "
                "phía trên trong hội thoại. DỪNG gọi tool, trả lời ngay bằng dữ liệu "
                "đã có; nếu dữ liệu không liên quan thì nói thẳng là không tìm thấy."
            )
        if self.tong_luot >= self.max_calls:
            return (
                f"HET LUOT TIM KIEM (tối đa {self.max_calls} lượt cho một câu hỏi). "
                "DỪNG gọi tool và tổng hợp câu trả lời từ các kết quả đã có."
            )
        self.da_goi.add(khoa)
        self.tong_luot += 1
        return None


def tim_arxiv(wrapper, query: str) -> List:
    """Gọi arXiv rồi trả về ĐỐI TƯỢNG GỐC, không lấy chuỗi wrapper định dạng sẵn.

    Vì sao không dùng wrapper.run() hay get_summaries_as_docs():
    - Cả hai đều bỏ mất mã bài báo (Entry ID) -> model buộc phải bịa khi trích dẫn.
    - Thứ cả hai gọi là "Published" thực ra là `result.updated`, tức ngày sửa bản
      mới nhất. RoFormer nộp 04/2021 nhưng bị in thành 2023-11-08. Trích dẫn sai
      năm là lỗi nặng với một Research Agent, mà lại rất khó phát hiện.

    Chỉ dùng thuộc tính công khai của wrapper nên không vỡ khi langchain đổi
    phần thân bên trong.
    """
    q = query[: wrapper.ARXIV_MAX_QUERY_LENGTH]
    if wrapper.is_arxiv_identifier(query):
        tim = wrapper.arxiv_search(id_list=q.split(), max_results=wrapper.top_k_results)
    else:
        tim = wrapper.arxiv_search(q, max_results=wrapper.top_k_results)
    return [
        {
            "entry_id": r.entry_id,
            "published": str(r.published.date()),
            "updated": str(r.updated.date()),
            "title": r.title,
            "authors": ", ".join(a.name for a in r.authors),
            "summary": r.summary,
        }
        for r in tim.results()
    ]


def format_arxiv_docs(items: List[dict], max_chars: int) -> str:
    """Dựng chuỗi kết quả arXiv: mã bài báo + ngày nộp + ngày sửa, rồi mới tới tóm tắt.

    Cắt bớt theo TỪNG bài chứ không cắt cả chuỗi, để bài cuối không mất nguyên
    phần đầu (Entry ID + Title) — thứ đáng giữ nhất khi cần trích dẫn.
    """
    if not items:
        return ""
    phan = max(200, max_chars // len(items))
    khoi = []
    for it in items:
        tom_tat = " ".join((it.get("summary") or "").split())
        if len(tom_tat) > phan:
            tom_tat = tom_tat[:phan].rstrip() + "..."
        khoi.append(
            f"Entry ID: {it.get('entry_id', '(không rõ)')}\n"
            f"Published: {it.get('published', '')}\n"
            f"Last updated: {it.get('updated', '')}\n"
            f"Title: {it.get('title', '')}\n"
            f"Authors: {it.get('authors', '')}\n"
            f"Summary: {tom_tat}"
        )
    return "\n\n".join(khoi)


def make_arxiv_tool(
    top_k: int | None = None,
    max_chars: int | None = None,
    budget: Optional[SearchBudget] = None,
):
    """Tạo tool tra cứu bài báo khoa học trên arXiv."""
    from langchain_community.utilities import ArxivAPIWrapper
    from langchain_core.tools import StructuredTool

    wrapper = ArxivAPIWrapper(
        top_k_results=top_k if top_k is not None else settings.arxiv_top_k,
        doc_content_chars_max=(
            max_chars if max_chars is not None else settings.arxiv_max_chars
        ),
    )

    def _run(text: str) -> str:
        if not text or not text.strip():
            return tool_error("EMPTY_QUERY", "Cần một truy vấn để tìm trên arXiv.")
        if budget is not None:
            tu_choi = budget.xin_luot("arxiv_search", text)
            if tu_choi is not None:
                return tu_choi
        try:
            items = tim_arxiv(wrapper, text.strip())
        except Exception as exc:  # mạng lỗi, arXiv 503, parse lỗi...
            return tool_error("ARXIV_UNAVAILABLE", str(exc))
        if not items:
            return f"Không tìm thấy bài báo arXiv nào cho truy vấn: {text!r}"
        return format_arxiv_docs(items, wrapper.doc_content_chars_max)

    return StructuredTool.from_function(
        func=_run,
        name="arxiv_search",
        description=(
            "Search peer-reviewed and preprint scientific papers on arXiv for a given "
            "topic. Returns publication date, title, authors and a short abstract for "
            "the most relevant papers. Use this for state-of-the-art, methods, papers."
        ),
        args_schema=SearchInput,
    )


def make_wikipedia_tool(
    top_k: int | None = None,
    max_chars: int | None = None,
    budget: Optional[SearchBudget] = None,
):
    """Tạo tool tra cứu khái niệm tổng quát trên Wikipedia."""
    import wikipedia as _wiki_pkg
    from langchain_community.utilities import WikipediaAPIWrapper
    from langchain_core.tools import StructuredTool

    # Wikimedia chặn User-Agent mặc định của requests -> body rỗng -> JSONDecodeError.
    # Bắt buộc set UA theo format "AppName/version (contact)".
    _wiki_pkg.set_user_agent(settings.wikipedia_user_agent)

    wrapper = WikipediaAPIWrapper(
        top_k_results=top_k if top_k is not None else settings.wikipedia_top_k,
        doc_content_chars_max=(
            max_chars if max_chars is not None else settings.wikipedia_max_chars
        ),
    )

    def _run(text: str) -> str:
        if not text or not text.strip():
            return tool_error("EMPTY_QUERY", "Cần một truy vấn để tra Wikipedia.")
        if budget is not None:
            tu_choi = budget.xin_luot("wikipedia_search", text)
            if tu_choi is not None:
                return tu_choi
        try:
            result = wrapper.run(text.strip())
        except Exception as exc:
            return tool_error("WIKIPEDIA_UNAVAILABLE", str(exc))
        if not result or result.strip().lower().startswith("no good"):
            return f"Không tìm thấy trang Wikipedia nào cho truy vấn: {text!r}"
        return result

    return StructuredTool.from_function(
        func=_run,
        name="wikipedia_search",
        description=(
            "Look up an encyclopedic definition or general background of a concept on "
            "Wikipedia. Use this to explain a term, a person, or an organisation. "
            "Do NOT use it to find research papers."
        ),
        args_schema=SearchInput,
    )


def default_research_tools(budget: Optional[SearchBudget] = None) -> List:
    """Hai tool dùng CHUNG một sổ lượt -> tổng số lượt bị chặn, không phải mỗi tool một sổ."""
    if budget is None:
        budget = SearchBudget()
    return [make_arxiv_tool(budget=budget), make_wikipedia_tool(budget=budget)]
