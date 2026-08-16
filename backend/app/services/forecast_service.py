import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import HORIZON_HOURS, REQUIRED_HORIZONS, PrecipitationType
from app.ingestion.historical_open_meteo import OpenMeteoHistoricalProvider
from app.ingestion.metar import MetarObservationProvider
from app.ingestion.nws import NWSForecastProvider
from app.ingestion.open_meteo import OpenMeteoForecastProvider, OpenMeteoModelProvider
from app.ingestion.providers import SourcePayload, WeatherProviderError
from app.models import ForecastSnapshot, Location, RawWeatherRecord
from app.schemas import ForecastPoint, ForecastSnapshotRead, LocationRead
from app.services.normalization_service import normalize_raw_records

FORECAST_POINTS_ADAPTER = TypeAdapter(list[ForecastPoint])
GENERATOR_KIND = "open_meteo_forecast_api"
MODEL_VERSION = "open-meteo-best-match"
FEATURE_VERSION = "phase-10-feature-contract-v0"
FORECAST_PROVIDER = OpenMeteoForecastProvider()
ADDITIONAL_INGESTION_PROVIDERS = [
    NWSForecastProvider(),
    MetarObservationProvider(),
    OpenMeteoModelProvider(source="Open-Meteo GFS", model="gfs_global"),
    OpenMeteoModelProvider(source="Open-Meteo ICON", model="icon_global"),
    OpenMeteoModelProvider(source="Open-Meteo ECMWF IFS", model="ecmwf_ifs025"),
    OpenMeteoHistoricalProvider(),
]
OPEN_METEO_HOURLY_UNITS = {
    "temperature_2m": "F",
    "relative_humidity_2m": "%",
    "dew_point_2m": "F",
    "apparent_temperature": "F",
    "precipitation_probability": "%",
    "precipitation": "in",
    "weather_code": "wmo_code",
    "pressure_msl": "hPa",
    "cloud_cover": "%",
    "visibility": "m",
    "wind_speed_10m": "mph",
    "wind_direction_10m": "degrees",
    "wind_gusts_10m": "mph",
}
OPEN_METEO_DAILY_UNITS = {
    "temperature_2m_max": "F",
    "temperature_2m_min": "F",
}
NWS_VARIABLE_UNITS = {
    "temperature": "F",
    "probability_of_precipitation": "%",
    "dewpoint": "unitCode",
    "relative_humidity": "%",
    "wind_speed": "text",
    "wind_direction": "text",
    "short_forecast": "text",
    "detailed_forecast": "text",
}
METAR_VARIABLE_UNITS = {
    "temp": "C",
    "dewp": "C",
    "wdir": "degrees",
    "wspd": "kt",
    "wgst": "kt",
    "visib": "SM",
    "altim": "hPa",
    "slp": "hPa",
    "presTend": "hPa",
    "rawOb": "text",
    "fltCat": "text",
    "cover": "text",
}
OPEN_METEO_HISTORICAL_DAILY_UNITS = {
    "temperature_2m_max": "F",
    "temperature_2m_min": "F",
    "precipitation_sum": "in",
}


ForecastProviderError = WeatherProviderError


def _round(value: float, digits: int = 1) -> float:
    return round(value, digits)


def _degrees(value: float) -> float:
    return round(value % 360, 0) % 360


def _horizon_label(horizon_hours: int) -> str:
    for horizon, hours in HORIZON_HOURS.items():
        if hours == horizon_hours:
            return horizon.value
    return f"{horizon_hours}h"


def _parse_open_meteo_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _value(hourly: dict[str, list[Any]], key: str, index: int, default: float = 0) -> float:
    value = hourly.get(key, [default])[index]
    return default if value is None else float(value)


def _find_hour_index(times: list[datetime], target: datetime) -> int:
    future_indexes = [index for index, value in enumerate(times) if value >= target]
    if future_indexes:
        return future_indexes[0]
    return len(times) - 1


