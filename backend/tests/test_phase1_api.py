from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.database import Base, engine
from app.ingestion.providers import SourcePayload
from app.main import app
from app.services import forecast_service, geocoding_service


def fake_open_meteo_payload() -> dict:
    times = [f"2026-08-{15 + hour // 24:02d}T{hour % 24:02d}:00" for hour in range(192)]
    return {
        "hourly": {
            "time": times,
            "temperature_2m": [70 + (hour % 24) * 0.1 for hour in range(192)],
            "relative_humidity_2m": [55 for _ in range(192)],
            "dew_point_2m": [58 for _ in range(192)],
            "apparent_temperature": [71 for _ in range(192)],
            "precipitation_probability": [20 for _ in range(192)],
            "precipitation": [0 for _ in range(192)],
            "weather_code": [1 for _ in range(192)],
            "pressure_msl": [1014 for _ in range(192)],
            "cloud_cover": [35 for _ in range(192)],
            "visibility": [16093.44 for _ in range(192)],
            "wind_speed_10m": [8 for _ in range(192)],
            "wind_direction_10m": [220 for _ in range(192)],
            "wind_gusts_10m": [14 for _ in range(192)],
        },
        "daily": {
            "time": [f"2026-08-{15 + day:02d}" for day in range(8)],
            "temperature_2m_max": [78 for _ in range(8)],
            "temperature_2m_min": [64 for _ in range(8)],
        },
    }


def fake_nws_payload() -> dict:
    return {
        "points": {
            "properties": {
                "cwa": "LOT",
                "gridId": "LOT",
                "gridX": 75,
                "gridY": 73,
            }
        },
        "forecastHourly": {
            "properties": {
                "periods": [
                    {
                        "startTime": "2026-08-15T20:00:00+00:00",
                        "temperature": 72,
                        "probabilityOfPrecipitation": {"value": 30, "unitCode": "wmoUnit:percent"},
                        "dewpoint": {"value": 16.6, "unitCode": "wmoUnit:degC"},
                        "relativeHumidity": {"value": 61, "unitCode": "wmoUnit:percent"},
                        "windSpeed": "8 mph",
                        "windDirection": "SW",
                        "shortForecast": "Partly Cloudy",
                        "detailedForecast": "Partly cloudy.",
                    }
                ]
            }
        },
    }


def fake_metar_payload() -> dict:
    return {
        "records": [
            {
                "icaoId": "KORD",
                "obsTime": 1786823460,
                "reportTime": "2026-08-15T20:00:00.000Z",
                "temp": 23.3,
                "dewp": 15.5,
                "wdir": 190,
                "wspd": 8,
                "visib": "10+",
                "altim": 1018.1,
                "rawOb": "METAR KORD 152000Z 19008KT 10SM FEW060 23/16 A3007",
                "lat": 41.9786,
                "lon": -87.9048,
                "elev": 204,
                "fltCat": "VFR",
                "cover": "FEW",
            },
            {
                "icaoId": "KORD",
                "obsTime": 1786827060,
                "reportTime": "2026-08-15T21:00:00.000Z",
                "temp": 24.4,
                "dewp": 16.1,
                "wdir": 210,
                "wspd": 11,
                "visib": "10+",
                "altim": 1017.3,
                "rawOb": "METAR KORD 152100Z 21011KT 10SM FEW050 24/16 A3004",
                "lat": 41.9786,
                "lon": -87.9048,
                "elev": 204,
                "fltCat": "VFR",
                "cover": "FEW",
            }
        ],
        "station": "KORD",
        "station_distance_mi": 14.2,
    }


def fake_historical_payload() -> dict:
    return {
        "daily": {
            "time": [
                "2021-08-08",
                "2021-08-09",
                "2021-08-10",
                "2021-08-11",
                "2021-08-12",
            ],
            "temperature_2m_max": [75, 77, 79, 81, 83],
            "temperature_2m_min": [58, 60, 62, 64, 66],
            "precipitation_sum": [0, 0.02, 0, 0.3, 0],
        }
    }


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    forecast_service.fetch_forecast_source = lambda _: SourcePayload(
        source="Open-Meteo",
        model="best_match",
        source_url="https://api.open-meteo.com/v1/forecast",
        retrieved_at=datetime(2026, 8, 15, 20, tzinfo=UTC),
        payload=fake_open_meteo_payload(),
    )
    forecast_service.fetch_additional_ingestion_sources = lambda _: [
        SourcePayload(
            source="National Weather Service",
            model="official_hourly_forecast",
            source_url="https://api.weather.gov/gridpoints/LOT/75,73/forecast/hourly",
            retrieved_at=datetime(2026, 8, 15, 20, tzinfo=UTC),
            payload=fake_nws_payload(),
        ),
        SourcePayload(
            source="Aviation Weather Center METAR",
            model="airport_observation",
            source_url="https://aviationweather.gov/api/data/metar",
            retrieved_at=datetime(2026, 8, 15, 20, tzinfo=UTC),
            payload=fake_metar_payload(),
        ),
    ]


