import math
import statistics
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Location, NormalizedWeatherRecord
from app.schemas import (
    AnalogLayerRead,
    FeatureDatasetRead,
    HistoricalPatternLayerRead,
    LocationRead,
    MicroclimateLayerRead,
    NumericalModelLayerRead,
    PhaseLayersRead,
    WeatherRegimeRead,
)
from app.services.current_state_service import build_current_state

FEATURE_VERSION = "phase-10-feature-contract-v0"
FORECAST_SOURCES = {
    "Open-Meteo",
    "Open-Meteo GFS",
    "Open-Meteo ICON",
    "Open-Meteo ECMWF IFS",
    "National Weather Service",
}


def build_phase_layers(db: Session, location: Location) -> PhaseLayersRead:
    generated_at = datetime.now(UTC)
    current_state = build_current_state(db, location)
    current_temperature = _current_numeric(current_state.values, "temperature")
    numerical = _numerical_model_layer(db, location.id, generated_at)
    historical = _historical_pattern_layer(db, location.id, current_temperature)
    analog = _analog_layer()
    microclimate = _microclimate_layer(location)
    regime = _weather_regime(current_state.values, numerical)
    features = _feature_dataset(
        location=location,
        generated_at=generated_at,
        current_values=current_state.values,
        current_trends=current_state.trends.model_dump(),
        numerical=numerical,
        historical=historical,
        analog=analog,
        microclimate=microclimate,
        regime=regime,
    )
    return PhaseLayersRead(
        location=LocationRead.model_validate(location),
        generated_at=generated_at,
        numerical_model_layer=numerical,
        historical_pattern_layer=historical,
        analog_layer=analog,
        microclimate_layer=microclimate,
        weather_regime=regime,
        feature_dataset=features,
    )


def _numerical_model_layer(
    db: Session, location_id: int, generated_at: datetime
) -> NumericalModelLayerRead:
    sources = _forecast_sources(db, location_id)
    temperatures = _latest_values_by_source(db, location_id, "temperature")
    precip_probs = _latest_values_by_source(db, location_id, "precipitation_probability")
    winds = _latest_values_by_source(db, location_id, "wind_speed")
    pressures = _latest_values_by_source(db, location_id, "pressure")
    temp_values = list(temperatures.values())
    precip_values = list(precip_probs.values())

    return NumericalModelLayerRead(
        generated_at=generated_at,
        model_count=len(sources),
        sources=sources,
        model_temperature_mean_f=_mean(temp_values),
        model_temperature_median_f=_median(temp_values),
        model_temperature_std_f=_std(temp_values),
        model_precipitation_probability_mean_percent=_mean(precip_values),
        model_precipitation_agreement_percent=_agreement(precip_values),
        model_wind_mean_mph=_mean(list(winds.values())),
        model_pressure_mean_hpa=_mean(list(pressures.values())),
        ensemble_spread=_std(temp_values),
    )


def _historical_pattern_layer(
    db: Session,
    location_id: int,
    current_temperature: float | None,
) -> HistoricalPatternLayerRead:
    historical_records = list(
        db.execute(
            select(
                NormalizedWeatherRecord.normalized_variable,
                NormalizedWeatherRecord.normalized_value,
            )
            .where(NormalizedWeatherRecord.location_id == location_id)
            .where(NormalizedWeatherRecord.quality_status != "rejected")
            .where(NormalizedWeatherRecord.source == "Open-Meteo Historical")
            .where(NormalizedWeatherRecord.normalized_value.is_not(None))
        ).all()
    )
    highs = [
        value
        for record in historical_records
        for variable, value in [record]
        if variable == "daily_max_temperature" and value is not None
    ]
    lows = [
        value
        for record in historical_records
        for variable, value in [record]
        if variable == "daily_min_temperature" and value is not None
    ]
    precipitation_days = [
        value
        for record in historical_records
        for variable, value in [record]
        if variable == "precipitation_amount" and value is not None
    ]
    if highs and lows:
        daily_means = [(high + low) / 2 for high, low in zip(highs, lows, strict=False)]
        percentile = (
            None
            if current_temperature is None or not daily_means
            else round(
                sum(1 for value in daily_means if value <= current_temperature)
                / len(daily_means)
                * 100,
                1,
            )
        )
        rainy_days = sum(1 for value in precipitation_days if value >= 0.01)
        precipitation_probability = (
            None
            if not precipitation_days
            else round(rainy_days / len(precipitation_days) * 100, 1)
        )
        return HistoricalPatternLayerRead(
            status="ready",
            sample_size=len(historical_records),
            normal_high_temperature_f=_mean(highs),
            normal_low_temperature_f=_mean(lows),
            typical_precipitation_probability_percent=precipitation_probability,
            historical_temperature_percentile=percentile,
            note="Historical baseline uses Open-Meteo archive data for the same calendar window in prior years.",
        )

    return HistoricalPatternLayerRead(
        status="insufficient_data",
        sample_size=len(historical_records),
        note=(
            "Historical climatology requires a historical provider and multi-year records. "
            "No climatology is inferred from current forecasts."
        ),
    )