def _daily_temperatures(payload: dict[str, Any], valid_at: datetime) -> tuple[float | None, float | None]:
    daily = payload.get("daily", {})
    dates = daily.get("time", [])
    if not dates:
        return None, None
    day = valid_at.date().isoformat()
    if day not in dates:
        return None, None
    index = dates.index(day)
    max_values = daily.get("temperature_2m_max", [])
    min_values = daily.get("temperature_2m_min", [])
    daily_max = max_values[index] if index < len(max_values) else None
    daily_min = min_values[index] if index < len(min_values) else None
    return (
        None if daily_max is None else _round(float(daily_max)),
        None if daily_min is None else _round(float(daily_min)),
    )


def _precipitation_type(
    weather_code: int, temperature_f: float, precipitation_probability: float, precipitation_amount: float
) -> PrecipitationType:
    if precipitation_probability < 20 and precipitation_amount <= 0:
        return PrecipitationType.none
    if weather_code in {56, 57, 66, 67}:
        return PrecipitationType.freezing_rain
    if weather_code in {71, 73, 75, 77, 85, 86}:
        return PrecipitationType.snow
    if 31 <= temperature_f <= 35 and precipitation_probability >= 30:
        return PrecipitationType.sleet
    if weather_code in {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}:
        return PrecipitationType.rain
    return PrecipitationType.none


def _precipitation_intensity(
    precipitation_type: PrecipitationType,
    precipitation_probability: float,
    precipitation_amount: float,
    weather_code: int,
) -> str:
    if precipitation_type == PrecipitationType.none:
        return "none"
    if weather_code in {65, 75, 82, 86, 95, 96, 99} or precipitation_amount >= 0.3:
        return "heavy"
    if precipitation_probability >= 50 or precipitation_amount >= 0.05:
        return "moderate"
    return "light"


def _precipitation_window(
    times: list[datetime], hourly: dict[str, list[Any]], index: int
) -> tuple[datetime | None, datetime | None]:
    probabilities = hourly.get("precipitation_probability", [])
    amounts = hourly.get("precipitation", [])
    if not probabilities or not amounts:
        return None, None
    if float(probabilities[index] or 0) < 30 and float(amounts[index] or 0) <= 0:
        return None, None

    start_index = index
    while start_index > 0:
        if float(probabilities[start_index - 1] or 0) < 30 and float(amounts[start_index - 1] or 0) <= 0:
            break
        start_index -= 1

    end_index = index
    while end_index + 1 < len(times):
        if float(probabilities[end_index + 1] or 0) < 30 and float(amounts[end_index + 1] or 0) <= 0:
            break
        end_index += 1

    return times[start_index], times[end_index] + timedelta(hours=1)


def _pressure_trend(hourly: dict[str, list[Any]], index: int) -> str:
    pressure = hourly.get("pressure_msl", [])
    if not pressure:
        return "steady"
    compare_index = index - 3 if index >= 3 else min(index + 3, len(pressure) - 1)
    delta = float(pressure[index] or 0) - float(pressure[compare_index] or 0)
    if compare_index > index:
        delta *= -1
    if delta <= -1.5:
        return "falling"
    if delta >= 1.5:
        return "rising"
    return "steady"


def _confidence(horizon_hours: int, precipitation_probability: float, wind_gust_mph: float) -> float:
    horizon_penalty = min(42, horizon_hours * 0.22)
    weather_penalty = 8 if precipitation_probability >= 70 else 0
    wind_penalty = 6 if wind_gust_mph >= 35 else 0
    return _round(max(35, 90 - horizon_penalty - weather_penalty - wind_penalty), 0)


