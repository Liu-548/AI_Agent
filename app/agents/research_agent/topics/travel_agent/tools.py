"""Tool lá của travel_agent: wikivoyage_search + place_lookup (OpenStreetMap Nominatim) + wikipedia_search.

- Wikivoyage (MediaWiki API, không key): hướng dẫn du lịch do cộng đồng viết. Lượt 1 tìm
  trang + đoạn mở đầu; lượt 2 lấy toàn văn trang đứng đầu (mục See/Do/Eat/Get around
  mới là phần có ích) rồi cắt theo profile.
- Nominatim (không key): tên địa điểm -> toạ độ, loại, địa chỉ, giờ mở cửa nếu OSM có.
  Điều khoản: tối đa 1 request/giây và bắt buộc User-Agent có liên hệ (get_json lo phần UA).
  shortcut: không sleep giữa hai lượt vì mỗi lượt cách nhau cả một lượt LLM; nếu sau này
  gọi song song thì phải thêm bộ hãm 1 request/giây.

Nhãn: [wikivoyage: <Tên trang>] và [osm: <node|way|relation>/<id>].
"""

from __future__ import annotations

from typing import Callable, Dict, List

from app.agents.research_agent.profiles import SearchProfile
from app.agents.research_agent.tools import SearchBudget, make_wikipedia_tool
from app.agents.research_agent.topics.web_tool import cat, get_json, make_web_tool

WIKIVOYAGE_API = "https://en.wikivoyage.org/w/api.php"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def tim_wikivoyage(get: Callable[..., Dict], text: str, limit: int, max_chars: int) -> List[str]:
    """`get` = get_json (test truyền hàm giả). Trang đầu lấy toàn văn, các trang sau chỉ mở đầu."""
    goc = {"action": "query", "format": "json", "formatversion": 2}
    ds = get(WIKIVOYAGE_API, {
        **goc, "generator": "search", "gsrsearch": text, "gsrlimit": limit,
        "prop": "extracts|info", "inprop": "url", "exintro": 1, "explaintext": 1,
    })
    trang = sorted((ds.get("query") or {}).get("pages") or [], key=lambda p: p.get("index", 0))
    if not trang:
        return []
    day_du = get(WIKIVOYAGE_API, {**goc, "prop": "extracts", "explaintext": 1, "titles": trang[0]["title"]})
    for p in (day_du.get("query") or {}).get("pages") or []:
        trang[0]["extract"] = p.get("extract") or trang[0].get("extract")
    khoi = []
    for i, p in enumerate(trang):
        # Toàn văn giữ xuống dòng ("== See ==") để model thấy ranh giới mục.
        noi_dung = p.get("extract") or ""
        noi_dung = noi_dung[:max_chars] if i == 0 else cat(noi_dung, max_chars // 4)
        khoi.append(f"Label: [wikivoyage: {p['title']}]\nText: {noi_dung.strip()}\nURL: {p.get('fullurl', '')}")
    return khoi


def dinh_dang_osm(data: List[Dict], limit: int) -> List[str]:
    khoi = []
    for p in data[:limit]:
        the = p.get("extratags") or {}
        them = " | ".join(f"{k}: {the[k]}" for k in ("opening_hours", "website", "phone", "wikipedia") if the.get(k))
        khoi.append(
            f"Label: [osm: {p['osm_type']}/{p['osm_id']}]\n"
            f"Name: {p.get('name') or '-'} | Kind: {p.get('category', '')}/{p.get('type', '')}\n"
            f"Address: {p.get('display_name', '')}\n"
            f"Coordinates: {p.get('lat')}, {p.get('lon')}"
            + (f"\nOSM tags (may be outdated): {them}" if them else "")
            + f"\nURL: https://www.openstreetmap.org/{p['osm_type']}/{p['osm_id']}"
        )
    return khoi


def make_wikivoyage_tool(budget: SearchBudget, limit: int = 3, max_chars: int = 2400):
    return make_web_tool(
        budget, name="wikivoyage_search", error_code="WIKIVOYAGE_UNAVAILABLE",
        description=(
            "Search Wikivoyage travel guides for a destination: what to see and do, where to eat "
            "and stay, how to get there and around, safety and local tips. Input: a place name, "
            "optionally with a topic, in English. Returns Label, Text, URL."
        ),
        search=lambda q: tim_wikivoyage(get_json, q, limit, max_chars),
    )


def make_place_tool(budget: SearchBudget, limit: int = 3):
    return make_web_tool(
        budget, name="place_lookup", error_code="OSM_UNAVAILABLE",
        description=(
            "Look up a specific place on OpenStreetMap: where it is (address, coordinates), what "
            "kind of place it is, and opening hours/website when mapped. Use for one named "
            "landmark, venue or address, not for general travel advice. Input: the place name "
            "with its city. Returns Label, Name, Kind, Address, Coordinates, URL."
        ),
        search=lambda q: dinh_dang_osm(
            get_json(NOMINATIM_URL, {"q": q, "format": "jsonv2", "limit": limit, "extratags": 1}), limit,
        ),
    )


def default_travel_tools(budget: SearchBudget, profile: SearchProfile) -> List:
    n = profile.max_results
    return [
        make_wikivoyage_tool(budget, n, profile.abstract_chars * 4),
        make_place_tool(budget, n),
        make_wikipedia_tool(budget=budget),
    ]