def _analog_layer() -> AnalogLayerRead:
    return AnalogLayerRead(
        status="insufficient_data",
        analog_count=0,
        analog_confidence_percent=0,
        analogs=[],
        note="Analog search is waiting for a historical atmospheric-state database.",
    )


def _microclimate_layer(location: Location) -> MicroclimateLayerRead:
    return MicroclimateLayerRead(
        latitude=location.latitude,
        longitude=location.longitude,
        elevation_m=location.elevation_m,
        learned_bias_status="insufficient_validation_history",
        estimated_features={
            "hemisphere": "north" if location.latitude >= 0 else "south",
            "absolute_latitude": round(abs(location.latitude), 4),
            "elevation_band": _elevation_band(location.elevation_m),
        },
        note="Learned local bias corrections require completed forecast-vs-observation history.",
    )


def _weather_regime(
    current_values: dict[str, Any], numerical: NumericalModelLayerRead
) -> WeatherRegimeRead:
    factors: list[str] = []
    temp = _current_numeric(current_values, "temperature")
    pressure = _current_numeric(current_values, "pressure")
    wind = _current_numeric(current_values, "wind_speed")
    precip_prob = numerical.model_precipitation_probability_mean_percent

    if wind is not None and wind >= 30:
        factors.append(f"Wind speed is elevated at {wind} mph.")
        return WeatherRegimeRead(regime="high_wind", confidence_percent=70, factors=factors)
    if precip_prob is not None and precip_prob >= 60:
        factors.append(f"Forecast precipitation probability mean is {precip_prob}%.")
        return WeatherRegimeRead(regime="rain_or_precipitation", confidence_percent=65, factors=factors)
    if temp is not None and temp >= 90:
        factors.append(f"Temperature is hot at {temp} F.")
        return WeatherRegimeRead(regime="heat", confidence_percent=68, factors=factors)
    if temp is not None and temp <= 20:
        factors.append(f"Temperature is cold at {temp} F.")
        return WeatherRegimeRead(regime="cold", confidence_percent=68, factors=factors)
    if pressure is not None and pressure >= 1018:
        factors.append(f"Pressure is relatively high at {pressure} hPa.")
        return WeatherRegimeRead(regime="stable_high_pressure", confidence_percent=62, factors=factors)

    factors.append("No strong precipitation, wind, heat, cold, or high-pressure signal dominates.")
    return WeatherRegimeRead(regime="stable_or_low_variability", confidence_percent=55, factors=factors)


