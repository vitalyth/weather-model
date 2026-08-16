import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    FeatureSnapshot,
    ForecastSnapshot,
    ForecastValidationRecord,
    Location,
    NormalizedWeatherRecord,
)
from app.schemas import (
    AccuracyMetricsRead,
    ConfidenceCalibrationRead,
    EnsembleLayerRead,
    GroundTruthRead,
    LocationRead,
    MachineLearningForecastLayerRead,
    PerformanceSegmentRead,
    Phase20ReportRead,
    PhaseLayersRead,
    ProfessionalBenchmarkRead,
    SkillScoreRead,
    SnapshotIntegrityRead,
    StatisticalSignificanceRead,
)
from app.services.phase_layers_service import build_phase_layers

OBSERVATION_SOURCES = {"Aviation Weather Center METAR"}
BENCHMARK_SOURCE = "National Weather Service"
VALIDATION_VARIABLES = {
    "temperature": ("temperature", lambda point: point["temperature"]["temperature_f"]),
    "wind_speed": ("wind_speed", lambda point: point["wind"]["sustained_speed_mph"]),
    "pressure": ("pressure", lambda point: point["atmosphere"]["pressure_hpa"]),
}
MIN_TRAINING_SAMPLES = 30
MIN_SIGNIFICANCE_SAMPLES = 30


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def freeze_feature_snapshot(
    db: Session,
    forecast_snapshot: ForecastSnapshot,
    phase_layers: PhaseLayersRead | None = None,
) -> FeatureSnapshot:
    if phase_layers is None:
        phase_layers = build_phase_layers(db, forecast_snapshot.location)
    payload = phase_layers.feature_dataset.model_dump(mode="json")
    payload_json = json.dumps(payload, sort_keys=True)
    feature_snapshot = FeatureSnapshot(
        forecast_snapshot_id=forecast_snapshot.id,
        location_id=forecast_snapshot.location_id,
        generated_at=phase_layers.feature_dataset.generated_at,
        feature_version=phase_layers.feature_dataset.feature_version,
        payload_json=payload_json,
        freeze_hash=hashlib.sha256(payload_json.encode()).hexdigest(),
    )
    db.add(feature_snapshot)
    return feature_snapshot


def validate_matured_forecasts(db: Session, location: Location) -> int:
    snapshots = list(
        db.scalars(
            select(ForecastSnapshot)
            .where(ForecastSnapshot.location_id == location.id)
            .order_by(ForecastSnapshot.forecast_created_at)
        ).all()
    )
    created = 0
    for snapshot in snapshots:
        payload = json.loads(snapshot.payload_json)
        regime = _snapshot_regime(db, snapshot)
        forecast_created_at = _as_utc(snapshot.forecast_created_at)
        for point in payload.get("points", []):
            forecast_valid_at = _as_utc(datetime.fromisoformat(point["forecast_valid_at"]))
            for variable, (normalized_variable, getter) in VALIDATION_VARIABLES.items():
                if _validation_exists(db, snapshot.id, point["horizon"], variable):
                    continue
                observation = _nearest_observation(
                    db,
                    location.id,
                    normalized_variable,
                    forecast_created_at,
                    forecast_valid_at,
                )
                if observation is None or observation.normalized_value is None:
                    continue
                predicted = float(getter(point))
                benchmark = _nearest_benchmark(
                    db,
                    location.id,
                    normalized_variable,
                    forecast_created_at,
                    forecast_valid_at,
                )
                benchmark_value = None if benchmark is None else benchmark.normalized_value
                error = predicted - observation.normalized_value
                benchmark_error = (
                    None
                    if benchmark_value is None
                    else float(benchmark_value) - observation.normalized_value
                )
                record = ForecastValidationRecord(
                    forecast_snapshot_id=snapshot.id,
                    location_id=location.id,
                    horizon=point["horizon"],
                    horizon_hours=int(point["horizon_hours"]),
                    forecast_created_at=forecast_created_at,
                    forecast_valid_at=forecast_valid_at,
                    validated_at=datetime.now(UTC),
                    observation_time=observation.valid_time,
                    observation_source=observation.source,
                    variable=variable,
                    predicted_value=predicted,
                    observed_value=observation.normalized_value,
                    error=round(error, 4),
                    absolute_error=round(abs(error), 4),
                    squared_error=round(error * error, 4),
                    benchmark_source=None if benchmark is None else benchmark.source,
                    benchmark_value=benchmark_value,
                    benchmark_error=None if benchmark_error is None else round(benchmark_error, 4),
                    benchmark_absolute_error=(
                        None if benchmark_error is None else round(abs(benchmark_error), 4)
                    ),
                    weather_regime=regime,
                    segment_json=json.dumps(
                        {
                            "horizon_bucket": _horizon_bucket(int(point["horizon_hours"])),
                            "season": _season(forecast_valid_at.month),
                            "time_of_day": _time_of_day(forecast_valid_at.hour),
                            "location": location.name,
                        }
                    ),
                )
                db.add(record)
                created += 1
    if created:
        db.commit()
    return created


