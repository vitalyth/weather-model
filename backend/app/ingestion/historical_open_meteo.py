from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from app.ingestion.providers import SourcePayload, WeatherProviderError
from app.models import Location

OPEN_METEO_HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_HISTORICAL_SOURCE = "Open-Meteo Historical"
OPEN_METEO_HISTORICAL_MODEL = "era5_reanalysis_daily"
OPEN_METEO_HISTORICAL_DAILY_VARIABLES = (
    "temperature_2m_max,temperature_2m_min,precipitation_sum"
)


class OpenMeteoHistoricalProvider:
    source = OPEN_METEO_HISTORICAL_SOURCE
    model = OPEN_METEO_HISTORICAL_MODEL
    source_url = OPEN_METEO_HISTORICAL_URL

    def __init__(self, timeout_seconds: float = 12, years_back: int = 5, window_days: int = 7) -> None:
        self.timeout_seconds = timeout_seconds
        self.years_back = years_back
        self.window_days = window_days

    def fetch_forecast(self, location: Location) -> SourcePayload:
        retrieved_at = datetime.now(UTC)
        target_date = retrieved_at.date()
        combined_daily: dict[str, list[Any]] = {
            "time": [],
            "temperature_2m_max": [],
            "temperature_2m_min": [],
            "precipitation_sum": [],
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                for year_offset in range(1, self.years_back + 1):
                    historical_date = _same_calendar_day(target_date, target_date.year - year_offset)
                    start_date = historical_date - timedelta(days=self.window_days)
                    end_date = historical_date + timedelta(days=self.window_days)
                    response = client.get(
                        self.source_url,
                        params=self._params(location, start_date, end_date),
                    )
                    response.raise_for_status()
                    payload: dict[str, Any] = response.json()
                    daily = payload.get("daily", {})
                    for key, values in combined_daily.items():
                        values.extend(daily.get(key, []))
        except httpx.HTTPError as exc:
            raise WeatherProviderError("Open-Meteo historical request failed") from exc

        return SourcePayload(
            source=self.source,
            model=self.model,
            source_url=self.source_url,
            retrieved_at=retrieved_at,
            payload={"daily": combined_daily},
        )

    def _params(self, location: Location, start_date: date, end_date: date) -> dict[str, str | float]:
        return {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "timezone": "UTC",
            "temperature_unit": "fahrenheit",
            "precipitation_unit": "inch",
            "daily": OPEN_METEO_HISTORICAL_DAILY_VARIABLES,
        }


def _same_calendar_day(target_date: date, year: int) -> date:
    try:
        return target_date.replace(year=year)
    except ValueError:
        return date(year, 2, 28)
