"""Tool lá của economy_agent: worldbank_indicator (World Bank API v2) + exchange_rate (open.er-api.com).

- World Bank Indicators API: không key, không giới hạn công bố. `mrnev=N` = N giá trị
  gần nhất KHÁC rỗng (số liệu năm hiện tại thường chưa có).
  shortcut: chỉ nhận mã quốc gia ISO3/ISO2 do model tự đổi ("Vietnam" -> "VNM"); không gọi
  thêm API tra tên nước để tiết kiệm một lượt HTTP. Model hay đổi đúng các mã phổ biến.
- open.er-api.com (ExchangeRate-API bản mở): không key, cập nhật 1 lần/ngày, có VND
  (Frankfurter/ECB thì không có VND nên không dùng). Điều khoản yêu cầu ghi nguồn -> dòng URL.

Nhãn: [worldbank: <ISO3>/<mã chỉ số>] và [exchangerate: <FROM>-<TO>].
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

from app.agents.research_agent.profiles import SearchProfile
from app.agents.research_agent.tools import SearchBudget
from app.agents.research_agent.topics.web_tool import get_json, make_web_tool

WORLDBANK_URL = "https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
EXCHANGE_URL = "https://open.er-api.com/v6/latest/{base}"

# Từ khoá -> mã chỉ số World Bank. Cụm dài đặt TRƯỚC để "gdp per capita" không khớp nhầm "gdp".
INDICATORS: Tuple[Tuple[str, str], ...] = (
    ("gdp per capita", "NY.GDP.PCAP.CD"),
    ("gdp growth", "NY.GDP.MKTP.KD.ZG"),
    ("gdp", "NY.GDP.MKTP.CD"),
    ("inflation", "FP.CPI.TOTL.ZG"),
    ("unemployment", "SL.UEM.TOTL.ZS"),
    ("population", "SP.POP.TOTL"),
    ("exports", "NE.EXP.GNFS.ZS"),
    ("debt", "GC.DOD.TOTL.GD.ZS"),
    ("fdi", "BX.KLT.DINV.WD.GD.ZS"),
)


def tach_truy_van(text: str) -> Optional[Tuple[str, str]]:
    """"VNM gdp growth" -> ("VNM", "NY.GDP.MKTP.KD.ZG"); sai khuôn -> None."""
    m = re.match(r"\s*([A-Za-z]{2,3})\b[\s,:]*(.*)$", text)
    if not m:
        return None
    nuoc, phan_con = m.group(1).upper(), m.group(2).lower()
    for tu, ma in INDICATORS:
        if tu in phan_con:
            return nuoc, ma
    return None


def tim_worldbank(get: Callable[..., Dict], text: str, years: int) -> List[str]:
    tach = tach_truy_van(text)
    if tach is None:
        raise ValueError(
            "input must be '<ISO3 country code> <indicator>', indicator one of: "
            + ", ".join(t for t, _ in INDICATORS)
        )
    nuoc, ma = tach
    data = get(WORLDBANK_URL.format(country=nuoc, indicator=ma), {"format": "json", "mrnev": years})
    # Thành công: [meta, [điểm...]]; mã nước sai: [{"message": [...]}].
    if not isinstance(data, list) or len(data) < 2 or not data[1]:
        return []
    diem = data[1]
    dau = diem[0]
    gia_tri = " | ".join(
        f"{x['date']}: {x['value']:,.2f}" for x in diem if x.get("value") is not None
    )
    iso3 = dau.get("countryiso3code") or nuoc
    return [
        f"Label: [worldbank: {iso3}/{ma}]\n"
        f"Country: {dau['country']['value']} | Indicator: {dau['indicator']['value']}\n"
        f"Values (most recent first): {gia_tri}\n"
        f"URL: https://data.worldbank.org/indicator/{ma}?locations={iso3}"
    ]


def tim_ty_gia(get: Callable[..., Dict], text: str) -> List[str]:
    ma = re.findall(r"\b[A-Za-z]{3}\b", text)
    if len(ma) < 2:
        raise ValueError("input must be two currency codes, e.g. 'USD VND'")
    tu, den = ma[0].upper(), ma[1].upper()
    data = get(EXCHANGE_URL.format(base=tu))
    if data.get("result") != "success":
        return []
    ty_gia = (data.get("rates") or {}).get(den)
    if ty_gia is None:
        return []
    return [
        f"Label: [exchangerate: {tu}-{den}]\n"
        f"Rate: 1 {tu} = {ty_gia:,.4f} {den} | Inverse: 1 {den} = {1 / ty_gia:,.6f} {tu}\n"
        f"Last update: {data.get('time_last_update_utc', '-')} (daily reference rate, not a bank quote)\n"
        f"URL: https://www.exchangerate-api.com"
    ]


def make_worldbank_tool(budget: SearchBudget, years: int = 5):
    return make_web_tool(
        budget, name="worldbank_indicator", error_code="WORLDBANK_UNAVAILABLE",
        description=(
            "Get recent yearly values of an economic indicator for ONE country from the World "
            "Bank. Input: '<ISO3 country code> <indicator>', e.g. 'VNM inflation'. Indicators: "
            "gdp, gdp growth, gdp per capita, inflation, unemployment, population, exports, debt, "
            "fdi. Returns Label, Country, Indicator, Values by year, URL."
        ),
        search=lambda q: tim_worldbank(get_json, q, years),
    )


def make_exchange_tool(budget: SearchBudget):
    return make_web_tool(
        budget, name="exchange_rate", error_code="EXCHANGERATE_UNAVAILABLE",
        description=(
            "Get today's reference exchange rate between two currencies (updated daily). Input: "
            "two ISO currency codes, e.g. 'USD VND' or 'EUR JPY'. Returns Label, Rate, Inverse, "
            "Last update, URL."
        ),
        search=lambda q: tim_ty_gia(get_json, q),
    )


def default_economy_tools(budget: SearchBudget, profile: SearchProfile) -> List:
    return [make_worldbank_tool(budget, years=3 if profile.name == "eco" else 5), make_exchange_tool(budget)]
