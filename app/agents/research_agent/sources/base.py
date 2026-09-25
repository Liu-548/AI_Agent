"""Lớp nền của các nguồn học thuật: PaperRecord, SourceError, http_get, khử trùng, xếp hạng.

Mỗi nguồn (arXiv, OpenAlex, Semantic Scholar, PubMed, Crossref) có một file riêng
làm đúng một việc: gọi API rồi đổi kết quả sang PaperRecord — dạng chuẩn hoá
chung. Nhờ vậy phần còn lại (khử trùng, xếp hạng, định dạng cho LLM) không cần
biết bài báo đến từ đâu (mẫu Adapter).

Mọi lỗi của lớp nguồn là SourceError. Nó chỉ sống BÊN TRONG lớp nguồn: tầng tool
bắt nó và đổi thành chuỗi "ERROR: ..." (tool không bao giờ raise).
"""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

import requests

log = logging.getLogger(__name__)

# Thứ tự ưu tiên khi gộp trường của cùng một bài từ nhiều nguồn (SPEC §5.3).
THU_TU_UU_TIEN = ("arxiv", "crossref", "openalex", "semantic_scholar", "pubmed")
# Thứ tự ưu tiên khi chọn nhãn để trích dẫn (SPEC §5.6).
THU_TU_NHAN = ("arxiv", "doi", "pmid", "openalex", "s2")

_TRE_KHI_THU_LAI = 2.0  # giây, chờ trước lần thử lại duy nhất
_KHOA_BI_MAT = ("api_key", "x-api-key")


class SourceError(Exception):
    """Lỗi nội bộ của lớp nguồn. `code` theo SPEC §5.11, vd OPENALEX_RATE_LIMITED."""

    def __init__(self, code: str, message: str, status: Optional[int] = None):
        super().__init__(f"{code} | {message}")
        self.code = code
        self.message = message
        self.status = status


@dataclass
class PaperRecord:
    title: str
    year: Optional[int] = None
    published: Optional[str] = None   # "YYYY-MM-DD". arXiv: NGÀY NỘP, không phải Last updated
    authors: List[str] = field(default_factory=list)
    venue: Optional[str] = None
    abstract: Optional[str] = None
    citations: Optional[int] = None
    ids: Dict[str, str] = field(default_factory=dict)  # khoá: arxiv | doi | pmid | openalex | s2
    url: Optional[str] = None
    found_in: List[str] = field(default_factory=list)  # các nguồn đã trả về bài này
    rank: int = 0  # vị trí (0 = đầu) trong danh sách của nguồn; gộp thì lấy vị trí tốt nhất

    def primary_label(self) -> str:
        """Nhãn dùng để trích dẫn, kèm ngoặc vuông. '' nếu bài không có mã nào."""
        for loai in THU_TU_NHAN:
            ma = self.ids.get(loai)
            if not ma:
                continue
            if loai == "arxiv":
                return f"[http://arxiv.org/abs/{ma}]"
            return f"[{loai}: {ma}]"
        return ""


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def _che_key(params: Optional[dict]) -> dict:
    return {k: ("***" if k.lower() in _KHOA_BI_MAT else v) for k, v in (params or {}).items()}


def user_agent() -> str:
    from app.core import config

    email = config.settings.openalex_mailto
    return f"visual-agentic-ai/1.0 (mailto:{email})" if email else "visual-agentic-ai/1.0"


def http_get(
    source: str,
    url: str,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = 15,
    expect: str = "json",
    sleep=None,
):
    """Hàm DUY NHẤT gọi HTTP của lớp nguồn. Trả JSON đã parse ("json") hoặc Element ("xml").

    429 hoặc 5xx: thử lại ĐÚNG 1 lần sau 2 giây. Không bao giờ ghi URL/tham số có
    key vào log (che api_key) và không đưa URL vào thông điệp lỗi (requests hay
    nhét cả query string, tức là cả key, vào message của exception).
    """
    src = source.upper()
    head = {"User-Agent": user_agent(), **(headers or {})}
    log.debug("GET %s params=%s", url.split("?")[0], _che_key(params))

    resp = None
    for lan in (1, 2):
        try:
            resp = requests.get(url, params=params, headers=head, timeout=timeout)
        except requests.RequestException as exc:
            # Chỉ ghi tên lớp lỗi, không ghi str(exc) (có thể chứa key trong URL).
            raise SourceError(f"{src}_UNAVAILABLE", type(exc).__name__) from None
        if (resp.status_code == 429 or resp.status_code >= 500) and lan == 1:
            (sleep or time.sleep)(_TRE_KHI_THU_LAI)
            continue
        break

    if resp.status_code == 429:
        raise SourceError(f"{src}_RATE_LIMITED", "HTTP 429", status=429)
    if not 200 <= resp.status_code < 300:
        raise SourceError(f"{src}_HTTP_ERROR", f"HTTP {resp.status_code}", status=resp.status_code)
    try:
        if expect == "xml":
            return ET.fromstring(resp.text)
        return resp.json()
    except (ValueError, ET.ParseError):
        raise SourceError(f"{src}_BAD_RESPONSE", f"body không phải {expect.upper()} hợp lệ") from None