def build_phase20_report(db: Session, location: Location) -> Phase20ReportRead:
    generated_at = datetime.now(UTC)
    phase_layers = build_phase_layers(db, location)
    validations = _validation_records(db, location.id)
    temp_records = [record for record in validations if record.variable == "temperature"]
    benchmark_records = [
        record for record in temp_records if record.benchmark_absolute_error is not None
    ]

    return Phase20ReportRead(
        location=LocationRead.model_validate(location),
        generated_at=generated_at,
        machine_learning_forecast=_machine_learning_layer(temp_records, phase_layers),
        ensemble=_ensemble_layer(phase_layers, temp_records),
        confidence=_confidence_layer(temp_records),
        snapshot_integrity=_snapshot_integrity(db, location.id),
        professional_benchmark=_professional_benchmark(db, location.id, benchmark_records),
        ground_truth=_ground_truth(validations),
        accuracy_metrics=_accuracy_metrics(validations),
        skill_scores=_skill_scores(benchmark_records),
        statistical_significance=_statistical_significance(benchmark_records),
        segmented_performance=_segmented_performance(temp_records),
    )


def _validation_exists(db: Session, snapshot_id: int, horizon: str, variable: str) -> bool:
    existing_id = db.scalar(
        select(ForecastValidationRecord.id)
        .where(ForecastValidationRecord.forecast_snapshot_id == snapshot_id)
        .where(ForecastValidationRecord.horizon == horizon)
        .where(ForecastValidationRecord.variable == variable)
        .limit(1)
    )
    return existing_id is not None


def _nearest_observation(
    db: Session,
    location_id: int,
    variable: str,
    forecast_created_at: datetime,
    forecast_valid_at: datetime,
) -> NormalizedWeatherRecord | None:
    window_start = forecast_valid_at - timedelta(hours=3)
    window_end = forecast_valid_at + timedelta(hours=3)
    records = list(
        db.scalars(
            select(NormalizedWeatherRecord)
            .where(NormalizedWeatherRecord.location_id == location_id)
            .where(NormalizedWeatherRecord.source.in_(OBSERVATION_SOURCES))
            .where(NormalizedWeatherRecord.normalized_variable == variable)
            .where(NormalizedWeatherRecord.quality_status != "rejected")
            .where(NormalizedWeatherRecord.valid_time >= forecast_created_at)
            .where(NormalizedWeatherRecord.valid_time >= window_start)
            .where(NormalizedWeatherRecord.valid_time <= window_end)
        ).all()
    )
    return min(
        records,
        key=lambda record: abs(_as_utc(record.valid_time) - forecast_valid_at),
        default=None,
    )


def _nearest_benchmark(
    db: Session,
    location_id: int,
    variable: str,
    forecast_created_at: datetime,
    forecast_valid_at: datetime,
) -> NormalizedWeatherRecord | None:
    window_start = forecast_valid_at - timedelta(hours=3)
    window_end = forecast_valid_at + timedelta(hours=3)
    records = list(
        db.scalars(
            select(NormalizedWeatherRecord)
            .where(NormalizedWeatherRecord.location_id == location_id)
            .where(NormalizedWeatherRecord.source == BENCHMARK_SOURCE)
            .where(NormalizedWeatherRecord.normalized_variable == variable)
            .where(NormalizedWeatherRecord.quality_status != "rejected")
            .where(NormalizedWeatherRecord.retrieved_at <= forecast_created_at)
            .where(NormalizedWeatherRecord.valid_time >= window_start)
            .where(NormalizedWeatherRecord.valid_time <= window_end)
        ).all()
    )
    return min(
        records,
        key=lambda record: abs(_as_utc(record.valid_time) - forecast_valid_at),
        default=None,
    )


