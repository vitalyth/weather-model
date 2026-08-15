from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.models import Location


class WeatherProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourcePayload:
    source: str
    model: str
    source_url: str
    retrieved_at: datetime
    payload: dict[str, Any]

    def retrieved_at_utc(self) -> datetime:
        if self.retrieved_at.tzinfo is None:
            return self.retrieved_at.replace(tzinfo=UTC)
        return self.retrieved_at.astimezone(UTC)


class ForecastProvider(Protocol):
    source: str
    model: str
    source_url: str

    def fetch_forecast(self, location: Location) -> SourcePayload:
        """Fetch forecast data for a configured location."""