def test_create_location_and_forecast_snapshot() -> None:
    client = TestClient(app)

    location_response = client.post(
        "/locations",
        json={
            "name": "New York, NY",
            "latitude": 40.7128,
            "longitude": -74.006,
            "elevation_m": 10,
            "timezone": "America/New_York",
        },
    )
    assert location_response.status_code == 201
    location = location_response.json()

    forecast_response = client.post(f"/locations/{location['id']}/forecasts")
    assert forecast_response.status_code == 201
    forecast = forecast_response.json()

    assert forecast["location"]["name"] == "New York, NY"
    assert forecast["generator_kind"] == "open_meteo_forecast_api"
    assert [point["horizon"] for point in forecast["points"]] == [
        "1h",
        "3h",
        "6h",
        "12h",
        "24h",
        "48h",
        "72h",
        "5d",
        "7d",
    ]
    assert len(forecast["hourly_points"]) == 72
    assert "temperature_f" in forecast["points"][0]["temperature"]
    assert "probability_percent" in forecast["points"][0]["precipitation"]


def test_location_search_returns_geocoded_candidates(monkeypatch) -> None:
    client = TestClient(app)

    monkeypatch.setattr(
        geocoding_service,
        "search_locations",
        lambda query, count=8: [
            {
                "id": 4941935,
                "name": "Lexington, US",
                "display_name": "Lexington, US",
                "subtitle": "Massachusetts, Middlesex, United States",
                "latitude": 42.4473,
                "longitude": -71.2245,
                "elevation_m": 64,
                "timezone": "America/New_York",
                "population": 35000,
                "country": "United States",
                "country_code": "US",
                "admin1": "Massachusetts",
            }
        ],
    )

    response = client.get("/locations/search?query=Lexington")

    assert response.status_code == 200
    result = response.json()[0]
    assert result["name"] == "Lexington, US"
    assert result["latitude"] == 42.4473
    assert result["timezone"] == "America/New_York"


def test_forecast_snapshots_are_not_overwritten() -> None:
    client = TestClient(app)
    location = client.post(
        "/locations",
        json={"name": "Boston", "latitude": 42.36, "longitude": -71.05},
    ).json()

    first = client.post(f"/locations/{location['id']}/forecasts").json()
    second = client.post(f"/locations/{location['id']}/forecasts").json()
    forecasts = client.get(f"/forecasts?location_id={location['id']}").json()

    assert first["id"] != second["id"]
    assert len(forecasts) == 2


def test_forecast_creation_persists_raw_weather_records() -> None:
    client = TestClient(app)
    location = client.post(
        "/locations",
        json={"name": "Chicago", "latitude": 41.88, "longitude": -87.63},
    ).json()

    client.post(f"/locations/{location['id']}/forecasts")
    records = client.get(f"/ingestion/raw-records?location_id={location['id']}&limit=500").json()

    assert len(records) == 500
    assert all(record["source"] == "Open-Meteo" for record in records[:20])
    assert all(record["model"] == "best_match" for record in records[:20])
    assert {"forecast_valid_time", "retrieval_time", "variable", "value", "units"} <= set(
        records[0]
    )
    nws_records = client.get(
        f"/ingestion/raw-records?location_id={location['id']}"
        "&source=National%20Weather%20Service&limit=500"
    ).json()
    assert {record["variable"] for record in nws_records} == {
        "temperature",
        "probability_of_precipitation",
        "dewpoint",
        "relative_humidity",
        "wind_speed",
        "wind_direction",
        "short_forecast",
        "detailed_forecast",
    }
    metar_records = client.get(
        f"/ingestion/raw-records?location_id={location['id']}"
        "&source=Aviation%20Weather%20Center%20METAR&limit=500"
    ).json()
    assert {record["variable"] for record in metar_records} == {
        "temp",
        "dewp",
        "wdir",
        "wspd",
        "visib",
        "altim",
        "rawOb",
        "fltCat",
        "cover",
    }