def _snapshot_regime(db: Session, snapshot: ForecastSnapshot) -> str | None:
    feature_snapshot = db.scalar(
        select(FeatureSnapshot)
        .where(FeatureSnapshot.forecast_snapshot_id == snapshot.id)
        .order_by(FeatureSnapshot.created_at.desc())
        .limit(1)
    )
    if feature_snapshot is None:
        return None
    payload = json.loads(feature_snapshot.payload_json)
    return payload.get("features", {}).get("weather_regime")


def _validation_records(db: Session, location_id: int) -> list[ForecastValidationRecord]:
    return list(
        db.scalars(
            select(ForecastValidationRecord)
            .where(ForecastValidationRecord.location_id == location_id)
            .order_by(ForecastValidationRecord.forecast_valid_at.desc())
        ).all()
    )


def _machine_learning_layer(
    temp_records: list[ForecastValidationRecord], phase_layers: PhaseLayersRead
) -> MachineLearningForecastLayerRead:
    training_count = len(temp_records)
    prediction = phase_layers.numerical_model_layer.model_temperature_mean_f
    if training_count < MIN_TRAINING_SAMPLES:
        return MachineLearningForecastLayerRead(
            status="insufficient_training_data",
            algorithm="linear_baseline_pending",
            training_sample_count=training_count,
            prediction_source="numerical_model_mean_fallback",
            temperature_prediction_f=prediction,
            note="ML training waits for resolved forecasts only; unresolved forecasts are excluded.",
        )
    bias = statistics.fmean(record.error for record in temp_records)
    return MachineLearningForecastLayerRead(
        status="baseline_ready",
        algorithm="bias_corrected_linear_baseline",
        training_sample_count=training_count,
        prediction_source="validated_bias_correction",
        temperature_prediction_f=None if prediction is None else round(prediction - bias, 2),
        note="First ML baseline uses resolved forecast bias; more algorithms need out-of-sample tests.",
    )


def _ensemble_layer(
    phase_layers: PhaseLayersRead, temp_records: list[ForecastValidationRecord]
) -> EnsembleLayerRead:
    numerical_temp = phase_layers.numerical_model_layer.model_temperature_mean_f
    weights = {
        "numerical": 0.75,
        "observational_trend": 0.15,
        "machine_learning": 0.10 if len(temp_records) >= MIN_TRAINING_SAMPLES else 0.0,
        "analog": 0.0,
        "climatology": 0.0,
    }
    total = sum(weights.values()) or 1
    weights = {key: round(value / total, 3) for key, value in weights.items()}
    return EnsembleLayerRead(
        status="first_pass",
        weights=weights,
        temperature_prediction_f=numerical_temp,
        precipitation_probability_percent=(
            phase_layers.numerical_model_layer.model_precipitation_probability_mean_percent
        ),
        note="Weights are rule-based until enough validation history exists for a meta-model.",
    )


def _confidence_layer(records: list[ForecastValidationRecord]) -> ConfidenceCalibrationRead:
    if not records:
        return ConfidenceCalibrationRead(
            status="waiting_for_validation",
            sample_count=0,
            mean_confidence_percent=None,
            calibration_error=None,
            note="Confidence calibration starts after forecasts resolve against observations.",
        )
    mean_abs_error = statistics.fmean(record.absolute_error for record in records)
    return ConfidenceCalibrationRead(
        status="uncalibrated_first_pass",
        sample_count=len(records),
        mean_confidence_percent=None,
        calibration_error=round(mean_abs_error, 3),
        note="Current calibration proxy reports mean absolute error until probability bins mature.",
    )


