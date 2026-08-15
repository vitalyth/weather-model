import json
import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FeatureSnapshot, ForecastSnapshot, ForecastValidationRecord, Location
from app.schemas import (
    AutomationTaskRead,
    DevelopmentPlanRead,
    ErrorAnalysisRead,
    FairComparisonRead,
    FinalScorecardRead,
    LocationRead,
    Phase20ReportRead,
    Phase35ReportRead,
    PredictionHistoryItemRead,
    SystemHealthRead,
    TransparencyReportRead,
    VisualizationSummaryRead,
)
from app.services.phase20_service import build_phase20_report


def prediction_history(
    db: Session, location_id: int | None = None, limit: int = 100
) -> list[PredictionHistoryItemRead]:
    statement = select(ForecastSnapshot).order_by(ForecastSnapshot.forecast_created_at.desc())
    if location_id is not None:
        statement = statement.where(ForecastSnapshot.location_id == location_id)
    snapshots = list(db.scalars(statement.limit(limit)).all())
    items: list[PredictionHistoryItemRead] = []
    for snapshot in snapshots:
        payload = json.loads(snapshot.payload_json)
        validations = _validations_for_snapshot(db, snapshot.id)
        by_horizon = {(record.horizon, record.variable): record for record in validations}
        for point in payload.get("points", []):
            validation = by_horizon.get((point["horizon"], "temperature"))
            target_time = datetime.fromisoformat(point["forecast_valid_at"])
            if target_time.tzinfo is None:
                target_time = target_time.replace(tzinfo=UTC)
            items.append(
                PredictionHistoryItemRead(
                    snapshot_id=snapshot.id,
                    prediction_time=snapshot.forecast_created_at,
                    target_time=target_time,
                    horizon=point["horizon"],
                    temperature_prediction_f=float(point["temperature"]["temperature_f"]),
                    professional_temperature_f=(
                        None if validation is None else validation.benchmark_value
                    ),
                    actual_temperature_f=None if validation is None else validation.observed_value,
                    model_error_f=None if validation is None else validation.error,
                    professional_error_f=None if validation is None else validation.benchmark_error,
                    weather_regime=None if validation is None else validation.weather_regime,
                )
            )
    return items[:limit]


def prediction_detail(db: Session, prediction_id: int) -> list[PredictionHistoryItemRead]:
    snapshot = db.get(ForecastSnapshot, prediction_id)
    if snapshot is None:
        return []
    payload = json.loads(snapshot.payload_json)
    validations = _validations_for_snapshot(db, snapshot.id)
    by_horizon = {(record.horizon, record.variable): record for record in validations}
    items: list[PredictionHistoryItemRead] = []
    for point in payload.get("points", []):
        validation = by_horizon.get((point["horizon"], "temperature"))
        target_time = datetime.fromisoformat(point["forecast_valid_at"])
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=UTC)
        items.append(
            PredictionHistoryItemRead(
                snapshot_id=snapshot.id,
                prediction_time=snapshot.forecast_created_at,
                target_time=target_time,
                horizon=point["horizon"],
                temperature_prediction_f=float(point["temperature"]["temperature_f"]),
                professional_temperature_f=None if validation is None else validation.benchmark_value,
                actual_temperature_f=None if validation is None else validation.observed_value,
                model_error_f=None if validation is None else validation.error,
                professional_error_f=None if validation is None else validation.benchmark_error,
                weather_regime=None if validation is None else validation.weather_regime,
            )
        )
    return items


