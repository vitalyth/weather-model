from datetime import datetime
from typing import Any

import httpx

from app.ingestion.open_meteo import OPEN_METEO_FORECAST_URL
from app.ingestion.providers import WeatherProviderError
from app.models import Location

CURRENT_VARIABLES = "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code"


def fetch_current_weather(location: Location) -> dict[str, Any]:
    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "current": CURRENT_VARIABLES,
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "auto",
    }
    try:
        with httpx.Client(timeout=8) as client:
            response = client.get(OPEN_METEO_FORECAST_URL, params=params)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
    except httpx.HTTPError as exc:
        raise WeatherProviderError("Open-Meteo current weather request failed") from exc

    current = payload.get("current") or {}
    return {
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
