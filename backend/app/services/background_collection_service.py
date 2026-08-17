import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import CollectionRun, Location
from app.services.completion_service import phase35_report
from app.services.current_state_service import build_current_state
from app.services.forecast_service import create_forecast_snapshot
from app.services.phase20_service import build_phase20_report, validate_matured_forecasts
from app.services.phase_layers_service import build_phase_layers
from app.services.report_cache_service import save_report

settings = get_settings()

_status_lock = Lock()
_status: dict[str, Any] = {
    "enabled": settings.background_collection_enabled,
    "running": False,
    "interval_seconds": settings.background_collection_interval_minutes * 60,
    "last_started_at": None,
    "last_finished_at": None,
    "last_success_at": None,
    "last_error": None,
    "last_location_count": 0,
    "last_forecast_snapshot_count": 0,
    "last_validation_record_count": 0,
    "last_cached_report_count": 0,
    "last_errors": [],
}


def background_collection_status(db: Session | None = None) -> dict[str, Any]:
    if db is not None:
        persisted_status = _latest_persisted_status(db)
        if persisted_status is not None:
            return persisted_status
    with _status_lock:
        return deepcopy(_status)


def _update_status(**updates: Any) -> None:
    with _status_lock:
        _status.update(updates)


async def run_background_collection_loop() -> None:
    if not settings.background_collection_enabled:
        return

    await asyncio.sleep(settings.background_collection_startup_delay_seconds)
    while True:
        await asyncio.to_thread(run_collection_cycle)
        await asyncio.sleep(settings.background_collection_interval_minutes * 60)


def run_collection_cycle() -> dict[str, Any]:
    started_at = datetime.now(UTC)
    run_id = _persist_started_run(started_at)
    _update_status(
        running=True,
        last_started_at=started_at,
        last_error=None,
        last_errors=[],
        last_forecast_snapshot_count=0,
        last_validation_record_count=0,
        last_cached_report_count=0,
    )

    forecast_count = 0
    validation_count = 0
    cached_report_count = 0
    errors: list[str] = []

    with SessionLocal() as db:
        locations = list(db.scalars(select(Location).order_by(Location.name)).all())
        for location in locations:
            try:
                create_forecast_snapshot(db, location)
                forecast_count += 1
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                errors.append(f"{location.name}: forecast collection failed: {exc}")

            try:
                validation_count += validate_matured_forecasts(db, location)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                errors.append(f"{location.name}: validation failed: {exc}")

            try:
                cached_report_count += _cache_location_reports(db, location)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                errors.append(f"{location.name}: report cache failed: {exc}")

    finished_at = datetime.now(UTC)
    last_error = "; ".join(errors[:3]) if errors else None
    _update_status(
        running=False,
        last_finished_at=finished_at,
        last_success_at=None if errors else finished_at,
        last_error=last_error,
        last_location_count=len(locations),
        last_forecast_snapshot_count=forecast_count,
        last_validation_record_count=validation_count,
        last_cached_report_count=cached_report_count,
        last_errors=errors[:10],
    )
    _persist_finished_run(
        run_id=run_id,
        finished_at=finished_at,
        location_count=len(locations),
        forecast_count=forecast_count,
        validation_count=validation_count,
        cached_report_count=cached_report_count,
        errors=errors,
    )
    return background_collection_status()


def _cache_location_reports(db: Session, location: Location) -> int:
    reports = [
        ("current_state", build_current_state(db, location)),
        ("phase_layers", build_phase_layers(db, location)),
        ("validation_report", build_phase20_report(db, location)),
        ("system_report", phase35_report(db, location)),
    ]
    for report_kind, report in reports:
        save_report(db, location.id, report_kind, report)
    db.commit()
    return len(reports)


def _persist_started_run(started_at: datetime) -> int:
    with SessionLocal() as db:
        collection_run = CollectionRun(started_at=started_at, finished_at=None)
        db.add(collection_run)
        db.commit()
        db.refresh(collection_run)
        return collection_run.id


def _persist_finished_run(
    run_id: int,
    finished_at: datetime,
    location_count: int,
    forecast_count: int,
    validation_count: int,
    cached_report_count: int,
    errors: list[str],
) -> None:
    with SessionLocal() as db:
        collection_run = db.get(CollectionRun, run_id)
        if collection_run is None:
            return
        collection_run.finished_at = finished_at
        collection_run.success_at = None if errors else finished_at
        collection_run.location_count = location_count
        collection_run.forecast_snapshot_count = forecast_count
        collection_run.validation_record_count = validation_count
        collection_run.cached_report_count = cached_report_count
        collection_run.error = "; ".join(errors[:3]) if errors else None
        collection_run.errors_json = json.dumps(errors[:10])
        db.commit()


def _latest_persisted_status(db: Session) -> dict[str, Any] | None:
    collection_run = db.scalar(
        select(CollectionRun).order_by(CollectionRun.started_at.desc(), CollectionRun.id.desc()).limit(1)
    )
    if collection_run is None:
        return None
    errors = json.loads(collection_run.errors_json or "[]")
    return {
        "enabled": True,
        "running": collection_run.finished_at is None,
        "interval_seconds": settings.background_collection_interval_minutes * 60,
        "last_started_at": collection_run.started_at,
        "last_finished_at": collection_run.finished_at,
        "last_success_at": collection_run.success_at,
        "last_error": collection_run.error,
        "last_location_count": collection_run.location_count,
        "last_forecast_snapshot_count": collection_run.forecast_snapshot_count,
        "last_validation_record_count": collection_run.validation_record_count,
        "last_cached_report_count": collection_run.cached_report_count,
        "last_errors": errors,
    }