def _open_meteo_point(
    payload: dict[str, Any],
    times: list[datetime],
    created_at: datetime,
    horizon_hours: int,
) -> ForecastPoint:
    hourly = payload["hourly"]
    target = created_at + timedelta(hours=horizon_hours)
    index = _find_hour_index(times, target)
    valid_at = times[index]
    temperature = _value(hourly, "temperature_2m", index)
    apparent_temperature = _value(hourly, "apparent_temperature", index, temperature)
    dew_point = _value(hourly, "dew_point_2m", index, temperature)
    precipitation_probability = _value(hourly, "precipitation_probability", index)
    precipitation_amount = _value(hourly, "precipitation", index)
    weather_code = int(_value(hourly, "weather_code", index))
    wind_speed = _value(hourly, "wind_speed_10m", index)
    wind_gust = _value(hourly, "wind_gusts_10m", index, wind_speed)
    visibility_mi = _value(hourly, "visibility", index) / 1609.344
    daily_max, daily_min = _daily_temperatures(payload, valid_at)
    precip_type = _precipitation_type(
        weather_code, temperature, precipitation_probability, precipitation_amount
    )
    precip_start, precip_end = _precipitation_window(times, hourly, index)

    return ForecastPoint(
        horizon=_horizon_label(horizon_hours),
        horizon_hours=horizon_hours,
        forecast_valid_at=valid_at,
        confidence_percent=_confidence(horizon_hours, precipitation_probability, wind_gust),
        temperature={
            "temperature_f": _round(temperature),
            "apparent_temperature_f": _round(apparent_temperature),
            "daily_max_f": daily_max,
            "daily_min_f": daily_min,
            "dew_point_f": _round(dew_point),
            "likely_low_f": _round(temperature - max(2.0, horizon_hours * 0.045)),
            "likely_high_f": _round(temperature + max(2.0, horizon_hours * 0.045)),
        },
        precipitation={
            "probability_percent": _round(precipitation_probability, 0),
            "amount_in": _round(precipitation_amount, 2),
            "precipitation_type": precip_type,
            "start_time": precip_start,
            "end_time": precip_end,
            "intensity": _precipitation_intensity(
                precip_type, precipitation_probability, precipitation_amount, weather_code
            ),
        },
        wind={
            "sustained_speed_mph": _round(wind_speed),
            "direction_degrees": _degrees(_value(hourly, "wind_direction_10m", index)),
            "max_gust_mph": _round(wind_gust),
        },
        atmosphere={
            "relative_humidity_percent": _round(_value(hourly, "relative_humidity_2m", index), 0),
            "pressure_hpa": _round(_value(hourly, "pressure_msl", index)),
            "pressure_trend": _pressure_trend(hourly, index),
            "cloud_cover_percent": _round(_value(hourly, "cloud_cover", index), 0),
            "visibility_mi": _round(max(0, visibility_mi)),
        },
        notable_weather={
            "thunderstorms_percent": _round(precipitation_probability if weather_code >= 95 else 0, 0),
            "heavy_rainfall_percent": _round(
                min(100, precipitation_probability) if precipitation_amount >= 0.25 else 0, 0
            ),
            "high_winds_percent": _round(min(100, max(0, (wind_gust - 30) * 4)), 0),
            "snow_percent": _round(precipitation_probability if precip_type == PrecipitationType.snow else 0, 0),
            "ice_percent": _round(
                precipitation_probability
                if precip_type in {PrecipitationType.freezing_rain, PrecipitationType.sleet}
                else 0,
                0,
            ),
            "fog_percent": _round(precipitation_probability if weather_code in {45, 48} or visibility_mi < 1.5 else 0, 0),
            "extreme_heat_percent": _round(min(100, max(0, (temperature - 95) * 10)), 0),
            "extreme_cold_percent": _round(min(100, max(0, (10 - temperature) * 10)), 0),
        },
    )


def fetch_forecast_source(location: Location) -> SourcePayload:
    return FORECAST_PROVIDER.fetch_forecast(location)


def fetch_additional_ingestion_sources(location: Location) -> list[SourcePayload]:
    source_payloads: list[SourcePayload] = []
    with ThreadPoolExecutor(max_workers=len(ADDITIONAL_INGESTION_PROVIDERS)) as executor:
        futures = [
            executor.submit(provider.fetch_forecast, location)
            for provider in ADDITIONAL_INGESTION_PROVIDERS
        ]
        for future in as_completed(futures):
            try:
                source_payloads.append(future.result())
            except WeatherProviderError:
                continue
    return source_payloads