def error_analysis(
    db: Session, location_id: int | None = None, prediction_id: int | None = None
) -> ErrorAnalysisRead:
    records = _validation_records(db, location_id=location_id, prediction_id=prediction_id)
    biggest = sorted(records, key=lambda record: record.absolute_error, reverse=True)[:10]
    categories = Counter(_failure_category(record) for record in records)
    by_horizon: dict[str, list[float]] = defaultdict(list)
    for record in records:
        by_horizon[record.horizon].append(record.error)
    bias_by_horizon = {
        horizon: round(statistics.fmean(values), 3) for horizon, values in by_horizon.items()
    }
    return ErrorAnalysisRead(
        prediction_id=prediction_id,
        sample_count=len(records),
        biggest_misses=[
            {
                "snapshot_id": record.forecast_snapshot_id,
                "horizon": record.horizon,
                "variable": record.variable,
                "predicted": record.predicted_value,
                "observed": record.observed_value,
                "absolute_error": record.absolute_error,
                "category": _failure_category(record),
            }
            for record in biggest
        ],
        failure_categories=dict(categories),
        bias_by_horizon=bias_by_horizon,
        note="Categories are rule-based first-pass labels until richer synoptic inputs exist.",
    )


def visualization_summary(db: Session, location: Location) -> VisualizationSummaryRead:
    records = _validation_records(db, location_id=location.id)
    temp_records = [record for record in records if record.variable == "temperature"]
    phase20 = build_phase20_report(db, location)
    return VisualizationSummaryRead(
        actual_vs_predicted=[
            {
                "valid_at": record.forecast_valid_at.isoformat(),
                "our_model": record.predicted_value,
                "professional": record.benchmark_value,
                "actual": record.observed_value,
            }
            for record in sorted(temp_records, key=lambda item: item.forecast_valid_at)[-120:]
        ],
        rolling_mae={
            "7_sample": _rolling_mae(temp_records, 7),
            "30_sample": _rolling_mae(temp_records, 30),
            "90_sample": _rolling_mae(temp_records, 90),
            "all_time": _mae(temp_records),
        },
        calibration_bins=[],
        contribution_weights=phase20.ensemble.weights,
        performance_matrix=[
            segment.model_dump()
            for segment in phase20.segmented_performance
            if segment.segment_type in {"horizon", "weather_regime"}
        ],
    )


def system_health(db: Session, location_id: int | None = None) -> SystemHealthRead:
    snapshot_filters = [] if location_id is None else [ForecastSnapshot.location_id == location_id]
    validation_filters = (
        [] if location_id is None else [ForecastValidationRecord.location_id == location_id]
    )
    latest_snapshot = db.scalar(
        select(ForecastSnapshot)
        .where(*snapshot_filters)
        .order_by(ForecastSnapshot.forecast_created_at.desc())
    )
    latest_validation = db.scalar(
        select(ForecastValidationRecord)
        .where(*validation_filters)
        .order_by(ForecastValidationRecord.observation_time.desc())
    )
    snapshot_count = int(
        db.scalar(select(func.count()).select_from(ForecastSnapshot).where(*snapshot_filters)) or 0
    )
    validation_count = int(
        db.scalar(
            select(func.count())
            .select_from(ForecastValidationRecord)
            .where(*validation_filters)
        )
        or 0
    )
    backlog = max(0, snapshot_count * 3 - validation_count)
    observation_age = None
    if latest_validation is not None:
        observation_age = round(
            (datetime.now(UTC) - latest_validation.observation_time).total_seconds() / 3600,
            2,
        )
    missing_models = ["ECMWF", "GFS", "HRRR", "ICON"]
    status = "GOOD"
    if latest_snapshot is None:
        status = "DEGRADED"
    if backlog > max(12, snapshot_count):
        status = "DEGRADED"
    return SystemHealthRead(
        status=status,
        observation_age_hours=observation_age,
        missing_models=missing_models,
        validation_backlog=backlog,
        indicators=[
            {"name": "database", "status": "GOOD", "detail": "SQLite connection available"},
            {
                "name": "validation_backlog",
                "status": "GOOD" if backlog <= max(12, snapshot_count) else "DEGRADED",
                "detail": f"{backlog} variable-level validations unresolved",
            },
            {
                "name": "model_coverage",
                "status": "DEGRADED",
                "detail": "Only Open-Meteo and NWS are currently archived as forecast sources.",
            },
        ],
    )