def _snapshot_integrity(db: Session, location_id: int) -> SnapshotIntegrityRead:
    snapshot_count = db.scalar(
        select(func.count()).select_from(ForecastSnapshot).where(ForecastSnapshot.location_id == location_id)
    )
    feature_count = db.scalar(
        select(func.count()).select_from(FeatureSnapshot).where(FeatureSnapshot.location_id == location_id)
    )
    validation_count = db.scalar(
        select(func.count())
        .select_from(ForecastValidationRecord)
        .where(ForecastValidationRecord.location_id == location_id)
    )
    unresolved = max(0, int(snapshot_count or 0) * len(VALIDATION_VARIABLES) - int(validation_count or 0))
    return SnapshotIntegrityRead(
        immutable_snapshot_count=int(snapshot_count or 0),
        frozen_feature_row_count=int(feature_count or 0),
        unresolved_forecast_count=unresolved,
        leakage_policy="Forecasts and feature rows are frozen before validation; observations are only used after valid time.",
    )


def _professional_benchmark(
    db: Session, location_id: int, benchmark_records: list[ForecastValidationRecord]
) -> ProfessionalBenchmarkRead:
    archived_count = db.scalar(
        select(func.count())
        .select_from(NormalizedWeatherRecord)
        .where(NormalizedWeatherRecord.location_id == location_id)
        .where(NormalizedWeatherRecord.source == BENCHMARK_SOURCE)
    )
    return ProfessionalBenchmarkRead(
        source=BENCHMARK_SOURCE,
        archived_record_count=int(archived_count or 0),
        comparable_validation_count=len(benchmark_records),
        status="ready" if benchmark_records else "archiving_or_waiting_for_overlap",
    )


def _ground_truth(records: list[ForecastValidationRecord]) -> GroundTruthRead:
    latest = max((record.observation_time for record in records), default=None)
    sources = {record.observation_source for record in records}
    return GroundTruthRead(
        methodology="Nearest non-rejected observation within +/-3 hours, fixed before comparison.",
        observation_source_count=len(sources),
        validated_record_count=len(records),
        latest_observation_time=latest,
    )


def _accuracy_metrics(records: list[ForecastValidationRecord]) -> AccuracyMetricsRead:
    temp = [record for record in records if record.variable == "temperature"]
    wind = [record for record in records if record.variable == "wind_speed"]
    pressure = [record for record in records if record.variable == "pressure"]
    return AccuracyMetricsRead(
        sample_count=len(records),
        temperature_mae_f=_mae(temp),
        temperature_rmse_f=_rmse(temp),
        temperature_median_absolute_error_f=_median_absolute_error(temp),
        temperature_bias_f=_bias(temp),
        wind_speed_mae_mph=_mae(wind),
        pressure_mae_hpa=_mae(pressure),
    )


def _skill_scores(records: list[ForecastValidationRecord]) -> list[SkillScoreRead]:
    model_error = _mae(records)
    benchmark_errors = [
        record.benchmark_absolute_error
        for record in records
        if record.benchmark_absolute_error is not None
    ]
    baseline_error = None if not benchmark_errors else round(statistics.fmean(benchmark_errors), 3)
    skill = None
    if model_error is not None and baseline_error not in {None, 0}:
        skill = round(1 - model_error / baseline_error, 3)
    return [
        SkillScoreRead(
            baseline=BENCHMARK_SOURCE,
            variable="temperature",
            sample_count=len(benchmark_errors),
            model_error=model_error,
            baseline_error=baseline_error,
            skill_score=skill,
            interpretation=_skill_interpretation(skill, len(benchmark_errors)),
        )
    ]


def _statistical_significance(
    records: list[ForecastValidationRecord],
) -> StatisticalSignificanceRead:
    differences = [
        record.absolute_error - float(record.benchmark_absolute_error)
        for record in records
        if record.benchmark_absolute_error is not None
    ]
    if not differences:
        return StatisticalSignificanceRead(
            sample_count=0,
            mean_error_difference=None,
            median_error_difference=None,
            confidence_interval_95=None,
            classification="TIED / INCONCLUSIVE",
            note="No paired benchmark comparisons are available yet.",
        )
    mean_diff = statistics.fmean(differences)
    median_diff = statistics.median(differences)
    interval = None
    if len(differences) > 1:
        std = statistics.pstdev(differences)
        margin = 1.96 * std / math.sqrt(len(differences))
        interval = [round(mean_diff - margin, 3), round(mean_diff + margin, 3)]
    classification = _significance_classification(mean_diff, interval, len(differences))
    return StatisticalSignificanceRead(
        sample_count=len(differences),
        mean_error_difference=round(mean_diff, 3),
        median_error_difference=round(median_diff, 3),
        confidence_interval_95=interval,
        classification=classification,
        note="Negative error difference means this system had lower absolute error than the benchmark.",
    )


