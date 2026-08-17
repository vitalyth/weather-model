from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain import PrecipitationType


class LocationBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    elevation_m: float | None = None
    timezone: str = "UTC"


class LocationCreate(LocationBase):
    pass


class LocationRead(LocationBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class LocationSearchResult(BaseModel):
    id: int | None = None
    name: str
    display_name: str
    subtitle: str
    latitude: float
    longitude: float
    elevation_m: float | None = None
    timezone: str
    population: int | None = None
    country: str | None = None
    country_code: str | None = None
    admin1: str | None = None


class CurrentWeatherRead(BaseModel):
    location_id: int
    source: str
    temperature_f: float | None = None
    relative_humidity_percent: float | None = None
    wind_speed_mph: float | None = None
    weather_code: int | None = None
    condition: str
    observed_at: datetime | None = None
    timezone: str


class TemperaturePrediction(BaseModel):
    temperature_f: float
    apparent_temperature_f: float
    daily_max_f: float | None = None
    daily_min_f: float | None = None
    dew_point_f: float
    likely_low_f: float
    likely_high_f: float


class PrecipitationPrediction(BaseModel):
    probability_percent: float = Field(ge=0, le=100)
    amount_in: float = Field(ge=0)
    precipitation_type: PrecipitationType
    start_time: datetime | None = None
    end_time: datetime | None = None
    intensity: Literal["none", "light", "moderate", "heavy"]


class WindPrediction(BaseModel):
    sustained_speed_mph: float = Field(ge=0)
    direction_degrees: float = Field(ge=0, lt=360)
    max_gust_mph: float = Field(ge=0)


class AtmosphericPrediction(BaseModel):
    relative_humidity_percent: float = Field(ge=0, le=100)
    pressure_hpa: float
    pressure_trend: Literal["falling", "steady", "rising"]
    cloud_cover_percent: float = Field(ge=0, le=100)
    visibility_mi: float = Field(ge=0)


class NotableWeatherProbabilities(BaseModel):
    thunderstorms_percent: float = Field(ge=0, le=100)
    heavy_rainfall_percent: float = Field(ge=0, le=100)
    high_winds_percent: float = Field(ge=0, le=100)
    snow_percent: float = Field(ge=0, le=100)
    ice_percent: float = Field(ge=0, le=100)
    fog_percent: float = Field(ge=0, le=100)
    extreme_heat_percent: float = Field(ge=0, le=100)
    extreme_cold_percent: float = Field(ge=0, le=100)


class ForecastPoint(BaseModel):
    horizon: str
    horizon_hours: int
    forecast_valid_at: datetime
    confidence_percent: float = Field(ge=0, le=100)
    temperature: TemperaturePrediction
    precipitation: PrecipitationPrediction
    wind: WindPrediction
    atmosphere: AtmosphericPrediction
    notable_weather: NotableWeatherProbabilities


class ForecastSnapshotRead(BaseModel):
    id: int
    location: LocationRead
    forecast_created_at: datetime
    data_cutoff_time: datetime
    model_version: str
    feature_version: str
    training_data_cutoff: datetime | None
    generator_kind: str
    raw_record_count: int = 0
    points: list[ForecastPoint]
    hourly_points: list[ForecastPoint]


class ForecastCreateResponse(ForecastSnapshotRead):
    pass


class RawWeatherRecordRead(BaseModel):
    id: int
    source: str
    model: str
    forecast_initialization_time: datetime | None
    forecast_valid_time: datetime
    retrieval_time: datetime
    location_id: int
    location_name: str
    latitude: float
    longitude: float
    elevation_m: float | None
    variable: str
    value: str
    units: str

    model_config = {"from_attributes": True}


class WeatherProviderRead(BaseModel):
    source: str
    model: str
    source_url: str


class NormalizedWeatherRecordRead(BaseModel):
    id: int
    raw_record_id: int
    source: str
    model: str
    location_id: int
    valid_time: datetime
    retrieved_at: datetime
    raw_variable: str
    normalized_variable: str
    raw_value: str
    normalized_value: float | None
    normalized_text: str | None
    normalized_units: str
    quality_status: str
    quality_score: float
    quality_reason: str

    model_config = {"from_attributes": True}


class BackgroundCollectionStatusRead(BaseModel):
    enabled: bool
    running: bool
    interval_seconds: int
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    last_location_count: int = 0
    last_forecast_snapshot_count: int = 0
    last_validation_record_count: int = 0
    last_cached_report_count: int = 0
    last_errors: list[str] = Field(default_factory=list)


class CurrentStateValue(BaseModel):
    value: float | None
    text: str | None = None
    units: str
    source: str
    valid_time: datetime
    quality_score: float


class CurrentStateTrends(BaseModel):
    temperature_change_1h_f: float | None = None
    temperature_change_3h_f: float | None = None
    temperature_change_6h_f: float | None = None
    pressure_change_3h_hpa: float | None = None
    pressure_change_6h_hpa: float | None = None
    dewpoint_change_f: float | None = None
    humidity_change_percent: float | None = None
    wind_shift_degrees: float | None = None
    precipitation_recent_in: float | None = None
    cloud_trend: str | None = None


class CurrentStateRead(BaseModel):
    location: LocationRead
    generated_at: datetime
    data_cutoff_time: datetime | None
    values: dict[str, CurrentStateValue]
    trends: CurrentStateTrends
    evidence_record_count: int


class NumericalModelLayerRead(BaseModel):
    generated_at: datetime
    model_count: int
    sources: list[str]
    model_temperature_mean_f: float | None
    model_temperature_median_f: float | None
    model_temperature_std_f: float | None
    model_precipitation_probability_mean_percent: float | None
    model_precipitation_agreement_percent: float | None
    model_wind_mean_mph: float | None
    model_pressure_mean_hpa: float | None
    ensemble_spread: float | None


class HistoricalPatternLayerRead(BaseModel):
    status: str
    sample_size: int
    normal_high_temperature_f: float | None = None
    normal_low_temperature_f: float | None = None
    typical_precipitation_probability_percent: float | None = None
    historical_temperature_percentile: float | None = None
    note: str


class AnalogLayerRead(BaseModel):
    status: str
    analog_count: int
    analog_confidence_percent: float
    analogs: list[dict[str, Any]]
    note: str


class MicroclimateLayerRead(BaseModel):
    latitude: float
    longitude: float
    elevation_m: float | None
    learned_bias_status: str
    estimated_features: dict[str, Any]
    note: str


class WeatherRegimeRead(BaseModel):
    regime: str
    confidence_percent: float
    factors: list[str]


class FeatureDatasetRead(BaseModel):
    feature_version: str
    generated_at: datetime
    features: dict[str, Any]


class PhaseLayersRead(BaseModel):
    location: LocationRead
    generated_at: datetime
    numerical_model_layer: NumericalModelLayerRead
    historical_pattern_layer: HistoricalPatternLayerRead
    analog_layer: AnalogLayerRead
    microclimate_layer: MicroclimateLayerRead
    weather_regime: WeatherRegimeRead
    feature_dataset: FeatureDatasetRead


class MachineLearningForecastLayerRead(BaseModel):
    status: str
    algorithm: str
    training_sample_count: int
    prediction_source: str
    temperature_prediction_f: float | None
    note: str


class EnsembleLayerRead(BaseModel):
    status: str
    weights: dict[str, float]
    temperature_prediction_f: float | None
    precipitation_probability_percent: float | None
    note: str


class ConfidenceCalibrationRead(BaseModel):
    status: str
    sample_count: int
    mean_confidence_percent: float | None
    calibration_error: float | None
    note: str


class SnapshotIntegrityRead(BaseModel):
    immutable_snapshot_count: int
    frozen_feature_row_count: int
    unresolved_forecast_count: int
    leakage_policy: str


class ProfessionalBenchmarkRead(BaseModel):
    source: str
    archived_record_count: int
    comparable_validation_count: int
    status: str


class GroundTruthRead(BaseModel):
    methodology: str
    observation_source_count: int
    validated_record_count: int
    latest_observation_time: datetime | None


class AccuracyMetricsRead(BaseModel):
    sample_count: int
    temperature_mae_f: float | None
    temperature_rmse_f: float | None
    temperature_median_absolute_error_f: float | None
    temperature_bias_f: float | None
    wind_speed_mae_mph: float | None
    pressure_mae_hpa: float | None


class SkillScoreRead(BaseModel):
    baseline: str
    variable: str
    sample_count: int
    model_error: float | None
    baseline_error: float | None
    skill_score: float | None
    interpretation: str


class StatisticalSignificanceRead(BaseModel):
    sample_count: int
    mean_error_difference: float | None
    median_error_difference: float | None
    confidence_interval_95: list[float] | None
    classification: str
    note: str


class PerformanceSegmentRead(BaseModel):
    segment_type: str
    segment: str
    sample_count: int
    temperature_mae_f: float | None
    benchmark_temperature_mae_f: float | None
    skill_score: float | None


class Phase20ReportRead(BaseModel):
    location: LocationRead
    generated_at: datetime
    machine_learning_forecast: MachineLearningForecastLayerRead
    ensemble: EnsembleLayerRead
    confidence: ConfidenceCalibrationRead
    snapshot_integrity: SnapshotIntegrityRead
    professional_benchmark: ProfessionalBenchmarkRead
    ground_truth: GroundTruthRead
    accuracy_metrics: AccuracyMetricsRead
    skill_scores: list[SkillScoreRead]
    statistical_significance: StatisticalSignificanceRead
    segmented_performance: list[PerformanceSegmentRead]


class PredictionHistoryItemRead(BaseModel):
    snapshot_id: int
    prediction_time: datetime
    target_time: datetime
    horizon: str
    temperature_prediction_f: float
    professional_temperature_f: float | None
    actual_temperature_f: float | None
    model_error_f: float | None
    professional_error_f: float | None
    weather_regime: str | None


class ErrorAnalysisRead(BaseModel):
    prediction_id: int | None = None
    sample_count: int
    biggest_misses: list[dict[str, Any]]
    failure_categories: dict[str, int]
    bias_by_horizon: dict[str, float]
    note: str


class VisualizationSummaryRead(BaseModel):
    actual_vs_predicted: list[dict[str, Any]]
    rolling_mae: dict[str, float | None]
    calibration_bins: list[dict[str, Any]]
    contribution_weights: dict[str, float]
    performance_matrix: list[dict[str, Any]]


class AutomationTaskRead(BaseModel):
    name: str
    cadence: str
    status: str
    last_run_at: datetime | None = None
    note: str


class SystemHealthRead(BaseModel):
    status: str
    observation_age_hours: float | None
    missing_models: list[str]
    validation_backlog: int
    indicators: list[dict[str, Any]]


class TransparencyReportRead(BaseModel):
    forecast_snapshot_id: int | None
    numerical_models_used: list[str]
    latest_observation_time: datetime | None
    ml_model_version: str
    ensemble_weights: dict[str, float]
    confidence: ConfidenceCalibrationRead
    prediction_interval: dict[str, float | None]
    missing_data: list[str]
    forecast_creation_time: datetime | None
    explanation: str


class FairComparisonRead(BaseModel):
    rules: list[str]
    qualifying_pair_count: int
    model_wins: int
    professional_wins: int
    ties: int
    conclusion: str


class FinalScorecardRead(BaseModel):
    forecasts_evaluated: int
    locations: int
    evaluation_period: str
    temperature: dict[str, Any]
    precipitation: dict[str, Any]
    wind: dict[str, Any]
    overall_conclusion: str


class DevelopmentPlanRead(BaseModel):
    architecture: list[str]
    data_source_strategy: list[str]
    database_schema: list[str]
    data_flow: list[str]
    validation_methodology: list[str]
    anti_leakage_strategy: list[str]
    benchmark_methodology: list[str]
    machine_learning_strategy: list[str]
    dashboard_architecture: list[str]
    api_architecture: list[str]
    technology_stack: list[str]
    project_structure: list[str]
    development_phases: list[str]


class Phase35ReportRead(BaseModel):
    location: LocationRead
    generated_at: datetime
    phase_21_error_analysis: ErrorAnalysisRead
    phase_22_continuous_learning: dict[str, Any]
    phase_23_walk_forward_backtesting: dict[str, Any]
    phase_24_dashboard: dict[str, Any]
    phase_25_visualizations: VisualizationSummaryRead
    phase_26_database_design: dict[str, Any]
    phase_27_api_design: dict[str, Any]
    phase_28_automation_pipeline: list[AutomationTaskRead]
    phase_29_data_quality_monitoring: SystemHealthRead
    phase_30_transparency: TransparencyReportRead
    phase_31_fair_comparison: FairComparisonRead
    phase_32_professional_outperformance: dict[str, Any]
    phase_33_final_scorecard: FinalScorecardRead
    phase_34_development_approach: dict[str, Any]
    phase_35_required_output: DevelopmentPlanRead
