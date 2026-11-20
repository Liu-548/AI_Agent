"""weather/economy/geo/dictionary agent (Phase 6). OFFLINE: dữ liệu API là dict mẫu, không gọi mạng/LLM."""

from __future__ import annotations

import json

import pytest
import requests
from langchain_core.messages import AIMessage

from app.agents.research_agent.profiles import PROFILES
from app.agents.research_agent.tools import SearchBudget
from app.agents.research_agent.topics import TOPIC_SPECS, make_topic_tool
from app.agents.research_agent.topics.dictionary_agent import tools as dictionary
from app.agents.research_agent.topics.economy_agent import tools as economy
from app.agents.research_agent.topics.geo_agent import tools as geo
from app.agents.research_agent.topics.weather_agent import tools as weather
from tests.fakes import FakeToolCallingModel, tool_call

PROFILE = PROFILES["standard"]
SPEC = {s.name: s for s in TOPIC_SPECS}

GEO = {"results": [{"name": "Da Lat", "country": "Vietnam", "admin1": "Lam Dong", "latitude": 11.94,
                    "longitude": 108.44, "timezone": "Asia/Ho_Chi_Minh"}]}
FORECAST = {
    "timezone": "Asia/Ho_Chi_Minh",
    "current": {"time": "2026-11-15T16:00", "temperature_2m": 19.5, "apparent_temperature": 18.9,
                "relative_humidity_2m": 82, "weather_code": 61, "wind_speed_10m": 9.4},
    "current_units": {"temperature_2m": "°C", "apparent_temperature": "°C", "wind_speed_10m": "km/h"},
    "daily": {"time": ["2026-11-15", "2026-11-16"], "weather_code": [61, 2],
              "temperature_2m_min": [15.1, 14.8], "temperature_2m_max": [22.0, 23.4],
              "precipitation_probability_max": [80, 20]},
}
WB = [{"page": 1}, [
    {"indicator": {"id": "FP.CPI.TOTL.ZG", "value": "Inflation, consumer prices (annual %)"},
     "country": {"id": "VN", "value": "Viet Nam"}, "countryiso3code": "VNM", "date": "2024", "value": 3.62},
    {"indicator": {"id": "FP.CPI.TOTL.ZG", "value": "Inflation, consumer prices (annual %)"},
     "country": {"id": "VN", "value": "Viet Nam"}, "countryiso3code": "VNM", "date": "2023", "value": 3.25},
]]
FX = {"result": "success", "time_last_update_utc": "Sun, 15 Nov 2026 00:02:31 +0000",
      "rates": {"USD": 1, "VND": 26350.0}}
WB_COUNTRIES = [{"page": 1}, [
    {"id": "EAS", "iso2Code": "Z4", "name": "East Asia & Pacific", "region": {"id": "NA", "value": "Aggregates"}},
    {"id": "KOR", "iso2Code": "KR", "name": "Korea, Rep.", "capitalCity": "Seoul", "latitude": "37.5", "longitude": "127",
     "region": {"id": "EAS", "value": "East Asia & Pacific"}, "incomeLevel": {"value": "High income"}},
    {"id": "VNM", "iso2Code": "VN", "name": "Viet Nam", "capitalCity": "Hanoi", "latitude": "21.0069",
     "longitude": "105.825", "region": {"id": "EAS", "value": "East Asia & Pacific"},
     "incomeLevel": {"value": "Upper middle income"}},
]]
WB_POP = [{"page": 1}, [{"date": "2025", "value": 101598527}]]
WB_AREA = [{"page": 1}, [{"date": "2024", "value": 331338.31}]]


def get_geo(url, params=None):
    return WB_POP if "SP.POP" in url else WB_AREA if "AG.SRF" in url else WB_COUNTRIES


DICT = [{"word": "serendipity", "phonetics": [{"text": "/ˌsɛɹ.ənˈdɪp.ɪ.ti/"}], "meanings": [
    {"partOfSpeech": "noun", "synonyms": ["luck"], "antonyms": [],
     "definitions": [{"definition": "An unsought, unintended, and/or unexpected discovery.",
                      "example": "Finding it was pure serendipity."}]},
]}]


def _404(*a, **k):
    resp = requests.Response()
    resp.status_code = 404
    raise requests.HTTPError(response=resp)


# ------------------------------------------------------------------ định dạng
def test_thoi_tiet_dinh_dang():
    def get(url, params=None):
        return GEO if "geocoding" in url else FORECAST

    khoi = weather.tim_thoi_tiet(get, "Da Lat", 2)[0]
    assert khoi.startswith("Label: [open-meteo: Da Lat, Vietnam]")
    assert "light rain, 19.5°C" in khoi and "2026-11-16: partly cloudy, 14.8–23.4°C, rain chance 20%" in khoi


