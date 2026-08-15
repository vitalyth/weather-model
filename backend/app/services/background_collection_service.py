import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import Location
from app.services.forecast_service import create_forecast_snapshot
from app.services.phase20_service import validate_matured_forecasts

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
    "last_errors": [],
}


def background_collection_status() -> dict[str, Any]:
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
    _update_status(
        running=True,
        last_started_at=started_at,
        last_error=None,
        last_errors=[],
        last_forecast_snapshot_count=0,
        last_validation_record_count=0,
    )

    forecast_count = 0
    validation_count = 0
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
        last_errors=errors[:10],
    )
    return background_collection_status()
