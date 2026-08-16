from datetime import datetime
from threading import Lock
from time import monotonic
from typing import Any

import httpx

from app.ingestion.open_meteo import OPEN_METEO_FORECAST_URL
from app.ingestion.providers import WeatherProviderError
from app.models import Location

CURRENT_VARIABLES = "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code"
CURRENT_WEATHER_CACHE_SECONDS = 300
CURRENT_WEATHER_TIMEOUT_SECONDS = 4

_cache_lock = Lock()
_current_weather_cache: dict[tuple[int, float, float], tuple[float, dict[str, Any]]] = {}


def fetch_current_weather(location: Location) -> dict[str, Any]:
    cache_key = _cache_key(location)
    cached = _read_cached_weather(cache_key)
    if cached is not None:
        return cached

    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "current": CURRENT_VARIABLES,
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "auto",
    }
    try:
        with httpx.Client(timeout=CURRENT_WEATHER_TIMEOUT_SECONDS) as client:
            response = client.get(OPEN_METEO_FORECAST_URL, params=params)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
    except httpx.HTTPError as exc:
        raise WeatherProviderError("Open-Meteo current weather request failed") from exc

    current = payload.get("current") or {}
    weather = {
        "location_id": location.id,
        "source": "Open-Meteo current weather",
        "temperature_f": current.get("temperature_2m"),
        "relative_humidity_percent": current.get("relative_humidity_2m"),
        "wind_speed_mph": current.get("wind_speed_10m"),
        "weather_code": current.get("weather_code"),
        "condition": _weather_code_label(current.get("weather_code")),
        "observed_at": _parse_observed_at(current.get("time")),
        "timezone": payload.get("timezone") or location.timezone,
    }
    _write_cached_weather(cache_key, weather)
    return weather


def clear_current_weather_cache() -> None:
    with _cache_lock:
        _current_weather_cache.clear()


def _cache_key(location: Location) -> tuple[int, float, float]:
    return (location.id, round(location.latitude, 4), round(location.longitude, 4))


def _read_cached_weather(cache_key: tuple[int, float, float]) -> dict[str, Any] | None:
    with _cache_lock:
        cached = _current_weather_cache.get(cache_key)
        if cached is None:
            return None

        cached_at, weather = cached
        if monotonic() - cached_at > CURRENT_WEATHER_CACHE_SECONDS:
            _current_weather_cache.pop(cache_key, None)
            return None

        return dict(weather)


def _write_cached_weather(cache_key: tuple[int, float, float], weather: dict[str, Any]) -> None:
    with _cache_lock:
        _current_weather_cache[cache_key] = (monotonic(), dict(weather))


def _parse_observed_at(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    return datetime.fromisoformat(value)


def _weather_code_label(value: object) -> str:
    try:
        code = int(value)
    except (TypeError, ValueError):
        return "Current conditions"
    if code == 0:
        return "Clear"
    if code in {1, 2, 3}:
        return "Partly cloudy"
    if code in {45, 48}:
        return "Fog"
    if code in {51, 53, 55, 56, 57}:
        return "Drizzle"
    if code in {61, 63, 65, 66, 67, 80, 81, 82}:
        return "Rain"
    if code in {71, 73, 75, 77, 85, 86}:
        return "Snow"
    if code in {95, 96, 99}:
        return "Thunderstorms"
    return "Current conditions"
