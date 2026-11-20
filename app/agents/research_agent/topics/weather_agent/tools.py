"""Tool lá của weather_agent: weather_forecast (Open-Meteo, không key).

Hai lượt HTTP trong MỘT lần gọi tool (chỉ tốn một lượt SearchBudget):
1. Geocoding API: tên địa điểm -> toạ độ + múi giờ.
2. Forecast API: thời tiết hiện tại + dự báo theo ngày (timezone=auto).
Điều khoản: dùng phi thương mại, < 10.000 request/ngày — dư sức cho đồ án.

Nhãn: [open-meteo: <Tên>, <Quốc gia>].
"""

from __future__ import annotations

from typing import Callable, Dict, List

from app.agents.research_agent.profiles import SearchProfile
from app.agents.research_agent.tools import SearchBudget
from app.agents.research_agent.topics.web_tool import get_json, make_web_tool

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Mã thời tiết WMO -> chữ (rút gọn theo bảng của Open-Meteo).
WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "rime fog",
    51: "light drizzle", 53: "drizzle", 55: "dense drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light showers", 81: "showers", 82: "violent showers", 85: "snow showers", 86: "snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
}


def mo_ta(ma) -> str:
    return WMO.get(ma, f"weather code {ma}")


def tim_thoi_tiet(get: Callable[..., Dict], text: str, days: int = 3) -> List[str]:
    """`get` = get_json (test truyền hàm giả). Trả [] khi không tìm thấy địa điểm."""
    noi = ((get(GEOCODING_URL, {"name": text, "count": 1, "language": "en", "format": "json"}) or {})
           .get("results") or [])
    if not noi:
        return []
    p = noi[0]
    ten = f"{p.get('name', text)}, {p.get('country', '-')}"
    d = get(FORECAST_URL, {
        "latitude": p["latitude"], "longitude": p["longitude"], "timezone": "auto", "forecast_days": days,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    })
    c, u = d.get("current") or {}, d.get("current_units") or {}
    dong = [
        f"Label: [open-meteo: {ten}]",
        f"Place: {ten} | Region: {p.get('admin1', '-')} | Coordinates: {p['latitude']}, {p['longitude']}"
        f" | Timezone: {d.get('timezone', p.get('timezone', '-'))}",
        f"Current ({c.get('time', '-')} local): {mo_ta(c.get('weather_code'))}, "
        f"{c.get('temperature_2m')}{u.get('temperature_2m', '°C')} "
        f"(feels like {c.get('apparent_temperature')}{u.get('apparent_temperature', '°C')}), "
        f"humidity {c.get('relative_humidity_2m')}%, wind {c.get('wind_speed_10m')} {u.get('wind_speed_10m', 'km/h')}",
    ]
    ng = d.get("daily") or {}
    for i, ngay in enumerate(ng.get("time") or []):
        lay = lambda k: (ng.get(k) or [None] * (i + 1))[i]  # noqa: E731
        dong.append(
            f"{ngay}: {mo_ta(lay('weather_code'))}, {lay('temperature_2m_min')}–{lay('temperature_2m_max')}°C, "
            f"rain chance {lay('precipitation_probability_max')}%"
        )
    dong.append(f"URL: https://open-meteo.com/en/docs#latitude={p['latitude']}&longitude={p['longitude']}")
    return ["\n".join(dong)]


def make_weather_tool(budget: SearchBudget, days: int = 3):
    return make_web_tool(
        budget, name="weather_forecast", error_code="OPENMETEO_UNAVAILABLE",
        description=(
            "Get the current weather and a daily forecast for a city or place from Open-Meteo: "
            "sky, temperature, feels-like, humidity, wind, daily min/max and rain chance. Input: "
            "the place name in English without diacritics, optionally with the country. Returns "
            "Label, Place, Current, one line per day, URL."
        ),
        search=lambda q: tim_thoi_tiet(get_json, q, days),
    )


def default_weather_tools(budget: SearchBudget, profile: SearchProfile) -> List:
    # eco: 3 ngày; standard/full: 5 ngày (ngắn gọn để không phình context).
    return [make_weather_tool(budget, days=3 if profile.name == "eco" else 5)]