def transparency_report(
    db: Session, location: Location, forecast_snapshot_id: int | None = None
) -> TransparencyReportRead:
    snapshot = _selected_snapshot(db, location.id, forecast_snapshot_id)
    phase20 = build_phase20_report(db, location)
    feature_snapshot = None
    if snapshot is not None:
        feature_snapshot = db.scalar(
            select(FeatureSnapshot)
            .where(FeatureSnapshot.forecast_snapshot_id == snapshot.id)
            .order_by(FeatureSnapshot.created_at.desc())
        )
    missing_data = ["historical_climatology", "analog_database", "trained_ml_model"]
    latest_observation = max(
        (record.observation_time for record in _validation_records(db, location_id=location.id)),
        default=None,
    )
    return TransparencyReportRead(
        forecast_snapshot_id=None if snapshot is None else snapshot.id,
        numerical_models_used=["Open-Meteo", "National Weather Service"],
        latest_observation_time=latest_observation,
        ml_model_version=phase20.machine_learning_forecast.algorithm,
        ensemble_weights=phase20.ensemble.weights,
        confidence=phase20.confidence,
        prediction_interval={
            "temperature_lower_f": None
            if phase20.ensemble.temperature_prediction_f is None
            else round(phase20.ensemble.temperature_prediction_f - 3, 1),
            "temperature_upper_f": None
            if phase20.ensemble.temperature_prediction_f is None
            else round(phase20.ensemble.temperature_prediction_f + 3, 1),
        },
        missing_data=missing_data,
        forecast_creation_time=None if snapshot is None else snapshot.forecast_created_at,
        explanation=_forecast_explanation(phase20, feature_snapshot),
    )


def fair_comparison(db: Session, location_id: int | None = None) -> FairComparisonRead:
    records = [
        record
        for record in _validation_records(db, location_id=location_id)
        if record.variable == "temperature" and record.benchmark_absolute_error is not None
    ]
    model_wins = sum(record.absolute_error < float(record.benchmark_absolute_error) for record in records)
    pro_wins = sum(record.absolute_error > float(record.benchmark_absolute_error) for record in records)
    ties = len(records) - model_wins - pro_wins
    conclusion = "Statistically tied / insufficient evidence"
    if len(records) >= 30 and model_wins > pro_wins * 1.1:
        conclusion = "Possibly outperforming"
    if len(records) >= 30 and pro_wins > model_wins * 1.1:
        conclusion = "Underperforming"
    return FairComparisonRead(
        rules=[
            "Same location",
            "Same variable",
            "Same valid time window",
            "Comparable forecast horizon",
            "Both forecasts recorded before the result occurred",
            "Every qualifying pair included",
        ],
        qualifying_pair_count=len(records),
        model_wins=model_wins,
        professional_wins=pro_wins,
        ties=ties,
        conclusion=conclusion,
    )


def final_scorecard(db: Session, location_id: int | None = None) -> FinalScorecardRead:
    records = _validation_records(db, location_id=location_id)
    temp = [record for record in records if record.variable == "temperature"]
    wind = [record for record in records if record.variable == "wind_speed"]
    locations = int(db.scalar(select(func.count()).select_from(Location)) or 0)
    period = "No resolved forecasts yet"
    if records:
        period = f"{min(record.forecast_valid_at for record in records).date()} to {max(record.forecast_valid_at for record in records).date()}"
    return FinalScorecardRead(
        forecasts_evaluated=len(records),
        locations=locations if location_id is None else 1,
        evaluation_period=period,
        temperature={
            "our_mae_f": _mae(temp),
            "professional_mae_f": _benchmark_mae(temp),
            "status": fair_comparison(db, location_id).conclusion,
        },
        precipitation={
            "brier_score": None,
            "professional_brier_score": None,
            "status": "Insufficient probability validation data",
        },
        wind={
            "our_mae_mph": _mae(wind),
            "professional_mae_mph": _benchmark_mae(wind),
            "status": "Insufficient evidence" if len(wind) < 30 else "Ready for review",
        },
        overall_conclusion=(
            "Performance is multidimensional; use variable, horizon, and regime segments instead of a single accuracy percentage."
        ),
    )


