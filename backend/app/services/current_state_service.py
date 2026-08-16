from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Location, NormalizedWeatherRecord
from app.schemas import CurrentStateRead, CurrentStateTrends, CurrentStateValue, LocationRead

SOURCE_PRIORITY = {
    "Aviation Weather Center METAR": 0,
    "National Weather Service": 1,
    "Open-Meteo": 2,
    "Open-Meteo ECMWF IFS": 3,
    "Open-Meteo ICON": 4,
    "Open-Meteo GFS": 5,
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
    current_records = _select_current_records(db, location.id)
    data_cutoff = db.scalar(
        select(func.max(NormalizedWeatherRecord.retrieved_at))
        .where(NormalizedWeatherRecord.location_id == location.id)
        .where(NormalizedWeatherRecord.quality_status != "rejected")
    )
    evidence_record_count = int(
        db.scalar(
            select(func.count())
            .select_from(NormalizedWeatherRecord)
            .where(NormalizedWeatherRecord.location_id == location.id)
            .where(NormalizedWeatherRecord.quality_status != "rejected")
        )
        or 0
    )
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
    return CurrentStateRead(
        location=LocationRead.model_validate(location),
        generated_at=datetime.now(UTC),
        data_cutoff_time=data_cutoff,
        values=values,
        trends=_build_trends(db, location.id, current_records),
        evidence_record_count=evidence_record_count,
    )


def _select_current_records(
    db: Session,
    location_id: int,
) -> dict[str, NormalizedWeatherRecord]:
    selected: dict[str, NormalizedWeatherRecord] = {}
    source_priority = case(
        *[
            (NormalizedWeatherRecord.source == source, priority)
            for source, priority in SOURCE_PRIORITY.items()
        ],
        else_=99,
    )
    for variable in CURRENT_VARIABLES:
        record = db.scalar(
            select(NormalizedWeatherRecord)
            .where(NormalizedWeatherRecord.location_id == location_id)
            .where(NormalizedWeatherRecord.quality_status != "rejected")
            .where(NormalizedWeatherRecord.normalized_variable == variable)
            .order_by(
                source_priority,
                NormalizedWeatherRecord.valid_time.desc(),
                NormalizedWeatherRecord.quality_score.desc(),
            )
            .limit(1)
        )
        if record is not None:
            selected[variable] = record
    return selected


def _build_trends(
    db: Session,
    location_id: int,
    current_records: dict[str, NormalizedWeatherRecord],
) -> CurrentStateTrends:
    return CurrentStateTrends(
        temperature_change_1h_f=_change(db, location_id, current_records, "temperature", hours=1),
        temperature_change_3h_f=_change(db, location_id, current_records, "temperature", hours=3),
        temperature_change_6h_f=_change(db, location_id, current_records, "temperature", hours=6),
        pressure_change_3h_hpa=_change(db, location_id, current_records, "pressure", hours=3),
        pressure_change_6h_hpa=_change(db, location_id, current_records, "pressure", hours=6),
        dewpoint_change_f=_change(db, location_id, current_records, "dew_point", hours=3),
        humidity_change_percent=_change(db, location_id, current_records, "relative_humidity", hours=3),
        wind_shift_degrees=_wind_shift(db, location_id, current_records, hours=1),
        precipitation_recent_in=_recent_precipitation(db, location_id, hours=6),
        cloud_trend=_cloud_trend(db, location_id, current_records),
    )


def _change(
    db: Session,
    location_id: int,
    current_records: dict[str, NormalizedWeatherRecord],
    variable: str,
    hours: int,
) -> float | None:
    current = current_records.get(variable)
    if current is None or current.normalized_value is None:
        return None

    target_time = current.valid_time - timedelta(hours=hours)
    prior = _nearest_prior(db, location_id, variable, target_time, source=current.source)
    if prior is None or prior.normalized_value is None:
        return None
    return round(current.normalized_value - prior.normalized_value, 3)


def _nearest_prior(
    db: Session,
    location_id: int,
    variable: str,
    target_time: datetime,
    source: str | None = None,
) -> NormalizedWeatherRecord | None:
    statement = (
        select(NormalizedWeatherRecord)
        .where(NormalizedWeatherRecord.location_id == location_id)
        .where(NormalizedWeatherRecord.quality_status != "rejected")
        .where(NormalizedWeatherRecord.normalized_variable == variable)
        .where(NormalizedWeatherRecord.normalized_value.is_not(None))
        .where(NormalizedWeatherRecord.valid_time <= target_time)
        .order_by(NormalizedWeatherRecord.valid_time.desc())
        .limit(1)
    )
    if source is not None:
        statement = statement.where(NormalizedWeatherRecord.source == source)
    return db.scalar(statement)


def _wind_shift(
    db: Session,
    location_id: int,
    current_records: dict[str, NormalizedWeatherRecord],
    hours: int,
) -> float | None:
    current = current_records.get("wind_direction")
    if current is None or current.normalized_value is None:
        return None
    prior = _nearest_prior(
        db,
        location_id,
        "wind_direction",
        current.valid_time - timedelta(hours=hours),
        source=current.source,
    )
    if prior is None or prior.normalized_value is None:
        return None
    diff = abs((current.normalized_value - prior.normalized_value + 180) % 360 - 180)
    return round(diff, 3)


def _recent_precipitation(db: Session, location_id: int, hours: int) -> float | None:
    latest_time = db.scalar(
        select(func.max(NormalizedWeatherRecord.valid_time))
        .where(NormalizedWeatherRecord.location_id == location_id)
        .where(NormalizedWeatherRecord.quality_status != "rejected")
        .where(NormalizedWeatherRecord.normalized_variable == "precipitation_amount")
        .where(NormalizedWeatherRecord.normalized_value.is_not(None))
    )
    if latest_time is None:
        return None
    cutoff = latest_time - timedelta(hours=hours)
    total = db.scalar(
        select(func.sum(NormalizedWeatherRecord.normalized_value))
        .where(NormalizedWeatherRecord.location_id == location_id)
        .where(NormalizedWeatherRecord.quality_status != "rejected")
        .where(NormalizedWeatherRecord.normalized_variable == "precipitation_amount")
        .where(NormalizedWeatherRecord.normalized_value.is_not(None))
        .where(NormalizedWeatherRecord.valid_time >= cutoff)
    )
    return None if total is None else round(float(total), 3)


def _cloud_trend(
    db: Session,
    location_id: int,
    current_records: dict[str, NormalizedWeatherRecord],
) -> str | None:
    current = current_records.get("cloud_cover")
    if current is None or current.normalized_value is None:
        return None
    prior = _nearest_prior(
        db,
        location_id,
        "cloud_cover",
        current.valid_time - timedelta(hours=3),
        source=current.source,
    )
    if prior is None or prior.normalized_value is None:
        return None
    diff = current.normalized_value - prior.normalized_value
    if diff >= 15:
        return "increasing"
    if diff <= -15:
        return "decreasing"
    return "steady"
