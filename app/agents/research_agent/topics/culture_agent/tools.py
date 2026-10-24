"""Tool lá của culture_agent: book_search (Open Library) + music_search (MusicBrainz) + wikipedia_search.

Cả hai nguồn chỉ trả SIÊU DỮ LIỆU (tác giả, năm, thể loại, album...), không trả lời bài
hát hay nội dung sách — nên tool tự nó không đưa văn bản có bản quyền cho model.
Cố ý KHÔNG xin trường `first_sentence` của Open Library vì đó là câu trích từ sách.

- Open Library search.json: không key.
- MusicBrainz ws/2: không key, tối đa ~1 request/giây, bắt buộc User-Agent có liên hệ.
  Mã MBID dài 36 ký tự; nhãn chỉ dùng 8 ký tự đầu (giống news_agent) để model chép
  không sai, URL đầy đủ vẫn nằm ở dòng URL.

Nhãn: [openlibrary: OL45804W] và [musicbrainz: recording/1a2b3c4d].
"""

from __future__ import annotations

from typing import Dict, List

from app.agents.research_agent.profiles import SearchProfile
from app.agents.research_agent.tools import SearchBudget, make_wikipedia_tool
from app.agents.research_agent.topics.web_tool import cat, get_json, make_web_tool

OPENLIBRARY_URL = "https://openlibrary.org/search.json"
MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2/recording"
_OL_FIELDS = "key,title,author_name,first_publish_year,subject,edition_count,language"


def dinh_dang_sach(data: Dict, limit: int) -> List[str]:
    khoi = []
    for d in (data.get("docs") or [])[:limit]:
        ma = d["key"].rsplit("/", 1)[-1]  # "/works/OL45804W" -> "OL45804W"
        khoi.append(
            f"Label: [openlibrary: {ma}]\n"
            f"Title: {d.get('title', '')}\n"
            f"Author: {', '.join(d.get('author_name') or ['-'])} | "
            f"First published: {d.get('first_publish_year', '-')} | Editions: {d.get('edition_count', '-')}\n"
            f"Subjects: {cat(', '.join((d.get('subject') or [])[:8]), 200)}\n"
            f"URL: https://openlibrary.org{d['key']}"
        )
    return khoi


def dinh_dang_nhac(data: Dict, limit: int) -> List[str]:
    khoi = []
    for r in (data.get("recordings") or [])[:limit]:
        nghe_si = "".join(a.get("name", "") + a.get("joinphrase", "") for a in r.get("artist-credit") or [])
        album = ", ".join(dict.fromkeys(x.get("title", "") for x in (r.get("releases") or [])[:3]))
        phut = r.get("length")
        khoi.append(
            f"Label: [musicbrainz: recording/{r['id'][:8]}]\n"
            f"Song: {r.get('title', '')} | Artist: {nghe_si or '-'}\n"
            f"First released: {r.get('first-release-date', '-')} | "
            f"Length: {f'{phut // 60000}:{phut // 1000 % 60:02d}' if phut else '-'}\n"
            f"Releases: {album or '-'}\n"
            f"URL: https://musicbrainz.org/recording/{r['id']}"
        )
    return khoi


def make_book_tool(budget: SearchBudget, limit: int = 3):
    return make_web_tool(
        budget, name="book_search", error_code="OPENLIBRARY_UNAVAILABLE",
        description=(
            "Search Open Library for books: title, author, first publication year, subjects, "
            "number of editions. Use for 'who wrote X', 'books by Y', 'when was Z published'. "
            "Input: title and/or author in English or the original language. Returns Label, "
            "Title, Author, First published, Subjects, URL. Never returns book text."
        ),
        search=lambda q: dinh_dang_sach(get_json(OPENLIBRARY_URL, {"q": q, "limit": limit, "fields": _OL_FIELDS}), limit),
    )


def make_music_tool(budget: SearchBudget, limit: int = 3):
    return make_web_tool(
        budget, name="music_search", error_code="MUSICBRAINZ_UNAVAILABLE",
        description=(
            "Search MusicBrainz for songs (recordings): who performed it, release date, albums "
            "it appears on, length. Use for 'who sang X', 'when was song X released'. Input: the "
            "song title, optionally with the artist. Returns Label, Song, Artist, First released, "
            "Releases, URL. Never returns lyrics."
        ),
        search=lambda q: dinh_dang_nhac(get_json(MUSICBRAINZ_URL, {"query": q, "fmt": "json", "limit": limit}), limit),
    )


def default_culture_tools(budget: SearchBudget, profile: SearchProfile) -> List:
    n = profile.max_results
    return [make_book_tool(budget, n), make_music_tool(budget, n), make_wikipedia_tool(budget=budget)]
