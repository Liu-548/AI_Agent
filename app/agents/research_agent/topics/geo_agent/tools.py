"""Tool lá của geo_agent: country_lookup (World Bank Country API, không key) + wikipedia_search.

Vì sao World Bank mà không phải REST Countries: REST Countries khai tử v1–v4 (11/2026),
bản v5 bắt buộc đăng ký API key — trái nguyên tắc "nguồn miễn phí không key" của đồ án.

Một lần gọi tool = 3 request HTTP nhưng chỉ tốn MỘT lượt SearchBudget:
1. /v2/country?per_page=400: danh sách ~300 mục -> tìm nước theo tên hoặc mã ISO.
2. + 3. dân số (SP.POP.TOTL) và diện tích (AG.SRF.TOTL.K2), giá trị gần nhất khác rỗng.
shortcut: không cache danh sách nước giữa các lượt (mỗi lượt cách nhau cả một lượt LLM,
~100KB/lần). Ngôn ngữ, tiền tệ, nước láng giềng: World Bank không có -> wikipedia_search.

Nhãn: [worldbank-country: <ISO3>].
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional

from app.agents.research_agent.profiles import SearchProfile
from app.agents.research_agent.tools import SearchBudget, make_wikipedia_tool
from app.agents.research_agent.topics.web_tool import get_json, make_web_tool

COUNTRIES_URL = "https://api.worldbank.org/v2/country"
INDICATOR_URL = "https://api.worldbank.org/v2/country/{iso3}/indicator/{code}"

# Tên thường gặp khác hẳn tên chính thức của World Bank ("Korea, Rep.", "Viet Nam"...).
BI_DANH = {
    "southkorea": "KOR", "korea": "KOR", "northkorea": "PRK", "russia": "RUS", "iran": "IRN",
    "egypt": "EGY", "laos": "LAO", "usa": "USA", "us": "USA", "unitedstates": "USA", "america": "USA",
    "uk": "GBR", "britain": "GBR", "england": "GBR", "turkey": "TUR", "syria": "SYR", "venezuela": "VEN",
    "vietnam": "VNM", "slovakia": "SVK", "kyrgyzstan": "KGZ", "yemen": "YEM", "gambia": "GMB",
    "bahamas": "BHS", "congo": "COD", "drc": "COD", "hongkong": "HKG", "macau": "MAC", "czechia": "CZE",
}


def _chuan(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


def chon_nuoc(ds: List[Dict], text: str) -> Optional[Dict]:
    """Tìm theo: mã ISO3/ISO2 -> tên khớp hẳn -> bí danh -> tên chứa chuỗi. Bỏ các mục là khu vực/nhóm."""
    nuoc = [c for c in ds if (c.get("region") or {}).get("id") not in (None, "NA")]
    q, ma = _chuan(text), text.strip().upper()
    for c in nuoc:
        if ma in (c.get("id"), c.get("iso2Code")):
            return c
    for c in nuoc:
        if _chuan(c.get("name")) == q:
            return c
    if q in BI_DANH:
        return next((c for c in nuoc if c.get("id") == BI_DANH[q]), None)
    return next((c for c in nuoc if q and q in _chuan(c.get("name"))), None)


def _chi_so(get: Callable[..., Dict], iso3: str, code: str) -> str:
    data = get(INDICATOR_URL.format(iso3=iso3, code=code), {"format": "json", "mrnev": 1})
    if isinstance(data, list) and len(data) > 1 and data[1]:
        x = data[1][0]
        if x.get("value") is not None:
            return f"{x['value']:,.0f} ({x['date']})"
    return "-"


def tim_quoc_gia(get: Callable[..., Dict], text: str) -> List[str]:
    data = get(COUNTRIES_URL, {"format": "json", "per_page": 400})
    c = chon_nuoc(data[1] if isinstance(data, list) and len(data) > 1 else [], text)
    if c is None:
        return []
    iso3 = c["id"]
    return [
        f"Label: [worldbank-country: {iso3}]\n"
        f"Country: {c.get('name', '-')} | ISO3: {iso3} | ISO2: {c.get('iso2Code', '-')}\n"
        f"Capital: {c.get('capitalCity') or '-'} | Capital coordinates: {c.get('latitude')}, {c.get('longitude')}\n"
        f"Region: {(c.get('region') or {}).get('value', '-')} | "
        f"Income level: {(c.get('incomeLevel') or {}).get('value', '-')}\n"
        f"Population: {_chi_so(get, iso3, 'SP.POP.TOTL')} | "
        f"Surface area (km²): {_chi_so(get, iso3, 'AG.SRF.TOTL.K2')}\n"
        f"URL: https://data.worldbank.org/country/{c.get('iso2Code', iso3)}"
    ]


def make_country_tool(budget: SearchBudget):
    return make_web_tool(
        budget, name="country_lookup", error_code="WORLDBANK_UNAVAILABLE",
        description=(
            "Look up basic facts about ONE country from the World Bank: official name, ISO codes, "
            "capital city, region, income level, latest population and surface area. Input: the "
            "country name in English or its ISO code. Returns Label, Country, Capital, Region, "
            "Income level, Population, Surface area, URL. No languages or currencies "
            "(use wikipedia_search for those)."
        ),
        search=lambda q: tim_quoc_gia(get_json, q),
    )


def default_geo_tools(budget: SearchBudget, profile: SearchProfile) -> List:
    return [make_country_tool(budget), make_wikipedia_tool(budget=budget)]
