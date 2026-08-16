import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db, init_db
from app.ingestion.providers import WeatherProviderError
from app.models import Location, NormalizedWeatherRecord, RawWeatherRecord
from app.schemas import (
    BackgroundCollectionStatusRead,
    CurrentStateRead,
    CurrentWeatherRead,
    ErrorAnalysisRead,
    FairComparisonRead,
    FinalScorecardRead,
    ForecastCreateResponse,
    ForecastSnapshotRead,
    LocationCreate,
    LocationRead,
    LocationSearchResult,
    NormalizedWeatherRecordRead,
    Phase20ReportRead,
    Phase35ReportRead,
    PhaseLayersRead,
    PredictionHistoryItemRead,
    RawWeatherRecordRead,
    SystemHealthRead,
    TransparencyReportRead,
    VisualizationSummaryRead,
    WeatherProviderRead,
)
from app.services import current_weather_service, forecast_service, geocoding_service
from app.services.background_collection_service import (
    background_collection_status,
    run_background_collection_loop,
)
from app.services.completion_service import (
    api_catalog,
    error_analysis,
    fair_comparison,
    final_scorecard,
    phase35_report,
    prediction_detail,
    prediction_history,
    system_health,
    transparency_report,
    visualization_summary,
)
from app.services.current_state_service import build_current_state
from app.services.forecast_service import (
    create_forecast_snapshot,
    get_forecast_snapshot,
    list_forecast_snapshots,
)
from app.services.normalization_service import list_normalized_records
from app.services.phase20_service import build_phase20_report, validate_matured_forecasts
from app.services.phase_layers_service import build_phase_layers

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    collector_task = asyncio.create_task(run_background_collection_loop())
    try:
        yield
    finally:
        collector_task.cancel()
        with suppress(asyncio.CancelledError):
            await collector_task


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
DbSession = Annotated[Session, Depends(get_db)]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/debug/runtime")
def runtime_debug() -> dict[str, str]:
    return {
        "app": settings.app_name,
        "database_url": settings.database_url,
    }


@app.get("/collection/status", response_model=BackgroundCollectionStatusRead)
def read_collection_status() -> dict[str, object]:
    return background_collection_status()


