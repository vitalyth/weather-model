from datetime import UTC, datetime
from typing import Any

import httpx

from app.ingestion.providers import SourcePayload, WeatherProviderError
from app.models import Location

NWS_API_ROOT = "https://api.weather.gov"
NWS_SOURCE = "National Weather Service"
NWS_MODEL = "official_hourly_forecast"
NWS_USER_AGENT = "weather-model/0.1 contact@example.com"


class NWSForecastProvider:
    source = NWS_SOURCE
    model = NWS_MODEL
    source_url = NWS_API_ROOT

    def __init__(self, timeout_seconds: float = 12) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_forecast(self, location: Location) -> SourcePayload:
        headers = {
            "Accept": "application/geo+json",
            "User-Agent": NWS_USER_AGENT,
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds, headers=headers) as client:
                points_response = client.get(
                    f"{self.source_url}/points/{location.latitude:.4f},{location.longitude:.4f}"
                )
                points_response.raise_for_status()
                points_payload: dict[str, Any] = points_response.json()
                hourly_url = points_payload["properties"]["forecastHourly"]

                hourly_response = client.get(hourly_url)
                hourly_response.raise_for_status()
                hourly_payload: dict[str, Any] = hourly_response.json()
        except (KeyError, httpx.HTTPError) as exc:
            raise WeatherProviderError("NWS forecast request failed") from exc

        return SourcePayload(
            source=self.source,
            model=self.model,
            source_url=hourly_url,
            retrieved_at=datetime.now(UTC),
            payload={
                "points": points_payload,
                "forecastHourly": hourly_payload,
            },
        )
