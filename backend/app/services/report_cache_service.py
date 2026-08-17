import json
from datetime import UTC, datetime
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CachedReport

ReportModel = TypeVar("ReportModel", bound=BaseModel)


def save_report(db: Session, location_id: int, report_kind: str, report: BaseModel) -> CachedReport:
    cached_report = CachedReport(
        location_id=location_id,
        report_kind=report_kind,
        generated_at=datetime.now(UTC),
        payload_json=json.dumps(report.model_dump(mode="json")),
    )
    db.add(cached_report)
    db.flush()
    return cached_report


def latest_report(
    db: Session,
    location_id: int,
    report_kind: str,
    schema: type[ReportModel],
) -> ReportModel | None:
    cached_report = db.scalar(
        select(CachedReport)
        .where(CachedReport.location_id == location_id)
        .where(CachedReport.report_kind == report_kind)
        .order_by(CachedReport.generated_at.desc(), CachedReport.id.desc())
        .limit(1)
    )
    if cached_report is None:
        return None
    return schema.model_validate_json(cached_report.payload_json)
