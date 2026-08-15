from typing import Any

import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


class GeocodingError(RuntimeError):
    pass


def search_locations(query: str, count: int = 8) -> list[dict[str, Any]]:
    if len(query.strip()) < 2:
        return []

    try:
        with httpx.Client(timeout=8) as client:
            response = client.get(
                GEOCODING_URL,
                params={
                    "name": query,
                    "count": count,
                    "language": "en",
                    "format": "json",
                },
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
    except httpx.HTTPError as exc:
        raise GeocodingError("Open-Meteo geocoding request failed") from exc

    return [_result_to_location(result) for result in payload.get("results", [])]


def _result_to_location(result: dict[str, Any]) -> dict[str, Any]:
    admin_parts = [
        result.get("admin1"),
        result.get("admin2"),
        result.get("country"),
    ]
    subtitle = ", ".join(str(part) for part in admin_parts if part)
    name = str(result.get("name", "Unknown location"))
    country_code = result.get("country_code")
    display_name = f"{name}, {country_code}" if country_code else name
    return {
        "id": result.get("id"),
        "name": display_name,
        "display_name": display_name,
        "subtitle": subtitle,
        "latitude": result.get("latitude"),
        "longitude": result.get("longitude"),
        "elevation_m": result.get("elevation"),
        "timezone": result.get("timezone") or "UTC",
        "population": result.get("population"),
        "country": result.get("country"),
        "country_code": country_code,
        "admin1": result.get("admin1"),
    }
