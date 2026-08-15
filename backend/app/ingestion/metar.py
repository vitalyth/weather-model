from dataclasses import dataclass
from datetime import UTC, datetime
from math import asin, cos, radians, sin, sqrt
from typing import Any

import httpx

from app.ingestion.providers import SourcePayload, WeatherProviderError
from app.models import Location

AVIATION_WEATHER_API_ROOT = "https://aviationweather.gov/api/data"
METAR_SOURCE = "Aviation Weather Center METAR"
METAR_MODEL = "airport_observation"
AVIATION_WEATHER_USER_AGENT = "weather-model/0.1 contact@example.com"


@dataclass(frozen=True)
class MetarStation:
    icao_id: str
    latitude: float
    longitude: float


METAR_STATIONS = [
    MetarStation("KJFK", 40.6392, -73.7639),
    MetarStation("KLGA", 40.7772, -73.8726),
    MetarStation("KEWR", 40.6825, -74.1694),
    MetarStation("KBOS", 42.3606, -71.0096),
    MetarStation("KORD", 41.9786, -87.9048),
    MetarStation("KMDW", 41.7868, -87.7522),
    MetarStation("KATL", 33.6367, -84.4281),
    MetarStation("KDFW", 32.8972, -97.0377),
    MetarStation("KDEN", 39.8561, -104.6737),
    MetarStation("KLAX", 33.9425, -118.4081),
    MetarStation("KSFO", 37.6190, -122.3749),
    MetarStation("KSEA", 47.4502, -122.3088),
    MetarStation("KMIA", 25.7933, -80.2906),
    MetarStation("KIAD", 38.9445, -77.4558),
    MetarStation("KDCA", 38.8521, -77.0377),
    MetarStation("KPHX", 33.4278, -112.0035),
    MetarStation("KMSP", 44.8848, -93.2223),
    MetarStation("KDTW", 42.2124, -83.3534),
    MetarStation("KPHL", 39.8744, -75.2424),
    MetarStation("KHOU", 29.6454, -95.2789),
]


class MetarObservationProvider:
    source = METAR_SOURCE
    model = METAR_MODEL
    source_url = f"{AVIATION_WEATHER_API_ROOT}/metar"

    def __init__(self, timeout_seconds: float = 12, max_station_distance_mi: float = 80) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_station_distance_mi = max_station_distance_mi

    def fetch_forecast(self, location: Location) -> SourcePayload:
        station, distance_mi = self._nearest_station(location)
        if station is None:
            return SourcePayload(
                source=self.source,
                model=self.model,
                source_url=self.source_url,
                retrieved_at=datetime.now(UTC),
                payload={"records": [], "station": None},
            )

        params = {
            "ids": station.icao_id,
            "format": "json",
            "hours": 2,
        }
        headers = {
            "Accept": "application/json",
            "User-Agent": AVIATION_WEATHER_USER_AGENT,
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds, headers=headers) as client:
                response = client.get(self.source_url, params=params)
                if response.status_code == 204:
                    records: list[dict[str, Any]] = []
                else:
                    response.raise_for_status()
                    records = response.json()
        except httpx.HTTPError as exc:
            raise WeatherProviderError("METAR observation request failed") from exc

        return SourcePayload(
            source=self.source,
            model=self.model,
            source_url=self.source_url,
            retrieved_at=datetime.now(UTC),
            payload={
                "records": records,
                "station": station.icao_id,
                "station_distance_mi": round(distance_mi, 2),
            },
        )

    def _nearest_station(self, location: Location) -> tuple[MetarStation | None, float]:
        nearest = min(
            METAR_STATIONS,
            key=lambda station: _distance_mi(
                location.latitude,
                location.longitude,
                station.latitude,
                station.longitude,
            ),
        )
        distance_mi = _distance_mi(
            location.latitude,
            location.longitude,
            nearest.latitude,
            nearest.longitude,
        )
        if distance_mi > self.max_station_distance_mi:
            return None, distance_mi
        return nearest, distance_mi


def _distance_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_mi = 3958.8
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    return 2 * earth_radius_mi * asin(sqrt(a))
