from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "weather_model.db"


class Settings(BaseSettings):
    app_name: str = "Weather Model API"
    database_url: str = Field(default_factory=lambda: f"sqlite:///{DEFAULT_DATABASE_PATH}")
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    cors_origin_regex: str | None = (
        r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|"
        r"10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+)(:\d+)?"
    )
    background_collection_enabled: bool = True
    background_collection_interval_minutes: int = Field(default=60, ge=5)
    background_collection_startup_delay_seconds: int = Field(default=10, ge=0)

    model_config = SettingsConfigDict(env_file=".env", env_prefix="WEATHER_")


@lru_cache
def get_settings() -> Settings:
    return Settings()