def persist_source_raw_records(
    db: Session,
    location: Location,
    source_payload: SourcePayload,
) -> int:
    if source_payload.source == "National Weather Service":
        return persist_nws_raw_records(db, location, source_payload)
    if source_payload.source == "Aviation Weather Center METAR":
        return persist_metar_raw_records(db, location, source_payload)
    if source_payload.source == "Open-Meteo Historical":
        return persist_open_meteo_historical_raw_records(db, location, source_payload)
    return persist_open_meteo_raw_records(db, location, source_payload)


def persist_open_meteo_raw_records(
    db: Session,
    location: Location,
    source_payload: SourcePayload,
) -> int:
    payload = source_payload.payload
    hourly = payload.get("hourly", {})
    hourly_times = hourly.get("time", [])
    raw_metadata = json.dumps(
        {
            "source_url": source_payload.source_url,
            "timezone": payload.get("timezone"),
            "utc_offset_seconds": payload.get("utc_offset_seconds"),
            "forecast_initialization_note": "Open-Meteo best_match response does not expose a model run initialization time.",
        }
    )
    records: list[RawWeatherRecord] = []

    for index, timestamp in enumerate(hourly_times):
        valid_time = _parse_open_meteo_time(timestamp)
        for variable, values in hourly.items():
            if variable == "time" or index >= len(values):
                continue
            value = values[index]
            if value is None:
                continue
            records.append(
                RawWeatherRecord(
                    source=source_payload.source,
                    model=source_payload.model,
                    forecast_initialization_time=None,
                    forecast_valid_time=valid_time,
                    retrieval_time=source_payload.retrieved_at_utc(),
                    location_id=location.id,
                    location_name=location.name,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    elevation_m=location.elevation_m,
                    variable=variable,
                    value=str(value),
                    units=OPEN_METEO_HOURLY_UNITS.get(variable, "unknown"),
                    raw_metadata_json=raw_metadata,
                )
            )

    daily = payload.get("daily", {})
    daily_times = daily.get("time", [])
    for index, day in enumerate(daily_times):
        valid_time = _parse_open_meteo_time(f"{day}T00:00")
        for variable, values in daily.items():
            if variable == "time" or index >= len(values):
                continue
            value = values[index]
            if value is None:
                continue
            records.append(
                RawWeatherRecord(
                    source=source_payload.source,
                    model=source_payload.model,
                    forecast_initialization_time=None,
                    forecast_valid_time=valid_time,
                    retrieval_time=source_payload.retrieved_at_utc(),
                    location_id=location.id,
                    location_name=location.name,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    elevation_m=location.elevation_m,
                    variable=variable,
                    value=str(value),
                    units=OPEN_METEO_DAILY_UNITS.get(variable, "unknown"),
                    raw_metadata_json=raw_metadata,
                )
            )

    return _store_raw_records(db, records)


def _nws_value_and_unit(period: dict[str, Any], key: str, variable: str) -> tuple[str | None, str]:
    value = period.get(key)
    if value is None:
        return None, NWS_VARIABLE_UNITS.get(variable, "unknown")
    if isinstance(value, dict):
        unit = str(value.get("unitCode") or NWS_VARIABLE_UNITS.get(variable, "unknown"))
        inner_value = value.get("value")
        return (None if inner_value is None else str(inner_value), unit)
    return str(value), NWS_VARIABLE_UNITS.get(variable, "unknown")