def _feature_dataset(
    location: Location,
    generated_at: datetime,
    current_values: dict[str, Any],
    current_trends: dict[str, Any],
    numerical: NumericalModelLayerRead,
    historical: HistoricalPatternLayerRead,
    analog: AnalogLayerRead,
    microclimate: MicroclimateLayerRead,
    regime: WeatherRegimeRead,
) -> FeatureDatasetRead:
    hour = generated_at.hour
    day_of_year = generated_at.timetuple().tm_yday
    features: dict[str, Any] = {
        "temperature": _current_numeric(current_values, "temperature"),
        "dew_point": _current_numeric(current_values, "dew_point"),
        "humidity": _current_numeric(current_values, "relative_humidity"),
        "pressure": _current_numeric(current_values, "pressure"),
        "wind_speed": _current_numeric(current_values, "wind_speed"),
        "wind_direction": _current_numeric(current_values, "wind_direction"),
        "cloud_cover": _current_numeric(current_values, "cloud_cover"),
        "visibility": _current_numeric(current_values, "visibility"),
        **current_trends,
        "model_temperature_mean": numerical.model_temperature_mean_f,
        "model_temperature_median": numerical.model_temperature_median_f,
        "model_temperature_std": numerical.model_temperature_std_f,
        "model_precipitation_probability_mean": numerical.model_precipitation_probability_mean_percent,
        "model_precipitation_agreement": numerical.model_precipitation_agreement_percent,
        "model_wind_mean": numerical.model_wind_mean_mph,
        "model_pressure_mean": numerical.model_pressure_mean_hpa,
        "climatological_temperature": historical.normal_high_temperature_f,
        "historical_temperature_percentile": historical.historical_temperature_percentile,
        "analog_temperature": None,
        "analog_precipitation_probability": None,
        "analog_similarity": analog.analog_confidence_percent,
        "elevation": location.elevation_m,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "elevation_band": microclimate.estimated_features["elevation_band"],
        "hour": hour,
        "day_of_year": day_of_year,
        "month": generated_at.month,
        "season": _season(generated_at.month),
        "sin_hour": round(math.sin(2 * math.pi * hour / 24), 6),
        "cos_hour": round(math.cos(2 * math.pi * hour / 24), 6),
        "sin_day_of_year": round(math.sin(2 * math.pi * day_of_year / 366), 6),
        "cos_day_of_year": round(math.cos(2 * math.pi * day_of_year / 366), 6),
        "weather_regime": regime.regime,
    }
    wind_direction = features.get("wind_direction")
    if isinstance(wind_direction, int | float):
        features["sin_wind_direction"] = round(math.sin(2 * math.pi * wind_direction / 360), 6)
        features["cos_wind_direction"] = round(math.cos(2 * math.pi * wind_direction / 360), 6)
    return FeatureDatasetRead(
        feature_version=FEATURE_VERSION,
        generated_at=generated_at,
        features=features,
    )


def _forecast_sources(db: Session, location_id: int) -> list[str]:
    return sorted(
        db.scalars(
            select(NormalizedWeatherRecord.source)
            .where(NormalizedWeatherRecord.location_id == location_id)
            .where(NormalizedWeatherRecord.quality_status != "rejected")
            .where(NormalizedWeatherRecord.source.in_(FORECAST_SOURCES))
            .distinct()
        ).all()
    )


def _latest_values_by_source(db: Session, location_id: int, variable: str) -> dict[str, float]:
    latest: dict[str, float] = {}
    for source in FORECAST_SOURCES:
        value = db.scalar(
            select(NormalizedWeatherRecord.normalized_value)
            .where(NormalizedWeatherRecord.location_id == location_id)
            .where(NormalizedWeatherRecord.quality_status != "rejected")
            .where(NormalizedWeatherRecord.source == source)
            .where(NormalizedWeatherRecord.normalized_variable == variable)
            .where(NormalizedWeatherRecord.normalized_value.is_not(None))
            .order_by(NormalizedWeatherRecord.valid_time.desc())
            .limit(1)
        )
        if value is not None:
            latest[source] = value
    return latest


def _current_numeric(current_values: dict[str, Any], variable: str) -> float | None:
    current = current_values.get(variable)
    return None if current is None else current.value


def _mean(values: list[float]) -> float | None:
    return None if not values else round(statistics.fmean(values), 3)


def _median(values: list[float]) -> float | None:
    return None if not values else round(statistics.median(values), 3)


def _std(values: list[float]) -> float | None:
    return None if len(values) < 2 else round(statistics.pstdev(values), 3)


def _agreement(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    spread = max(values) - min(values)
    return round(max(0, 100 - spread * 5), 3)


def _elevation_band(elevation_m: float | None) -> str:
    if elevation_m is None:
        return "unknown"
    if elevation_m < 250:
        return "lowland"
    if elevation_m < 1000:
        return "upland"
    return "mountain"


def _season(month: int) -> str:
    if month in {12, 1, 2}:
        return "winter"
    if month in {3, 4, 5}:
        return "spring"
    if month in {6, 7, 8}:
        return "summer"
    return "fall"