def phase35_report(db: Session, location: Location) -> Phase35ReportRead:
    phase20 = build_phase20_report(db, location)
    return Phase35ReportRead(
        location=LocationRead.model_validate(location),
        generated_at=datetime.now(UTC),
        phase_21_error_analysis=error_analysis(db, location_id=location.id),
        phase_22_continuous_learning={
            "status": "gated",
            "resolved_training_samples": phase20.machine_learning_forecast.training_sample_count,
            "policy": "Train only on resolved forecasts; promote only after out-of-sample improvement.",
        },
        phase_23_walk_forward_backtesting={
            "status": "planned",
            "method": "Chronological walk-forward validation by year or month once history exists.",
        },
        phase_24_dashboard={
            "status": "implemented_foundation",
            "views": [
                "forecast",
                "prediction_breakdown",
                "model_agreement",
                "accuracy",
                "head_to_head",
                "history",
                "error_analysis",
            ],
        },
        phase_25_visualizations=visualization_summary(db, location),
        phase_26_database_design={
            "implemented_tables": [
                "locations",
                "forecast_snapshots",
                "raw_weather_records",
                "normalized_weather_records",
                "feature_snapshots",
                "forecast_validation_records",
            ],
            "planned_tables": [
                "model_versions",
                "analog_matches",
                "professional_forecasts",
                "model_metrics",
                "error_analysis",
            ],
        },
        phase_27_api_design={"endpoints": api_catalog()},
        phase_28_automation_pipeline=automation_tasks(),
        phase_29_data_quality_monitoring=system_health(db, location.id),
        phase_30_transparency=transparency_report(db, location),
        phase_31_fair_comparison=fair_comparison(db, location.id),
        phase_32_professional_outperformance={
            "status": phase20.statistical_significance.classification,
            "rule": "Never claim superiority until paired samples and confidence intervals support it.",
        },
        phase_33_final_scorecard=final_scorecard(db, location.id),
        phase_34_development_approach={
            "current_stage": "Stage 2/3 bridge",
            "next_steps": [
                "Accumulate resolved validations",
                "Add historical providers",
                "Add probability metrics",
                "Train simple baselines before advanced models",
            ],
        },
        phase_35_required_output=development_plan(),
    )


def automation_tasks() -> list[AutomationTaskRead]:
    return [
        AutomationTaskRead(
            name="retrieve_observations",
            cadence="every 15 minutes",
            status="manual_endpoint_ready",
            note="Current implementation retrieves observations during forecast generation.",
        ),
        AutomationTaskRead(
            name="generate_forecasts",
            cadence="hourly",
            status="manual_endpoint_ready",
            note="Use POST /locations/{location_id}/forecasts until scheduler is added.",
        ),
        AutomationTaskRead(
            name="validate_forecasts",
            cadence="hourly after valid time",
            status="manual_endpoint_ready",
            note="Use POST /validation/run/{location_id}; eligible records are de-duplicated.",
        ),
        AutomationTaskRead(
            name="recalculate_metrics",
            cadence="daily",
            status="api_computed",
            note="Reports are computed from persisted validation records.",
        ),
    ]


def api_catalog() -> list[str]:
    return [
        "GET /locations",
        "POST /locations",
        "DELETE /locations/{location_id}",
        "POST /locations/{location_id}/forecasts",
        "GET /forecasts",
        "GET /forecasts/{snapshot_id}",
        "GET /phase-layers/{location_id}",
        "POST /validation/run/{location_id}",
        "GET /phase-20/{location_id}",
        "GET /predictions/history",
        "GET /predictions/{prediction_id}",
        "GET /accuracy/head-to-head",
        "GET /accuracy/calibration",
        "GET /models/performance",
        "GET /models/versions",
        "GET /errors",
        "GET /errors/{prediction_id}",
        "GET /system/health",
        "GET /scorecard",
        "GET /phase-35/{location_id}",
    ]