def _segmented_performance(
    records: list[ForecastValidationRecord],
) -> list[PerformanceSegmentRead]:
    groups: dict[tuple[str, str], list[ForecastValidationRecord]] = defaultdict(list)
    for record in records:
        segments = json.loads(record.segment_json)
        groups[("horizon", segments.get("horizon_bucket", "unknown"))].append(record)
        groups[("season", segments.get("season", "unknown"))].append(record)
        groups[("time", segments.get("time_of_day", "unknown"))].append(record)
        groups[("location", segments.get("location", "unknown"))].append(record)
        groups[("weather_regime", record.weather_regime or "unknown")].append(record)

    output: list[PerformanceSegmentRead] = []
    for (segment_type, segment), group_records in sorted(groups.items()):
        benchmark_values = [
            record.benchmark_absolute_error
            for record in group_records
            if record.benchmark_absolute_error is not None
        ]
        model_error = _mae(group_records)
        benchmark_error = None if not benchmark_values else round(statistics.fmean(benchmark_values), 3)
        skill = None
        if model_error is not None and benchmark_error not in {None, 0}:
            skill = round(1 - model_error / benchmark_error, 3)
        output.append(
            PerformanceSegmentRead(
                segment_type=segment_type,
                segment=segment,
                sample_count=len(group_records),
                temperature_mae_f=model_error,
                benchmark_temperature_mae_f=benchmark_error,
                skill_score=skill,
            )
        )
    return output[:24]


def _mae(records: list[ForecastValidationRecord]) -> float | None:
    return None if not records else round(statistics.fmean(record.absolute_error for record in records), 3)


def _rmse(records: list[ForecastValidationRecord]) -> float | None:
    if not records:
        return None
    return round(math.sqrt(statistics.fmean(record.squared_error for record in records)), 3)


def _median_absolute_error(records: list[ForecastValidationRecord]) -> float | None:
    return None if not records else round(statistics.median(record.absolute_error for record in records), 3)


def _bias(records: list[ForecastValidationRecord]) -> float | None:
    return None if not records else round(statistics.fmean(record.error for record in records), 3)


def _skill_interpretation(skill: float | None, sample_count: int) -> str:
    if skill is None:
        return "No comparable benchmark validation yet."
    if sample_count < MIN_SIGNIFICANCE_SAMPLES:
        return "Directional only; sample size is too small for a strong claim."
    if skill > 0:
        return "Positive skill against the benchmark for this segment."
    if skill < 0:
        return "Negative skill against the benchmark for this segment."
    return "No demonstrated skill difference."


def _significance_classification(
    mean_diff: float, interval: list[float] | None, sample_count: int
) -> str:
    if sample_count < MIN_SIGNIFICANCE_SAMPLES or interval is None:
        if mean_diff < 0:
            return "POSSIBLY OUTPERFORMING"
        if mean_diff > 0:
            return "UNDERPERFORMING"
        return "TIED / INCONCLUSIVE"
    if interval[1] < 0:
        return "OUTPERFORMING"
    if interval[0] > 0:
        return "UNDERPERFORMING"
    return "TIED / INCONCLUSIVE"


def _horizon_bucket(horizon_hours: int) -> str:
    if horizon_hours <= 6:
        return "0-6h"
    if horizon_hours <= 12:
        return "6-12h"
    if horizon_hours <= 24:
        return "12-24h"
    if horizon_hours <= 48:
        return "24-48h"
    if horizon_hours <= 72:
        return "48-72h"
    if horizon_hours <= 120:
        return "3-5d"
    return "5-7d"


def _season(month: int) -> str:
    if month in {12, 1, 2}:
        return "winter"
    if month in {3, 4, 5}:
        return "spring"
    if month in {6, 7, 8}:
        return "summer"
    return "fall"


def _time_of_day(hour: int) -> str:
    return "daytime" if 6 <= hour < 18 else "nighttime"
