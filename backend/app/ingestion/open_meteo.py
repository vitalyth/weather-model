from datetime import UTC, datetime
from typing import Any

import httpx

from app.ingestion.providers import SourcePayload, WeatherProviderError
from app.models import Location

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_SOURCE = "Open-Meteo"
OPEN_METEO_MODEL = "best_match"
OPEN_METEO_MODEL_PROVIDER_SOURCE_PREFIX = "Open-Meteo Model"
OPEN_METEO_HOURLY_VARIABLES = (
    "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,"
    "precipitation_probability,precipitation,weather_code,pressure_msl,cloud_cover,"
    "visibility,wind_speed_10m,wind_direction_10m,wind_gusts_10m"
)
OPEN_METEO_DAILY_VARIABLES = "temperature_2m_max,temperature_2m_min"


class OpenMeteoForecastProvider:
    source_url = OPEN_METEO_FORECAST_URL

    def __init__(
        self,
        timeout_seconds: float = 12,
        model: str = OPEN_METEO_MODEL,
        source: str = OPEN_METEO_SOURCE,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.model = model
        self.source = source

    def fetch_forecast(self, location: Location) -> SourcePayload:
        params = self._params(location)
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(self.source_url, params=params)
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
        except httpx.HTTPError as exc:
            raise WeatherProviderError("Open-Meteo forecast request failed") from exc

        return SourcePayload(
            source=self.source,
            model=self.model,
            source_url=self.source_url,
            retrieved_at=datetime.now(UTC),
            payload=payload,
        )

    def _params(self, location: Location) -> dict[str, str | float | int]:
        params: dict[str, str | float | int] = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "forecast_days": 8,
            "timezone": "UTC",
            "timeformat": "iso8601",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "hourly": OPEN_METEO_HOURLY_VARIABLES,
            "daily": OPEN_METEO_DAILY_VARIABLES,
        }
        if self.model != OPEN_METEO_MODEL:
            params["models"] = self.model
        return params


class OpenMeteoModelProvider(OpenMeteoForecastProvider):
    def __init__(self, source: str, model: str, timeout_seconds: float = 8) -> None:
        super().__init__(timeout_seconds=timeout_seconds, model=model, source=source)
