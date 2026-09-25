"""Nguồn PubMed (NCBI E-utilities) — hai bước tuần tự.

1. esearch: tìm danh sách PMID theo từ khoá.
2. efetch : lấy bản ghi đầy đủ (XML) của các PMID đó rồi parse.

Không có NCBI_API_KEY thì hạn mức thấp (~3 request/giây) — hai bước gọi tuần tự là ổn.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import List, Optional

from app.agents.research_agent.sources.base import PaperRecord, SourceError, http_get

NGUON = "pubmed"
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def _text(el: Optional[ET.Element]) -> str:
    """Toàn bộ chữ trong một thẻ, kể cả thẻ con như <i>, <sub>."""
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


def parse_efetch(root: ET.Element) -> List[PaperRecord]:
    ket_qua: List[PaperRecord] = []
    for i, art in enumerate(root.iter("PubmedArticle")):
        pmid = _text(art.find("./MedlineCitation/PMID"))
        bai = art.find("./MedlineCitation/Article")
        if bai is None:
            continue
        # Abstract có thể chia nhiều đoạn (BACKGROUND, METHODS...) -> ghép lại.
        abstract = " ".join(_text(a) for a in bai.findall("./Abstract/AbstractText"))

        nam: Optional[int] = None
        ngay = bai.find("./Journal/JournalIssue/PubDate")
        if ngay is not None:
            chuoi = _text(ngay.find("Year")) or _text(ngay.find("MedlineDate"))
            khop = re.search(r"\d{4}", chuoi)  # MedlineDate kiểu "2019 Dec-2020 Jan"
            nam = int(khop.group(0)) if khop else None

        tac_gia = []
        for a in bai.findall("./AuthorList/Author"):
            ho, ten = _text(a.find("LastName")), _text(a.find("Initials"))
            if ho:
                tac_gia.append(f"{ho} {ten}".strip())

        ids = {"pmid": pmid} if pmid else {}
        for aid in art.findall("./PubmedData/ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi" and _text(aid):
                ids["doi"] = _text(aid).lower()

        ket_qua.append(
            PaperRecord(
                title=_text(bai.find("ArticleTitle")),
                year=nam,
                authors=tac_gia,
                venue=_text(bai.find("./Journal/Title")) or None,
                abstract=abstract or None,
                ids=ids,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
                found_in=[NGUON],
                rank=i,
            )
        )
    return ket_qua


def search(query: str, limit: int) -> List[PaperRecord]:
    from app.core import config

    cfg = config.settings
    chung = {"tool": "visual-agentic-ai"}
    if cfg.openalex_mailto:
        chung["email"] = cfg.openalex_mailto
    if cfg.ncbi_api_key:
        chung["api_key"] = cfg.ncbi_api_key

    data = http_get(
        NGUON, ESEARCH, params={"db": "pubmed", "term": query, "retmax": limit, "retmode": "json", **chung}
    )
    try:
        pmids = data["esearchresult"]["idlist"]
    except (KeyError, TypeError):
        raise SourceError("PUBMED_BAD_RESPONSE", "thiếu esearchresult.idlist") from None
    if not pmids:
        return []
    root = http_get(
        NGUON, EFETCH, params={"db": "pubmed", "id": ",".join(pmids), "retmode": "xml", **chung}, expect="xml"
    )
    return parse_efetch(root)
