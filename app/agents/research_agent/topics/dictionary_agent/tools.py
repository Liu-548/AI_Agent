"""Tool lá của dictionary_agent: dictionary_lookup (Free Dictionary API, dữ liệu Wiktionary) + wikipedia_search.

dictionaryapi.dev: không key, chỉ tiếng Anh. Từ không có trong từ điển trả HTTP 404 kèm
JSON {"title": "No Definitions Found"} -> coi là "không có kết quả", không phải lỗi dịch vụ.
Dữ liệu Wiktionary theo CC BY-SA -> dòng URL dẫn về trang Wiktionary để ghi nguồn.

Nhãn: [dictionary: <từ>].
"""

from __future__ import annotations

from typing import Callable, Dict, List
from urllib.parse import quote

from app.agents.research_agent.profiles import SearchProfile
from app.agents.research_agent.tools import SearchBudget, make_wikipedia_tool
from app.agents.research_agent.topics.web_tool import cat, get_json, make_web_tool

DICTIONARY_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"


def dinh_dang_tu(data: List[Dict], max_nghia: int) -> List[str]:
    if not data:
        return []
    tu = data[0].get("word", "")
    phat_am = next((p["text"] for e in data for p in e.get("phonetics") or [] if p.get("text")), "-")
    dong, dong_nghia, trai_nghia = [], [], []
    for e in data:
        for m in e.get("meanings") or []:
            loai = m.get("partOfSpeech", "-")
            dong_nghia += m.get("synonyms") or []
            trai_nghia += m.get("antonyms") or []
            for d in (m.get("definitions") or [])[:max_nghia]:
                vd = f' Example: "{cat(d["example"], 120)}"' if d.get("example") else ""
                dong.append(f"- ({loai}) {cat(d.get('definition', ''), 220)}{vd}")
                dong_nghia += d.get("synonyms") or []
                trai_nghia += d.get("antonyms") or []
    gon = lambda xs: ", ".join(list(dict.fromkeys(xs))[:8]) or "-"  # noqa: E731
    return [
        f"Label: [dictionary: {tu}]\n"
        f"Word: {tu} | Pronunciation: {phat_am}\n"
        f"Meanings:\n" + "\n".join(dong[: max_nghia * 3]) + "\n"
        f"Synonyms: {gon(dong_nghia)} | Antonyms: {gon(trai_nghia)}\n"
        f"URL: https://en.wiktionary.org/wiki/{quote(tu.replace(' ', '_'))}"
    ]


def tim_tu(get: Callable[..., Dict], text: str, max_nghia: int) -> List[str]:
    import requests

    try:
        data = get(DICTIONARY_URL.format(word=quote(text.strip().lower())))
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return []
        raise
    return dinh_dang_tu(data if isinstance(data, list) else [], max_nghia)


def make_dictionary_tool(budget: SearchBudget, max_nghia: int = 2):
    return make_web_tool(
        budget, name="dictionary_lookup", error_code="DICTIONARY_UNAVAILABLE",
        description=(
            "Look up ONE English word or short idiom in the Free Dictionary (Wiktionary data): "
            "IPA pronunciation, meanings by part of speech, examples, synonyms, antonyms. Input: "
            "the word, e.g. 'serendipity'. Returns Label, Word, Pronunciation, Meanings, "
            "Synonyms, Antonyms, URL."
        ),
        search=lambda q: tim_tu(get_json, q, max_nghia),
    )


def default_dictionary_tools(budget: SearchBudget, profile: SearchProfile) -> List:
    return [make_dictionary_tool(budget, max_nghia=1 if profile.name == "eco" else 2),
            make_wikipedia_tool(budget=budget)]