@app.post("/locations", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
def create_location(payload: LocationCreate, db: DbSession) -> Location:
    location = Location(**payload.model_dump())
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


@app.get("/locations", response_model=list[LocationRead])
def list_locations(db: DbSession) -> list[Location]:
    return list(db.scalars(select(Location).order_by(Location.name)).all())


@app.get("/locations/search", response_model=list[LocationSearchResult])
def search_location_candidates(
    query: Annotated[str, Query(min_length=2)],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> list[dict[str, object]]:
    try:
        return geocoding_service.search_locations(query, count=limit)
    except geocoding_service.GeocodingError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Location search provider is unavailable. Try again shortly.",
        ) from exc


@app.get("/locations/{location_id}", response_model=LocationRead)
def get_location(location_id: int, db: DbSession) -> Location:
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return location


@app.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(location_id: int, db: DbSession) -> None:
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    db.delete(location)
    db.commit()


@app.post(
    "/locations/{location_id}/forecasts",
    response_model=ForecastCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_forecast(location_id: int, db: DbSession) -> ForecastSnapshotRead:
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    try:
        return create_forecast_snapshot(db, location)
    except WeatherProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Real forecast provider is unavailable. Try again shortly.",
        ) from exc


@app.get("/forecasts", response_model=list[ForecastSnapshotRead])
def list_forecasts(
    db: DbSession,
    location_id: Annotated[int | None, Query()] = None,
) -> list[ForecastSnapshotRead]:
    return list_forecast_snapshots(db, location_id=location_id)


@app.get("/forecasts/{snapshot_id}", response_model=ForecastSnapshotRead)
def read_forecast(snapshot_id: int, db: DbSession) -> ForecastSnapshotRead:
    snapshot = get_forecast_snapshot(db, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forecast not found")
    return snapshot


@app.get("/ingestion/raw-records", response_model=list[RawWeatherRecordRead])
def list_raw_weather_records(
    db: DbSession,
    location_id: Annotated[int | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 100,
) -> list[RawWeatherRecord]:
    statement = select(RawWeatherRecord).order_by(RawWeatherRecord.retrieval_time.desc())
    if location_id is not None:
        statement = statement.where(RawWeatherRecord.location_id == location_id)
    if source is not None:
        statement = statement.where(RawWeatherRecord.source == source)
    return list(db.scalars(statement.limit(limit)).all())


@app.get("/ingestion/providers", response_model=list[WeatherProviderRead])
def list_ingestion_providers() -> list[dict[str, str]]:
    providers = [
        forecast_service.FORECAST_PROVIDER,
        *forecast_service.ADDITIONAL_INGESTION_PROVIDERS,
    ]
    return [
        {
            "source": provider.source,
            "model": provider.model,
            "source_url": provider.source_url,
        }
        for provider in providers
    ]


@app.get("/normalization/records", response_model=list[NormalizedWeatherRecordRead])
def read_normalized_records(
    db: DbSession,
    location_id: Annotated[int | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
    quality_status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 100,
) -> list[NormalizedWeatherRecord]:
    return list_normalized_records(
        db,
        location_id=location_id,
        source=source,
        quality_status=quality_status,
        limit=limit,
    )


@app.get("/current-state/{location_id}", response_model=CurrentStateRead)
def read_current_state(location_id: int, db: DbSession) -> CurrentStateRead:
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return build_current_state(db, location)


@app.get("/weather/current/{location_id}", response_model=CurrentWeatherRead)
def read_current_weather(location_id: int, db: DbSession) -> dict[str, object]:
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    try:
        return current_weather_service.fetch_current_weather(location)
    except WeatherProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Current weather provider is unavailable. Try again shortly.",
        ) from exc


def _get_location_or_404(location_id: int, db: DbSession) -> Location:
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return location


@app.get("/forecast/layers/{location_id}", response_model=PhaseLayersRead)
def read_forecast_layers(location_id: int, db: DbSession) -> PhaseLayersRead:
    location = _get_location_or_404(location_id, db)
    return build_phase_layers(db, location)


@app.get(
    "/phase-layers/{location_id}",
    response_model=PhaseLayersRead,
    include_in_schema=False,
)
def read_phase_layers_alias(location_id: int, db: DbSession) -> PhaseLayersRead:
    return read_forecast_layers(location_id, db)


@app.post("/validation/run/{location_id}")
def run_validation(location_id: int, db: DbSession) -> dict[str, int]:
    location = _get_location_or_404(location_id, db)
    return {"created_records": validate_matured_forecasts(db, location)}


@app.get("/validation/report/{location_id}", response_model=Phase20ReportRead)
def read_validation_report(location_id: int, db: DbSession) -> Phase20ReportRead:
    location = _get_location_or_404(location_id, db)
    return build_phase20_report(db, location)


@app.get("/phase-20/{location_id}", response_model=Phase20ReportRead, include_in_schema=False)
def read_phase20_report_alias(location_id: int, db: DbSession) -> Phase20ReportRead:
    return read_validation_report(location_id, db)


@app.get("/predictions/history", response_model=list[PredictionHistoryItemRead])
def read_prediction_history(
    db: DbSession,
    location_id: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[PredictionHistoryItemRead]:
    return prediction_history(db, location_id=location_id, limit=limit)


@app.get("/predictions/{prediction_id}", response_model=list[PredictionHistoryItemRead])
def read_prediction(prediction_id: int, db: DbSession) -> list[PredictionHistoryItemRead]:
    prediction = prediction_detail(db, prediction_id)
    if not prediction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found")
    return prediction


@app.get("/errors", response_model=ErrorAnalysisRead)
def read_errors(
    db: DbSession,
    location_id: Annotated[int | None, Query()] = None,
) -> ErrorAnalysisRead:
    return error_analysis(db, location_id=location_id)


@app.get("/errors/{prediction_id}", response_model=ErrorAnalysisRead)
def read_prediction_errors(prediction_id: int, db: DbSession) -> ErrorAnalysisRead:
    return error_analysis(db, prediction_id=prediction_id)


@app.get("/accuracy/head-to-head", response_model=FairComparisonRead)
def read_head_to_head(
    db: DbSession,
    location_id: Annotated[int | None, Query()] = None,
) -> FairComparisonRead:
    return fair_comparison(db, location_id=location_id)


@app.get("/accuracy/calibration", response_model=VisualizationSummaryRead)
def read_calibration(
    location_id: int,
    db: DbSession,
) -> VisualizationSummaryRead:
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return visualization_summary(db, location)


@app.get("/models/performance", response_model=VisualizationSummaryRead)
def read_model_performance(
    location_id: int,
    db: DbSession,
) -> VisualizationSummaryRead:
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return visualization_summary(db, location)


@app.get("/models/versions")
def read_model_versions() -> list[dict[str, str]]:
    return [
        {
            "model_version": forecast_service.MODEL_VERSION,
            "feature_version": forecast_service.FEATURE_VERSION,
            "status": "production_first_pass",
        }
    ]


@app.get("/system/health", response_model=SystemHealthRead)
def read_system_health(
    db: DbSession,
    location_id: Annotated[int | None, Query()] = None,
) -> SystemHealthRead:
    return system_health(db, location_id=location_id)


@app.get("/forecast/transparency/{location_id}", response_model=TransparencyReportRead)
def read_forecast_transparency(
    location_id: int,
    db: DbSession,
    forecast_snapshot_id: Annotated[int | None, Query()] = None,
) -> TransparencyReportRead:
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return transparency_report(db, location, forecast_snapshot_id=forecast_snapshot_id)


@app.get("/scorecard", response_model=FinalScorecardRead)
def read_scorecard(
    db: DbSession,
    location_id: Annotated[int | None, Query()] = None,
) -> FinalScorecardRead:
    return final_scorecard(db, location_id=location_id)


@app.get("/api/catalog")
def read_api_catalog() -> list[str]:
    return api_catalog()


@app.get("/forecast/system-report/{location_id}", response_model=Phase35ReportRead)
def read_forecast_system_report(location_id: int, db: DbSession) -> Phase35ReportRead:
    location = _get_location_or_404(location_id, db)
    return phase35_report(db, location)


@app.get("/phase-35/{location_id}", response_model=Phase35ReportRead, include_in_schema=False)
def read_phase35_report_alias(location_id: int, db: DbSession) -> Phase35ReportRead:
    return read_forecast_system_report(location_id, db)