def persist_nws_raw_records(
    db: Session,
    location: Location,
    source_payload: SourcePayload,
) -> int:
    periods = source_payload.payload.get("forecastHourly", {}).get("properties", {}).get("periods", [])
    raw_metadata = json.dumps(
        {
            "source_url": source_payload.source_url,
            "office": source_payload.payload.get("points", {}).get("properties", {}).get("cwa"),
            "grid_id": source_payload.payload.get("points", {}).get("properties", {}).get("gridId"),
            "grid_x": source_payload.payload.get("points", {}).get("properties", {}).get("gridX"),
            "grid_y": source_payload.payload.get("points", {}).get("properties", {}).get("gridY"),
        }
    )
    records: list[RawWeatherRecord] = []

    for period in periods:
        start_time = period.get("startTime")
        if not start_time:
            continue
        valid_time = _parse_open_meteo_time(start_time)
        for nws_key, variable in (
            ("temperature", "temperature"),
            ("probabilityOfPrecipitation", "probability_of_precipitation"),
            ("dewpoint", "dewpoint"),
            ("relativeHumidity", "relative_humidity"),
            ("windSpeed", "wind_speed"),
            ("windDirection", "wind_direction"),
            ("shortForecast", "short_forecast"),
            ("detailedForecast", "detailed_forecast"),
        ):
            value, unit = _nws_value_and_unit(period, nws_key, variable)
            if value is None:
                continue
            records.append(
                RawWeatherRecord(
                    source=source_payload.source,
                    model=source_payload.model,
                    forecast_initialization_time=None,
                    forecast_valid_time=valid_time,
                    retrieval_time=source_payload.retrieved_at_utc(),
                    location_id=location.id,
                    location_name=location.name,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    elevation_m=location.elevation_m,
                    variable=variable,
                    value=value,
                    units=unit,
                    raw_metadata_json=raw_metadata,
                )
            )

    return _store_raw_records(db, records)


def _parse_epoch_or_iso_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        return _parse_open_meteo_time(value)
    return None


def persist_metar_raw_records(
    db: Session,
    location: Location,
    source_payload: SourcePayload,
) -> int:
    records_payload = source_payload.payload.get("records", [])
    raw_metadata = json.dumps(
        {
            "source_url": source_payload.source_url,
            "station": source_payload.payload.get("station"),
            "station_distance_mi": source_payload.payload.get("station_distance_mi"),
        }
    )
    records: list[RawWeatherRecord] = []

    for metar in records_payload:
        valid_time = _parse_epoch_or_iso_time(metar.get("obsTime") or metar.get("reportTime"))
        if valid_time is None:
            continue
        for variable, unit in METAR_VARIABLE_UNITS.items():
            value = metar.get(variable)
            if value is None:
                continue
            records.append(
                RawWeatherRecord(
                    source=source_payload.source,
                    model=source_payload.model,
                    forecast_initialization_time=None,
                    forecast_valid_time=valid_time,
                    retrieval_time=source_payload.retrieved_at_utc(),
                    location_id=location.id,
                    location_name=location.name,
                    latitude=float(metar.get("lat") or location.latitude),
                    longitude=float(metar.get("lon") or location.longitude),
                    elevation_m=metar.get("elev") or location.elevation_m,
                    variable=variable,
                    value=str(value),
                    units=unit,
                    raw_metadata_json=raw_metadata,
                )
            )

    return _store_raw_records(db, records)


def persist_open_meteo_historical_raw_records(
    db: Session,
    location: Location,
    source_payload: SourcePayload,
) -> int:
    daily = source_payload.payload.get("daily", {})
    daily_times = daily.get("time", [])
    raw_metadata = json.dumps(
        {
            "source_url": source_payload.source_url,
            "purpose": "same-calendar-window historical climatology",
            "forecast_initialization_note": "Historical reanalysis records are observations/reanalysis, not forecast model runs.",
        }
    )
    records: list[RawWeatherRecord] = []

    for index, day in enumerate(daily_times):
        valid_time = _parse_open_meteo_time(f"{day}T00:00")
        for variable, values in daily.items():
            if variable == "time" or index >= len(values):
                continue
            value = values[index]
            if value is None:
                continue
            records.append(
                RawWeatherRecord(
                    source=source_payload.source,
                    model=source_payload.model,
                    forecast_initialization_time=None,
                    forecast_valid_time=valid_time,
                    retrieval_time=source_payload.retrieved_at_utc(),
                    location_id=location.id,
                    location_name=location.name,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    elevation_m=location.elevation_m,
                    variable=variable,
                    value=str(value),
                    units=OPEN_METEO_HISTORICAL_DAILY_UNITS.get(variable, "unknown"),
                    raw_metadata_json=raw_metadata,
                )
            )

    return _store_raw_records(db, records)