def test_forecast_creation_normalizes_and_quality_scores_records() -> None:
    client = TestClient(app)
    location = client.post(
        "/locations",
        json={"name": "Chicago", "latitude": 41.88, "longitude": -87.63},
    ).json()

    client.post(f"/locations/{location['id']}/forecasts")
    normalized_records = client.get(
        f"/normalization/records?location_id={location['id']}"
        "&source=Aviation%20Weather%20Center%20METAR&limit=500"
    ).json()

    metar_temperature = max(
        (record for record in normalized_records if record["raw_variable"] == "temp"),
        key=lambda record: record["valid_time"],
    )
    assert metar_temperature["normalized_variable"] == "temperature"
    assert metar_temperature["normalized_units"] == "F"
    assert metar_temperature["normalized_value"] == 75.92
    assert metar_temperature["quality_status"] == "accepted"
    assert metar_temperature["quality_score"] == 1.0

    nws_dewpoint = client.get(
        f"/normalization/records?location_id={location['id']}"
        "&source=National%20Weather%20Service&limit=500"
    ).json()
    dewpoint = next(record for record in nws_dewpoint if record["raw_variable"] == "dewpoint")
    assert dewpoint["normalized_variable"] == "dew_point"
    assert dewpoint["normalized_units"] == "F"
    assert dewpoint["quality_status"] == "accepted"


def test_lists_configured_ingestion_providers() -> None:
    client = TestClient(app)

    providers = client.get("/ingestion/providers").json()

    assert providers == [
        {
            "source": "Open-Meteo",
            "model": "best_match",
            "source_url": "https://api.open-meteo.com/v1/forecast",
        },
        {
            "source": "National Weather Service",
            "model": "official_hourly_forecast",
            "source_url": "https://api.weather.gov",
        },
        {
            "source": "Aviation Weather Center METAR",
            "model": "airport_observation",
            "source_url": "https://aviationweather.gov/api/data/metar",
        },
        {
            "source": "Open-Meteo Historical",
            "model": "era5_reanalysis_daily",
            "source_url": "https://archive-api.open-meteo.com/v1/archive",
        },
    ]


def test_current_state_uses_normalized_observations_and_trends() -> None:
    client = TestClient(app)
    location = client.post(
        "/locations",
        json={"name": "Chicago", "latitude": 41.88, "longitude": -87.63},
    ).json()

    client.post(f"/locations/{location['id']}/forecasts")
    current_state = client.get(f"/current-state/{location['id']}").json()

    assert current_state["location"]["id"] == location["id"]
    assert current_state["values"]["temperature"]["source"] == "Aviation Weather Center METAR"
    assert current_state["values"]["temperature"]["value"] == 75.92
    assert current_state["values"]["pressure"]["units"] == "hPa"
    assert current_state["trends"]["temperature_change_1h_f"] == 1.98
    assert current_state["trends"]["wind_shift_degrees"] == 20
    assert current_state["evidence_record_count"] > 0


def test_phase_layers_builds_layers_through_phase_10() -> None:
    client = TestClient(app)
    forecast_service.fetch_additional_ingestion_sources = lambda _: [
        SourcePayload(
            source="National Weather Service",
            model="official_hourly_forecast",
            source_url="https://api.weather.gov/gridpoints/LOT/75,73/forecast/hourly",
            retrieved_at=datetime(2026, 8, 15, 20, tzinfo=UTC),
            payload=fake_nws_payload(),
        ),
        SourcePayload(
            source="Aviation Weather Center METAR",
            model="airport_observation",
            source_url="https://aviationweather.gov/api/data/metar",
            retrieved_at=datetime(2026, 8, 15, 20, tzinfo=UTC),
            payload=fake_metar_payload(),
        ),
        SourcePayload(
            source="Open-Meteo Historical",
            model="era5_reanalysis_daily",
            source_url="https://archive-api.open-meteo.com/v1/archive",
            retrieved_at=datetime(2026, 8, 15, 19, tzinfo=UTC),
            payload=fake_historical_payload(),
        ),
    ]
    location = client.post(
        "/locations",
        json={"name": "Chicago", "latitude": 41.88, "longitude": -87.63},
    ).json()

    client.post(f"/locations/{location['id']}/forecasts")
    layers = client.get(f"/phase-layers/{location['id']}").json()

    assert layers["location"]["id"] == location["id"]
    assert layers["numerical_model_layer"]["model_count"] >= 1
    assert layers["historical_pattern_layer"]["status"] == "ready"
    assert layers["historical_pattern_layer"]["normal_high_temperature_f"] == 79
    assert layers["historical_pattern_layer"]["normal_low_temperature_f"] == 62
    assert layers["historical_pattern_layer"]["typical_precipitation_probability_percent"] == 40
    assert layers["analog_layer"]["status"] == "insufficient_data"
    assert layers["weather_regime"]["regime"]
    assert layers["feature_dataset"]["feature_version"] == "phase-10-feature-contract-v0"
    assert "sin_hour" in layers["feature_dataset"]["features"]
    assert "temperature" in layers["feature_dataset"]["features"]


