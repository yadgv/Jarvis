"""Weather from Open-Meteo (free, no API key)."""
import requests

import config

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle", 61: "light rain", 63: "rain",
    65: "heavy rain", 66: "freezing rain", 67: "freezing rain", 71: "light snow",
    73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers", 81: "showers",
    82: "violent showers", 85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail",
}


def _find_place(name):
    r = requests.get(GEOCODE_URL, params={"name": name, "count": 1, "language": "en"}, timeout=10)
    r.raise_for_status()
    results = r.json().get("results") or []
    if not results:
        return None
    p = results[0]
    label = ", ".join(x for x in (p.get("name"), p.get("admin1"), p.get("country")) if x)
    return p["latitude"], p["longitude"], label


def get_weather(a):
    place = (a.get("location") or config.HOME_CITY or "").strip()
    if not place:
        return "No location given and HOME_CITY isn't set in config.py. Ask the user which city."
    found = _find_place(place)
    if not found:
        return f"Couldn't find a place called {place}."
    lat, lon, label = found
    days = max(1, min(7, int(a.get("days", 1)) or 1))
    unit = "fahrenheit" if config.TEMPERATURE_UNIT.lower().startswith("f") else "celsius"
    r = requests.get(FORECAST_URL, params={
        "latitude": lat, "longitude": lon, "timezone": "auto",
        "temperature_unit": unit, "wind_speed_unit": "kmh", "forecast_days": days,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    }, timeout=10)
    r.raise_for_status()
    data = r.json()
    deg = "F" if unit == "fahrenheit" else "C"
    c = data["current"]
    lines = [f"{label}. Now: {round(c['temperature_2m'])}°{deg} "
             f"(feels like {round(c['apparent_temperature'])}°{deg}), "
             f"{CODES.get(c['weather_code'], 'unknown conditions')}, wind {round(c["wind_speed_10m"])} km/h"]
    d = data["daily"]
    for i, day in enumerate(d["time"]):
        rain = d["precipitation_probability_max"][i]
        lines.append(f"{day}: {CODES.get(d['weather_code'][i], 'unknown')}, "
                     f"high {round(d['temperature_2m_max'][i])}°, low {round(d['temperature_2m_min'][i])}°"
                     + (f", {rain}% chance of rain" if rain is not None else ""))
    return ". ".join(lines)


SKILLS = [
    {
        "name": "get_weather",
        "description": (
            "Current weather and the daily forecast. Leave location empty for the user's "
            "home city. days=1 for today, up to 7 for the week ahead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name, e.g. 'Toronto'"},
                "days": {"type": "integer", "minimum": 1, "maximum": 7},
            },
        },
        "run": get_weather,
    },
]
