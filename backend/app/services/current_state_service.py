from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Location, NormalizedWeatherRecord
from app.schemas import CurrentStateRead, CurrentStateTrends, CurrentStateValue, LocationRead

SOURCE_PRIORITY = {
    "Aviation Weather Center METAR": 0,
    "National Weather Service": 1,
    "Open-Meteo": 2,
}

CURRENT_VARIABLES = {
    "temperature",
    "dew_point",
    "relative_humidity",
    "pressure",
    "visibility",
    "wind_speed",
    "wind_gust",
    "wind_direction",
    "cloud_cover",
    "cloud_cover_text",
    "precipitation_amount",
    "precipitation_probability",
}


def build_current_state(db: Session, location: Location) -> CurrentStateRead:
    records = list(
        db.scalars(
            select(NormalizedWeatherRecord)
            .where(NormalizedWeatherRecord.location_id == location.id)
            .where(NormalizedWeatherRecord.quality_status != "rejected")
            .order_by(NormalizedWeatherRecord.valid_time.desc())
        ).all()
    )
    current_records = _select_current_records(records)
    values = {
        variable: CurrentStateValue(
            value=record.normalized_value,
            text=record.normalized_text,
            units=record.normalized_units,
            source=record.source,
            valid_time=record.valid_time,
            quality_score=record.quality_score,
        )
        for variable, record in current_records.items()
    }
    data_cutoff = max((record.retrieved_at for record in records), default=None)
    return CurrentStateRead(
        location=LocationRead.model_validate(location),
        generated_at=datetime.now(UTC),
        data_cutoff_time=data_cutoff,
        values=values,
        trends=_build_trends(records, current_records),
        evidence_record_count=len(records),
    )


def _select_current_records(
    records: list[NormalizedWeatherRecord],
) -> dict[str, NormalizedWeatherRecord]:
    candidates: dict[str, list[NormalizedWeatherRecord]] = {}
    for record in records:
        if record.normalized_variable not in CURRENT_VARIABLES:
            continue
        candidates.setdefault(record.normalized_variable, []).append(record)

    selected: dict[str, NormalizedWeatherRecord] = {}
    for variable, variable_records in candidates.items():
        selected[variable] = min(
            variable_records,
            key=lambda record: (
                SOURCE_PRIORITY.get(record.source, 99),
                -record.valid_time.timestamp(),
                -record.quality_score,
            ),
        )
    return selected


def _build_trends(
    records: list[NormalizedWeatherRecord],
    current_records: dict[str, NormalizedWeatherRecord],
) -> CurrentStateTrends:
    return CurrentStateTrends(
        temperature_change_1h_f=_change(records, current_records, "temperature", hours=1),
        temperature_change_3h_f=_change(records, current_records, "temperature", hours=3),
        temperature_change_6h_f=_change(records, current_records, "temperature", hours=6),
        pressure_change_3h_hpa=_change(records, current_records, "pressure", hours=3),
        pressure_change_6h_hpa=_change(records, current_records, "pressure", hours=6),
        dewpoint_change_f=_change(records, current_records, "dew_point", hours=3),
        humidity_change_percent=_change(records, current_records, "relative_humidity", hours=3),
        wind_shift_degrees=_wind_shift(records, current_records, hours=1),
        precipitation_recent_in=_recent_precipitation(records, hours=6),
        cloud_trend=_cloud_trend(records, current_records),
    )


def _change(
    records: list[NormalizedWeatherRecord],
    current_records: dict[str, NormalizedWeatherRecord],
    variable: str,
    hours: int,
) -> float | None:
    current = current_records.get(variable)
    if current is None or current.normalized_value is None:
        return None

    target_time = current.valid_time - timedelta(hours=hours)
    prior = _nearest_prior(records, variable, target_time, source=current.source)
    if prior is None or prior.normalized_value is None:
        return None
    return round(current.normalized_value - prior.normalized_value, 3)


def _nearest_prior(
    records: list[NormalizedWeatherRecord],
    variable: str,
    target_time: datetime,
    source: str | None = None,
) -> NormalizedWeatherRecord | None:
    candidates = [
        record
        for record in records
        if record.normalized_variable == variable
        and record.normalized_value is not None
        and record.valid_time <= target_time
        and (source is None or record.source == source)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda record: record.valid_time)


def _wind_shift(
    records: list[NormalizedWeatherRecord],
    current_records: dict[str, NormalizedWeatherRecord],
    hours: int,
) -> float | None:
    current = current_records.get("wind_direction")
    if current is None or current.normalized_value is None:
        return None
    prior = _nearest_prior(
        records, "wind_direction", current.valid_time - timedelta(hours=hours), source=current.source
    )
    if prior is None or prior.normalized_value is None:
        return None
    diff = abs((current.normalized_value - prior.normalized_value + 180) % 360 - 180)
    return round(diff, 3)


def _recent_precipitation(records: list[NormalizedWeatherRecord], hours: int) -> float | None:
    precip_records = [
        record
        for record in records
        if record.normalized_variable == "precipitation_amount" and record.normalized_value is not None
    ]
    if not precip_records:
        return None
    latest_time = max(record.valid_time for record in precip_records)
    cutoff = latest_time - timedelta(hours=hours)
    total = sum(
        record.normalized_value
        for record in precip_records
        if record.valid_time >= cutoff and record.normalized_value is not None
    )
    return round(total, 3)


def _cloud_trend(
    records: list[NormalizedWeatherRecord],
    current_records: dict[str, NormalizedWeatherRecord],
) -> str | None:
    current = current_records.get("cloud_cover")
    if current is None or current.normalized_value is None:
        return None
    prior = _nearest_prior(records, "cloud_cover", current.valid_time - timedelta(hours=3), source=current.source)
    if prior is None or prior.normalized_value is None:
        return None
    diff = current.normalized_value - prior.normalized_value
    if diff >= 15:
        return "increasing"
    if diff <= -15:
        return "decreasing"
    return "steady"
