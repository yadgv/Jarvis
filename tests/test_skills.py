import time

import config
import skills
from skills import stocks, system, timers, weather, web_search


class Resp:
    def __init__(self, text=None, js=None, status=200):
        self.text, self._js, self.status_code = text, js, status

    def raise_for_status(self):
        pass

    def json(self):
        return self._js


def test_formats_match_each_provider():
    names = [t["name"] for t in skills.anthropic_tools()]
    assert names == [t["function"]["name"] for t in skills.openai_tools()]
    assert {"set_timer", "get_weather", "web_search", "stock_price", "shut_down"} <= set(names)


def test_unknown_tool_and_errors_return_text():
    assert "Unknown tool" in skills.run("nope", {})
    assert "failed" in skills.run("get_weather", {"location": "x", "days": "abc"})


def test_timer_fires_and_cancel():
    said = []
    timers.announce = said.append
    skills.run("set_timer", {"seconds": 0.2, "label": "tea"})
    skills.run("set_timer", {"seconds": 3600, "label": "pasta"})
    assert "pasta" in skills.run("list_timers", {})
    time.sleep(0.5)
    assert said == ["Sir, your tea timer is done."]
    assert skills.run("cancel_timer", {"label": "all"}) == "Cancelled 1."
    assert "HH:MM" in skills.run("set_alarm", {"time": "7pm"})


def test_weather(monkeypatch):
    def get(url, params, timeout):
        if "geocoding" in url:
            return Resp(js={"results": [
                {"name": "Courtice", "admin1": "Pennsylvania", "country": "United States", "latitude": 1, "longitude": 1},
                {"name": "Courtice", "admin1": "Ontario", "country": "Canada", "latitude": 43.9, "longitude": -78.8}]})
        return Resp(js={"current": {"temperature_2m": 2.4, "apparent_temperature": -1.2, "weather_code": 3, "wind_speed_10m": 14.6},
                        "daily": {"time": ["2026-11-25"], "weather_code": [61], "temperature_2m_max": [4.1],
                                  "temperature_2m_min": [-1.0], "precipitation_probability_max": [80]}})
    monkeypatch.setattr(weather.requests, "get", get)
    assert weather._find_place("Courtice, Ontario")[2] == "Courtice, Ontario, Canada"
    out = skills.run("get_weather", {"location": "Courtice, Ontario"})
    assert "2°C" in out and "light rain" in out and "80% chance of rain" in out


def test_search_falls_back_to_html(monkeypatch):
    page = ('<a class="result__a" href="x">NVIDIA <b>Stock</b></a>'
            '<a class="result__snippet" href="x">$181 &amp; rising</a>')
    monkeypatch.setattr(web_search.requests, "post", lambda *a, **k: Resp(text=page))
    monkeypatch.setattr(web_search, "DDGS", None)
    assert skills.run("web_search", {"query": "nvda"}) == "- NVIDIA Stock: $181 & rising"


def test_stock_price(monkeypatch):
    monkeypatch.setattr(stocks.requests, "get", lambda *a, **k: Resp(js={"chart": {"result": [{"meta": {
        "regularMarketPrice": 181.2, "chartPreviousClose": 178.0, "currency": "USD", "longName": "NVIDIA Corporation"}}]}}))
    assert skills.run("stock_price", {"symbol": "nvda"}).startswith("NVIDIA Corporation (NVDA): 181.20 USD, up 1.8%")


def test_shutdown_flag():
    skills.run("shut_down", {})
    assert system.shutdown_requested
    system.shutdown_requested = False
