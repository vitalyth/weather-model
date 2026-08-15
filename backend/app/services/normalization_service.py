import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NormalizedWeatherRecord, RawWeatherRecord

VARIABLE_MAP = {
    "temperature_2m": "temperature",
    "temperature_2m_max": "daily_max_temperature",
    "temperature_2m_min": "daily_min_temperature",
    "temp": "temperature",
    "temperature": "temperature",
    "apparent_temperature": "apparent_temperature",
    "dew_point_2m": "dew_point",
    "dewp": "dew_point",
    "dewpoint": "dew_point",
    "relative_humidity_2m": "relative_humidity",
    "relative_humidity": "relative_humidity",
    "precipitation_probability": "precipitation_probability",
    "probability_of_precipitation": "precipitation_probability",
    "precipitation": "precipitation_amount",
    "precipitation_sum": "precipitation_amount",
    "pressure_msl": "pressure",
    "altim": "pressure",
    "slp": "pressure",
    "presTend": "pressure_tendency",
    "cloud_cover": "cloud_cover",
    "visibility": "visibility",
    "visib": "visibility",
    "wind_speed_10m": "wind_speed",
    "wspd": "wind_speed",
    "wind_gusts_10m": "wind_gust",
    "wgst": "wind_gust",
    "wind_direction_10m": "wind_direction",
    "wdir": "wind_direction",
    "wind_direction": "wind_direction_text",
    "weather_code": "weather_code",
    "rawOb": "raw_observation",
    "fltCat": "flight_category",
    "cover": "cloud_cover_text",
    "short_forecast": "short_forecast",
    "detailed_forecast": "detailed_forecast",
}

EXPECTED_RANGES = {
    "temperature": (-130, 140),
    "apparent_temperature": (-150, 160),
    "daily_max_temperature": (-130, 140),
    "daily_min_temperature": (-130, 140),
    "dew_point": (-130, 100),
    "relative_humidity": (0, 100),
    "precipitation_probability": (0, 100),
    "precipitation_amount": (0, 50),
    "pressure": (850, 1100),
    "pressure_tendency": (-50, 50),
    "cloud_cover": (0, 100),
    "visibility": (0, 100),
    "wind_speed": (0, 250),
    "wind_gust": (0, 300),
    "wind_direction": (0, 360),
    "weather_code": (0, 999),
}


@dataclass(frozen=True)
class NormalizedValue:
    variable: str
    value: float | None
    text: str | None
    units: str
    status: str
    score: float
    reason: str


def normalize_raw_records(db: Session, raw_records: list[RawWeatherRecord]) -> int:
    normalized_records = [normalize_raw_record(raw_record) for raw_record in raw_records]
    db.add_all(
        NormalizedWeatherRecord(
            raw_record_id=raw_record.id,
            source=raw_record.source,
            model=raw_record.model,
            location_id=raw_record.location_id,
            valid_time=raw_record.forecast_valid_time,
            retrieved_at=raw_record.retrieval_time,
            raw_variable=raw_record.variable,
            normalized_variable=normalized.variable,
            raw_value=raw_record.value,
            normalized_value=normalized.value,
            normalized_text=normalized.text,
            normalized_units=normalized.units,
            quality_status=normalized.status,
            quality_score=normalized.score,
            quality_reason=normalized.reason,
        )
        for raw_record, normalized in zip(raw_records, normalized_records, strict=True)
    )
    return len(normalized_records)


def normalize_raw_record(raw_record: RawWeatherRecord) -> NormalizedValue:
    variable = VARIABLE_MAP.get(raw_record.variable, raw_record.variable)
    numeric_value = _parse_numeric_value(raw_record.value)
    units = _normalize_units(raw_record.units)

    if numeric_value is None:
        return NormalizedValue(
            variable=variable,
            value=None,
            text=raw_record.value,
            units="text",
            status="accepted",
            score=0.8,
            reason="Text value preserved without numeric conversion.",
        )

    converted_value, converted_units = _convert_value(numeric_value, raw_record.units, variable)
    status, score, reason = _quality(variable, converted_value)
    return NormalizedValue(
        variable=variable,
        value=round(converted_value, 3),
        text=None,
        units=converted_units or units,
        status=status,
        score=score,
        reason=reason,
    )


def list_normalized_records(
    db: Session,
    location_id: int | None = None,
    source: str | None = None,
    quality_status: str | None = None,
    limit: int = 100,
) -> list[NormalizedWeatherRecord]:
    statement = select(NormalizedWeatherRecord).order_by(NormalizedWeatherRecord.retrieved_at.desc())
    if location_id is not None:
        statement = statement.where(NormalizedWeatherRecord.location_id == location_id)
    if source is not None:
        statement = statement.where(NormalizedWeatherRecord.source == source)
    if quality_status is not None:
        statement = statement.where(NormalizedWeatherRecord.quality_status == quality_status)
    return list(db.scalars(statement.limit(limit)).all())


def _parse_numeric_value(value: str) -> float | None:
    value = value.removesuffix("+")
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    if not match:
        return None
    return float(match.group(0))


def _normalize_units(units: str) -> str:
    if units in {"F", "C", "%", "in", "hPa", "degrees", "mph", "mi"}:
        return units
    if units == "kt":
        return "mph"
    if units == "m":
        return "mi"
    if units == "SM":
        return "mi"
    if units == "wmoUnit:degC":
        return "F"
    if units == "wmoUnit:percent":
        return "%"
    return units


def _convert_value(value: float, units: str, variable: str) -> tuple[float, str]:
    if units in {"C", "wmoUnit:degC"}:
        return value * 9 / 5 + 32, "F"
    if units == "kt":
        return value * 1.15078, "mph"
    if units == "m":
        return value / 1609.344, "mi"
    if units == "SM":
        return value, "mi"
    if units == "wmoUnit:percent":
        return value, "%"
    if variable == "pressure" and units == "hPa":
        return value, "hPa"
    return value, _normalize_units(units)


def _quality(variable: str, value: float) -> tuple[str, float, str]:
    expected_range = EXPECTED_RANGES.get(variable)
    if expected_range is None:
        return "accepted", 0.9, "No numeric range rule exists yet; value preserved."

    low, high = expected_range
    if low <= value <= high:
        return "accepted", 1.0, "Value is within expected physical range."

    margin = max((high - low) * 0.1, 1)
    if low - margin <= value <= high + margin:
        return "suspicious", 0.45, "Value is outside expected range but near the boundary."

    return "rejected", 0.0, "Value is physically implausible for this variable."