def test_thoi_tiet_khong_thay_dia_diem():
    assert weather.tim_thoi_tiet(lambda url, params=None: {}, "Atlantis", 3) == []


@pytest.mark.parametrize("text,ket_qua", [
    ("VNM inflation", ("VNM", "FP.CPI.TOTL.ZG")),
    ("usa gdp per capita", ("USA", "NY.GDP.PCAP.CD")),
    ("JPN, gdp growth", ("JPN", "NY.GDP.MKTP.KD.ZG")),
    ("VNM weather", None),
])
def test_tach_truy_van_worldbank(text, ket_qua):
    assert economy.tach_truy_van(text) == ket_qua


def test_worldbank_va_ty_gia_dinh_dang():
    wb = economy.tim_worldbank(lambda url, params=None: WB, "VNM inflation", 5)[0]
    assert wb.startswith("Label: [worldbank: VNM/FP.CPI.TOTL.ZG]") and "2024: 3.62 | 2023: 3.25" in wb
    fx = economy.tim_ty_gia(lambda url, params=None: FX, "USD VND")[0]
    assert fx.startswith("Label: [exchangerate: USD-VND]") and "1 USD = 26,350.0000 VND" in fx
    assert economy.tim_ty_gia(lambda url, params=None: FX, "USD XYZ") == []


def test_worldbank_ma_nuoc_sai_la_khong_co_ket_qua():
    assert economy.tim_worldbank(lambda url, params=None: [{"message": [{"id": "120"}]}], "XXX gdp", 5) == []


@pytest.mark.parametrize("text,iso3", [
    ("Vietnam", "VNM"), ("viet nam", "VNM"), ("VN", "VNM"), ("South Korea", "KOR"), ("korea", "KOR"),
    ("East Asia", None), ("Narnia", None),
])
def test_chon_nuoc_theo_ten_ma_bi_danh(text, iso3):
    c = geo.chon_nuoc(WB_COUNTRIES[1], text)
    assert (c or {}).get("id") == iso3


def test_quoc_gia_dinh_dang():
    khoi = geo.tim_quoc_gia(get_geo, "Vietnam")[0]
    assert khoi.startswith("Label: [worldbank-country: VNM]") and "Capital: Hanoi" in khoi
    assert "Population: 101,598,527 (2025)" in khoi and "Surface area (km²): 331,338 (2024)" in khoi
    assert geo.tim_quoc_gia(get_geo, "Narnia") == []


def test_tu_dien_dinh_dang_va_404():
    khoi = dictionary.tim_tu(lambda url, params=None: DICT, "Serendipity", 2)[0]
    assert khoi.startswith("Label: [dictionary: serendipity]") and "/ˌsɛɹ.ənˈdɪp.ɪ.ti/" in khoi
    assert "(noun) An unsought" in khoi and "Synonyms: luck" in khoi
    assert dictionary.tim_tu(_404, "qwzx", 2) == []


def test_tool_la_cua_bon_chu_de_moi():
    ten = lambda n: [t.name for t in SPEC[n].default_tools(SearchBudget(max_calls=3), PROFILE)]  # noqa: E731
    assert ten("weather_agent") == ["weather_forecast"]
    assert ten("economy_agent") == ["worldbank_indicator", "exchange_rate"]
    assert ten("geo_agent") == ["country_lookup", "wikipedia_search"]
    assert ten("dictionary_agent") == ["dictionary_lookup", "wikipedia_search"]


def test_economy_tool_dau_vao_sai_tra_loi_ro():
    out = economy.make_worldbank_tool(SearchBudget(max_calls=3)).invoke({"text": "Vietnam weather"})
    assert out.startswith("ERROR") and "ISO3" in out


# ------------------------------------------------------------------ e2e (model giả)
def test_weather_agent_e2e_giu_cau_co_nhan(monkeypatch):
    monkeypatch.setattr(weather, "get_json", lambda url, params=None: GEO if "geocoding" in url else FORECAST)
    model = FakeToolCallingModel(responses=[
        AIMessage(content="", tool_calls=[tool_call("weather_forecast", {"text": "Da Lat"})]),
        AIMessage(content="Da Lat currently has light rain at 19.5°C [open-meteo: Da Lat, Vietnam]."),
    ])
    msg = make_topic_tool(SPEC["weather_agent"], profile=PROFILE, model=model).invoke(
        {"name": "weather_agent", "args": {"text": "weather in Da Lat"}, "id": "c1", "type": "tool_call"}
    )
    assert "19.5°C" in json.loads(msg.content)["answer"]
