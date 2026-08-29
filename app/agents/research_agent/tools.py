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

    def bat_dau_cau_hoi_moi(self) -> None:
        """Xoá sổ để sang câu hỏi mới.

        Sổ lượt phải tính theo TỪNG CÂU HỎI, không phải theo tiến trình. Chạy CLI
        một câu một lần thì tiến trình chết sau mỗi câu nên không lộ ra. Nhưng bất
        kỳ ai dùng lại một agent đã dựng sẵn cho nhiều câu hỏi — vòng lặp hỏi đáp,
        web, notebook — sẽ thấy câu thứ hai bị chính tool từ chối với
        "DA TIM TRUY VAN NAY ROI", và hết hẳn sau 4 lượt cho CẢ phiên.
        """
        self.tong_luot = 0
        self.da_goi.clear()

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
        metadata={"search_budget": budget},
        description=(
            "Search peer-reviewed and preprint scientific papers on arXiv for a given "
            "topic. Returns publication date, title, authors and a short abstract for "
            "the most relevant papers. Use this for state-of-the-art, methods, papers."
        ),
        args_schema=SearchInput,
    )


def _dung_lai_abstract(inverted_index: Optional[dict]) -> str:
    """OpenAlex tra abstract dang 'inverted index' ({tu: [vi_tri,...]}) de tiet
    kiem bang thong, khong tra van ban thang. Phai dung lai thanh cau van.
    """
    if not inverted_index:
        return ""
    vi_tri_toi_da = max(p for positions in inverted_index.values() for p in positions)
    tu_theo_vi_tri = [""] * (vi_tri_toi_da + 1)
    for tu, positions in inverted_index.items():
        for p in positions:
            tu_theo_vi_tri[p] = tu
    return " ".join(w for w in tu_theo_vi_tri if w)