def _store_raw_records(db: Session, records: list[RawWeatherRecord]) -> int:
    if not records:
        return 0
    db.add_all(records)
    db.flush()
    normalize_raw_records(db, records)
    return len(records)


def build_forecast_points(
    location: Location, created_at: datetime, payload: dict[str, Any] | None = None
) -> tuple[list[ForecastPoint], list[ForecastPoint]]:
    if payload is None:
        payload = fetch_forecast_source(location).payload
    hourly = payload.get("hourly")
    if not hourly or not hourly.get("time"):
        raise ForecastProviderError("Open-Meteo response did not include hourly forecast data")

    times = [_parse_open_meteo_time(value) for value in hourly["time"]]
    required_points = [
        _open_meteo_point(payload, times, created_at, HORIZON_HOURS[horizon])
        for horizon in REQUIRED_HORIZONS
    ]
    hourly_points = [_open_meteo_point(payload, times, created_at, hour) for hour in range(1, 73)]
    return required_points, hourly_points


def create_forecast_snapshot(db: Session, location: Location) -> ForecastSnapshotRead:
    created_at = datetime.now(UTC)
    source_payload = fetch_forecast_source(location)
    raw_record_count = persist_source_raw_records(db, location, source_payload)
    for additional_source_payload in fetch_additional_ingestion_sources(location):
        raw_record_count += persist_source_raw_records(db, location, additional_source_payload)
    required_points, hourly_points = build_forecast_points(
        location, created_at, source_payload.payload
    )
    payload = {
        "points": [point.model_dump(mode="json") for point in required_points],
        "hourly_points": [point.model_dump(mode="json") for point in hourly_points],
        "raw_record_count": raw_record_count,
    }
    snapshot = ForecastSnapshot(
        location_id=location.id,
        forecast_created_at=created_at,
        data_cutoff_time=created_at,
        model_version=MODEL_VERSION,
        feature_version=FEATURE_VERSION,
        training_data_cutoff=None,
        generator_kind=GENERATOR_KIND,
        payload_json=json.dumps(payload),
    )
    db.add(snapshot)
    db.flush()
    from app.services.phase20_service import freeze_feature_snapshot

    freeze_feature_snapshot(db, snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot_to_schema(snapshot)


def get_forecast_snapshot(db: Session, snapshot_id: int) -> ForecastSnapshotRead | None:
    snapshot = db.scalar(select(ForecastSnapshot).where(ForecastSnapshot.id == snapshot_id))
    return snapshot_to_schema(snapshot) if snapshot else None


def list_forecast_snapshots(db: Session, location_id: int | None = None) -> list[ForecastSnapshotRead]:
    statement = select(ForecastSnapshot).order_by(ForecastSnapshot.forecast_created_at.desc())
    if location_id is not None:
        statement = statement.where(ForecastSnapshot.location_id == location_id)
    return [snapshot_to_schema(snapshot) for snapshot in db.scalars(statement).all()]


def snapshot_to_schema(snapshot: ForecastSnapshot) -> ForecastSnapshotRead:
    payload = json.loads(snapshot.payload_json)
    return ForecastSnapshotRead(
        id=snapshot.id,
        location=LocationRead.model_validate(snapshot.location),
        forecast_created_at=snapshot.forecast_created_at,
        data_cutoff_time=snapshot.data_cutoff_time,
        model_version=snapshot.model_version,
        feature_version=snapshot.feature_version,
        training_data_cutoff=snapshot.training_data_cutoff,
        generator_kind=snapshot.generator_kind,
        raw_record_count=int(payload.get("raw_record_count", 0)),
        points=FORECAST_POINTS_ADAPTER.validate_python(payload["points"]),
        hourly_points=FORECAST_POINTS_ADAPTER.validate_python(payload["hourly_points"]),
    )
