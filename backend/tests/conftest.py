import os
from pathlib import Path

TEST_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "weather_model_test.db"

os.environ.setdefault("WEATHER_DATABASE_URL", f"sqlite:///{TEST_DATABASE_PATH}")
