from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    elevation_m: Mapped[float | None] = mapped_column(Float)
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    forecasts: Mapped[list["ForecastSnapshot"]] = relationship(
        back_populates="location", cascade="all, delete-orphan"
    )
    raw_weather_records: Mapped[list["RawWeatherRecord"]] = relationship(
        back_populates="location", cascade="all, delete-orphan"
    )
    feature_snapshots: Mapped[list["FeatureSnapshot"]] = relationship(
        back_populates="location", cascade="all, delete-orphan"
    )
    validation_records: Mapped[list["ForecastValidationRecord"]] = relationship(
        back_populates="location", cascade="all, delete-orphan"
    )


class ForecastSnapshot(Base):
    __tablename__ = "forecast_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)
    forecast_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_cutoff_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(80), nullable=False)
    training_data_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generator_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)

    location: Mapped[Location] = relationship(back_populates="forecasts")
    feature_snapshots: Mapped[list["FeatureSnapshot"]] = relationship(
        back_populates="forecast_snapshot", cascade="all, delete-orphan"
    )
    validation_records: Mapped[list["ForecastValidationRecord"]] = relationship(
        back_populates="forecast_snapshot", cascade="all, delete-orphan"
    )


class RawWeatherRecord(Base):
    __tablename__ = "raw_weather_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    forecast_initialization_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    forecast_valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retrieval_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)
    location_name: Mapped[str] = mapped_column(String(120), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    elevation_m: Mapped[float | None] = mapped_column(Float)
    variable: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(120), nullable=False)
    units: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    location: Mapped[Location] = relationship(back_populates="raw_weather_records")
    normalized_record: Mapped["NormalizedWeatherRecord | None"] = relationship(
        back_populates="raw_record", cascade="all, delete-orphan"
    )


class NormalizedWeatherRecord(Base):
    __tablename__ = "normalized_weather_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    raw_record_id: Mapped[int] = mapped_column(
        ForeignKey("raw_weather_records.id"), nullable=False, unique=True, index=True
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_variable: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    normalized_variable: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    raw_value: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_value: Mapped[float | None] = mapped_column(Float)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    normalized_units: Mapped[str] = mapped_column(String(40), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    quality_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    raw_record: Mapped[RawWeatherRecord] = relationship(back_populates="normalized_record")


class FeatureSnapshot(Base):
    __tablename__ = "feature_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    forecast_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("forecast_snapshots.id"), nullable=False, index=True
    )
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    freeze_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    location: Mapped[Location] = relationship(back_populates="feature_snapshots")
    forecast_snapshot: Mapped[ForecastSnapshot] = relationship(back_populates="feature_snapshots")


class ForecastValidationRecord(Base):
    __tablename__ = "forecast_validation_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    forecast_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("forecast_snapshots.id"), nullable=False, index=True
    )
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)
    horizon: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    forecast_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast_valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observation_source: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    variable: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    predicted_value: Mapped[float] = mapped_column(Float, nullable=False)
    observed_value: Mapped[float] = mapped_column(Float, nullable=False)
    error: Mapped[float] = mapped_column(Float, nullable=False)
    absolute_error: Mapped[float] = mapped_column(Float, nullable=False)
    squared_error: Mapped[float] = mapped_column(Float, nullable=False)
    benchmark_source: Mapped[str | None] = mapped_column(String(120), index=True)
    benchmark_value: Mapped[float | None] = mapped_column(Float)
    benchmark_error: Mapped[float | None] = mapped_column(Float)
    benchmark_absolute_error: Mapped[float | None] = mapped_column(Float)
    weather_regime: Mapped[str | None] = mapped_column(String(80), index=True)
    segment_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    location: Mapped[Location] = relationship(back_populates="validation_records")
    forecast_snapshot: Mapped[ForecastSnapshot] = relationship(back_populates="validation_records")