def tim_openalex(query: str, top_k: int, mailto: str, timeout: float = 10.0) -> List[dict]:
    """Goi thang REST API cua OpenAlex (khong can API key).

    Dung tham so `select=` de CHI lay dung field can dung -> giam kich thuoc
    payload tra ve, tuc la giam so token phai nhet vao prompt cho LLM so voi
    lay nguyen ban ghi day du cua OpenAlex (co the vai KB/bai).
    Tai lieu: https://docs.openalex.org/api-entities/works
    """
    import requests

    params = {
        "search": query,
        "per-page": top_k,
        "select": "id,doi,title,publication_year,authorships,abstract_inverted_index,cited_by_count",
        "mailto": mailto,
    }
    resp = requests.get("https://api.openalex.org/works", params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    items = []
    for w in data.get("results", []) or []:
        tac_gia = ", ".join(
            (a.get("author") or {}).get("display_name", "")
            for a in (w.get("authorships") or [])
            if (a.get("author") or {}).get("display_name")
        )
        items.append(
            {
                "openalex_id": w.get("id") or "",
                "doi": w.get("doi") or "",
                "year": w.get("publication_year"),
                "title": w.get("title") or "(khong co tieu de)",
                "authors": tac_gia,
                "cited_by_count": w.get("cited_by_count", 0),
                "abstract": _dung_lai_abstract(w.get("abstract_inverted_index")),
            }
        )
    return items


def format_openalex_docs(items: List[dict], max_chars: int) -> str:
    """Dung chuoi ket qua OpenAlex: cung khuon voi format_arxiv_docs de model
    ap dung dung mot bo quy tac trich dan cho ca hai nguon.
    """
    if not items:
        return ""
    phan = max(200, max_chars // len(items))
    khoi = []
    for it in items:
        tom_tat = " ".join((it.get("abstract") or "").split())
        if not tom_tat:
            tom_tat = "(khong co abstract)"
        elif len(tom_tat) > phan:
            tom_tat = tom_tat[:phan].rstrip() + "..."
        khoi.append(
            f"OpenAlex ID: {it.get('openalex_id', '(khong ro)')}\n"
            f"DOI: {it.get('doi') or '(khong co)'}\n"
            f"Published: {it.get('year', '')}\n"
            f"Title: {it.get('title', '')}\n"
            f"Authors: {it.get('authors', '')}\n"
            f"Cited by: {it.get('cited_by_count', 0)}\n"
            f"Summary: {tom_tat}"
        )
    return "\n\n".join(khoi)


def make_openalex_tool(
    top_k: int | None = None,
    max_chars: int | None = None,
    mailto: str | None = None,
    budget: Optional[SearchBudget] = None,
):
    """Tao tool tra cuu bai bao tren OpenAlex.

    Khac arxiv_search o cho OpenAlex phu het moi nganh (khong rieng CS/vat ly)
    va co san so luot trich dan (cited_by_count) -- arXiv khong co so nay.
    """
    from langchain_core.tools import StructuredTool

    _top_k = top_k if top_k is not None else settings.openalex_top_k
    _max_chars = max_chars if max_chars is not None else settings.openalex_max_chars
    _mailto = mailto if mailto is not None else settings.openalex_mailto

    def _run(text: str) -> str:
        if not text or not text.strip():
            return tool_error("EMPTY_QUERY", "Cần một truy vấn để tìm trên OpenAlex.")
        if budget is not None:
            tu_choi = budget.xin_luot("openalex_search", text)
            if tu_choi is not None:
                return tu_choi
        try:
            items = tim_openalex(text.strip(), top_k=_top_k, mailto=_mailto)
        except Exception as exc:  # mạng lỗi, OpenAlex 5xx, JSON hỏng...
            return tool_error("OPENALEX_UNAVAILABLE", str(exc))
        if not items:
            return f"Không tìm thấy bài báo OpenAlex nào cho truy vấn: {text!r}"
        return format_openalex_docs(items, _max_chars)

    return StructuredTool.from_function(
        func=_run,
        name="openalex_search",
        metadata={"search_budget": budget},
        description=(
            "Search scientific papers across ALL fields (not limited to CS/physics like "
            "arXiv) via OpenAlex's large open index. Returns title, year, authors, citation "
            "count and abstract. Use this when arxiv_search found nothing relevant, or the "
            "topic is outside CS/physics (biology, medicine, social science, etc.)."
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
        metadata={"search_budget": budget},
        description=(
            "Look up an encyclopedic definition or general background of a concept on "
            "Wikipedia. Use this to explain a term, a person, or an organisation. "
            "Do NOT use it to find research papers."
        ),
        args_schema=SearchInput,
    )


def default_research_tools(budget: Optional[SearchBudget] = None) -> List:
    """Ba tool dùng CHUNG một sổ lượt -> tổng số lượt bị chặn, không phải mỗi tool một sổ.

    Sổ được gắn vào `tool.metadata["search_budget"]` để người gọi lấy lại được mà
    không phải giữ tham chiếu riêng — xem `reset_search_budget()`.
    """
    if budget is None:
        budget = SearchBudget()
    return [
        make_arxiv_tool(budget=budget),
        make_openalex_tool(budget=budget),
        make_wikipedia_tool(budget=budget),
    ]


def reset_search_budget(tools: Optional[List] = None) -> int:
    """Xoá sổ lượt tìm kiếm của mọi tool trong danh sách. Trả về số sổ đã xoá.

    GỌI TRƯỚC MỖI CÂU HỎI MỚI nếu bạn dùng lại một agent đã dựng sẵn:

        tools = default_research_tools()
        agent = build_research_agent(tools=tools)
        while True:                      # vòng lặp hỏi đáp / web / notebook
            cau_hoi = input("> ")
            reset_search_budget(tools)   # <- thiếu dòng này là câu thứ 2 hỏng
            agent.invoke(...)

    CLI một-câu-một-lần (`python -m app.main ...`) KHÔNG cần gọi: tiến trình chết
    sau mỗi câu nên sổ tự mất theo. Hàm này tồn tại cho mọi thứ chạy lâu hơn thế.

    Hai sổ trỏ chung một đối tượng chỉ được xoá một lần (đếm theo id), nên con số
    trả về là số SỔ chứ không phải số tool.
    """
    da_xoa = set()
    for tool in tools or []:
        meta = getattr(tool, "metadata", None)
        budget = meta.get("search_budget") if isinstance(meta, dict) else None
        if isinstance(budget, SearchBudget) and id(budget) not in da_xoa:
            budget.bat_dau_cau_hoi_moi()
            da_xoa.add(id(budget))
    return len(da_xoa)