def development_plan() -> DevelopmentPlanRead:
    return DevelopmentPlanRead(
        architecture=["FastAPI API", "SQLite persistence", "Next.js dashboard", "provider adapters"],
        data_source_strategy=["Open-Meteo forecasts", "NWS benchmark forecasts", "METAR observations"],
        database_schema=[
            "raw archive",
            "normalized records",
            "frozen forecast snapshots",
            "frozen feature snapshots",
            "validation records",
        ],
        data_flow=[
            "ingest",
            "normalize",
            "build current state",
            "build features",
            "freeze forecast",
            "validate after valid time",
            "score and report",
        ],
        validation_methodology=["fixed observation matching rules", "paired benchmark comparison"],
        anti_leakage_strategy=["freeze before outcome", "use only pre-issue benchmark records"],
        benchmark_methodology=["archive professional forecasts at issue time", "compare only matched pairs"],
        machine_learning_strategy=["start simple", "train only on resolved forecasts", "walk-forward validation"],
        dashboard_architecture=["forecast", "layers", "validation", "segments", "transparency"],
        api_architecture=api_catalog(),
        technology_stack=["FastAPI", "SQLAlchemy", "SQLite", "Next.js", "TypeScript"],
        project_structure=["backend/app", "backend/tests", "frontend/app", "docs"],
        development_phases=["foundation", "validation", "learning", "automation", "statistical reporting"],
    )


def _validations_for_snapshot(db: Session, snapshot_id: int) -> list[ForecastValidationRecord]:
    return list(
        db.scalars(
            select(ForecastValidationRecord).where(
                ForecastValidationRecord.forecast_snapshot_id == snapshot_id
            )
        ).all()
    )


def _validation_records(
    db: Session, location_id: int | None = None, prediction_id: int | None = None
) -> list[ForecastValidationRecord]:
    statement = select(ForecastValidationRecord).order_by(
        ForecastValidationRecord.forecast_valid_at.desc()
    )
    if location_id is not None:
        statement = statement.where(ForecastValidationRecord.location_id == location_id)
    if prediction_id is not None:
        statement = statement.where(ForecastValidationRecord.forecast_snapshot_id == prediction_id)
    return list(db.scalars(statement).all())


def _selected_snapshot(
    db: Session, location_id: int, forecast_snapshot_id: int | None
) -> ForecastSnapshot | None:
    if forecast_snapshot_id is not None:
        return db.get(ForecastSnapshot, forecast_snapshot_id)
    return db.scalar(
        select(ForecastSnapshot)
        .where(ForecastSnapshot.location_id == location_id)
        .order_by(ForecastSnapshot.forecast_created_at.desc())
    )


def _failure_category(record: ForecastValidationRecord) -> str:
    if record.variable == "temperature":
        if record.error > 0:
            return "warm_bias"
        if record.error < 0:
            return "cold_bias"
    if record.variable == "wind_speed":
        return "wind_speed_error"
    if record.variable == "pressure":
        return "pressure_error"
    return "uncategorized"


def _forecast_explanation(
    phase20: Phase20ReportRead, feature_snapshot: FeatureSnapshot | None
) -> str:
    if feature_snapshot is None:
        return "No frozen feature row is available for this forecast yet."
    payload = json.loads(feature_snapshot.payload_json)
    features = payload.get("features", {})
    regime = features.get("weather_regime", "unknown regime")
    temp = phase20.ensemble.temperature_prediction_f
    spread = features.get("model_temperature_std")
    return (
        f"The forecast uses the frozen {payload.get('feature_version')} feature row, "
        f"a {regime} regime, numerical-model temperature {temp} F, and model spread {spread}. "
        "Missing historical analog and trained ML inputs are explicitly excluded from the explanation."
    )


def _rolling_mae(records: list[ForecastValidationRecord], window: int) -> float | None:
    if not records:
        return None
    return _mae(sorted(records, key=lambda item: item.forecast_valid_at)[-window:])


def _mae(records: list[ForecastValidationRecord]) -> float | None:
    return None if not records else round(statistics.fmean(record.absolute_error for record in records), 3)


def _benchmark_mae(records: list[ForecastValidationRecord]) -> float | None:
    values = [record.benchmark_absolute_error for record in records if record.benchmark_absolute_error is not None]
    return None if not values else round(statistics.fmean(values), 3)