def test_phase20_report_exposes_validation_and_benchmark_contracts() -> None:
    client = TestClient(app)
    location = client.post(
        "/locations",
        json={"name": "Chicago", "latitude": 41.88, "longitude": -87.63},
    ).json()

    client.post(f"/locations/{location['id']}/forecasts")
    validation = client.post(f"/validation/run/{location['id']}").json()
    report = client.get(f"/phase-20/{location['id']}").json()

    assert validation["created_records"] >= 0
    assert report["location"]["id"] == location["id"]
    assert report["machine_learning_forecast"]["status"] in {
        "insufficient_training_data",
        "baseline_ready",
    }
    assert report["snapshot_integrity"]["immutable_snapshot_count"] == 1
    assert report["snapshot_integrity"]["frozen_feature_row_count"] == 1
    assert report["professional_benchmark"]["source"] == "National Weather Service"
    assert report["accuracy_metrics"]["sample_count"] >= 0
    assert report["skill_scores"][0]["baseline"] == "National Weather Service"
    assert report["statistical_significance"]["classification"] in {
        "OUTPERFORMING",
        "POSSIBLY OUTPERFORMING",
        "TIED / INCONCLUSIVE",
        "UNDERPERFORMING",
    }
    assert isinstance(report["segmented_performance"], list)


def test_phase35_completion_endpoints_expose_history_health_and_scorecard() -> None:
    client = TestClient(app)
    location = client.post(
        "/locations",
        json={"name": "Chicago", "latitude": 41.88, "longitude": -87.63},
    ).json()
    forecast = client.post(f"/locations/{location['id']}/forecasts").json()

    history = client.get(f"/predictions/history?location_id={location['id']}").json()
    detail = client.get(f"/predictions/{forecast['id']}").json()
    health = client.get(f"/system/health?location_id={location['id']}").json()
    scorecard = client.get(f"/scorecard?location_id={location['id']}").json()
    phase35 = client.get(f"/phase-35/{location['id']}").json()
    catalog = client.get("/api/catalog").json()

    assert history[0]["snapshot_id"] == forecast["id"]
    assert {item["horizon"] for item in detail} == {
        "1h",
        "3h",
        "6h",
        "12h",
        "24h",
        "48h",
        "72h",
        "5d",
        "7d",
    }
    assert health["status"] in {"GOOD", "DEGRADED", "FAILED"}
    assert scorecard["overall_conclusion"]
    assert phase35["phase_31_fair_comparison"]["rules"]
    assert phase35["phase_35_required_output"]["technology_stack"] == [
        "FastAPI",
        "SQLAlchemy",
        "SQLite",
        "Next.js",
        "TypeScript",
    ]
    assert "GET /phase-35/{location_id}" in catalog


def test_delete_location_removes_location_and_snapshots() -> None:
    client = TestClient(app)
    location = client.post(
        "/locations",
        json={"name": "Seattle", "latitude": 47.61, "longitude": -122.33},
    ).json()
    snapshot = client.post(f"/locations/{location['id']}/forecasts").json()

    delete_response = client.delete(f"/locations/{location['id']}")

    assert delete_response.status_code == 204
    assert client.get(f"/locations/{location['id']}").status_code == 404
    assert client.get(f"/forecasts/{snapshot['id']}").status_code == 404