def cat_gon(text: Optional[str], toi_da: int) -> str:
    """Gộp khoảng trắng rồi cắt còn `toi_da` ký tự (thêm '...' nếu bị cắt)."""
    text = " ".join((text or "").split())
    return text if len(text) <= toi_da else text[:toi_da].rstrip() + "..."


# --------------------------------------------------------------------------- #
# Khử trùng
# --------------------------------------------------------------------------- #
def _chuan_tieu_de(title: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).split())


def _arxiv_khong_version(ma: str) -> str:
    return re.sub(r"v\d+$", "", (ma or "").lower())


def _cung_bai(a: PaperRecord, b: PaperRecord) -> bool:
    """Hai bản ghi là một bài nếu trùng DOI, mã arXiv (bỏ version), PMID, hoặc
    tiêu đề chuẩn hoá + năm gần nhau (lệch tối đa 1 năm, hoặc một bên thiếu năm)."""
    for khoa in ("doi", "pmid"):
        if a.ids.get(khoa) and a.ids[khoa].lower() == b.ids.get(khoa, "").lower():
            return True
    if a.ids.get("arxiv") and _arxiv_khong_version(a.ids["arxiv"]) == _arxiv_khong_version(
        b.ids.get("arxiv", "")
    ):
        return True
    ta = _chuan_tieu_de(a.title)
    if ta and ta == _chuan_tieu_de(b.title):
        return a.year is None or b.year is None or abs(a.year - b.year) <= 1
    return False


def _do_uu_tien(rec: PaperRecord) -> int:
    ds = [THU_TU_UU_TIEN.index(s) for s in rec.found_in if s in THU_TU_UU_TIEN]
    return min(ds) if ds else len(THU_TU_UU_TIEN)


def _gop(nhom: List[PaperRecord]) -> PaperRecord:
    """Gộp các bản ghi của cùng một bài: trường rỗng lấy từ nguồn ưu tiên kế tiếp,
    abstract dài nhất, citations lớn nhất, published của arXiv (ưu tiên nhất) thắng."""
    theo_uu_tien = sorted(nhom, key=_do_uu_tien)
    dau = theo_uu_tien[0]
    kq = replace(dau, ids=dict(dau.ids), found_in=[], authors=list(dau.authors))
    for r in nhom:  # found_in theo thứ tự xuất hiện
        for s in r.found_in:
            if s not in kq.found_in:
                kq.found_in.append(s)
    for r in theo_uu_tien[1:]:
        for truong in ("title", "year", "published", "venue", "url"):
            if not getattr(kq, truong):
                setattr(kq, truong, getattr(r, truong))
        if not kq.authors:
            kq.authors = list(r.authors)
        for k, v in r.ids.items():
            kq.ids.setdefault(k, v)
    kq.abstract = max((r.abstract or "" for r in nhom), key=len) or None
    dem = [r.citations for r in nhom if r.citations is not None]
    kq.citations = max(dem) if dem else None
    kq.rank = min(r.rank for r in nhom)
    return kq


def dedupe_records(records: List[PaperRecord]) -> List[PaperRecord]:
    """Gộp các bản ghi trùng bài. Giữ thứ tự xuất hiện đầu tiên của từng bài.

    ponytail: so sánh từng cặp O(n^2) — n chỉ cỡ vài chục bài mỗi câu hỏi. Đổi
    sang chỉ mục theo khoá nếu một ngày n lên hàng nghìn.
    """
    cha = list(range(len(records)))

    def tim(i: int) -> int:
        while cha[i] != i:
            cha[i] = cha[cha[i]]
            i = cha[i]
        return i

    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            if _cung_bai(records[i], records[j]):
                cha[tim(j)] = tim(i)

    nhom: Dict[int, List[PaperRecord]] = {}
    for i, r in enumerate(records):
        nhom.setdefault(tim(i), []).append(r)
    return [_gop(g) for g in nhom.values()]


def rank_records(records: List[PaperRecord], max_results: int) -> List[PaperRecord]:
    """Xếp hạng: nhiều nguồn cùng tìm thấy trước, rồi tới thứ hạng tốt nhất trong nguồn.

    Viết riêng thành một hàm để Phase 2 thay bằng chiến lược khác (Strategy)
    mà không phải đụng chỗ khác.
    """
    return sorted(records, key=lambda r: (-len(r.found_in), r.rank))[:max_results]
