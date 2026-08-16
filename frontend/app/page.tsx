"use client";

import {
  Activity,
  AlertTriangle,
  Archive,
  BadgeCheck,
  Cloud,
  CloudFog,
  CloudRain,
  CloudSnow,
  CloudSun,
  Database,
  Droplets,
  Eye,
  Filter,
  Gauge,
  Loader2,
  MapPin,
  Navigation,
  Plus,
  RadioTower,
  RefreshCw,
  Snowflake,
  Sun,
  Thermometer,
  TrendingUp,
  Trash2,
  Umbrella,
  Wind,
  X
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const SELECTED_LOCATION_STORAGE_KEY = "weather-model:selected-location-id";

type Location = {
  id: number;
  name: string;
  latitude: number;
  longitude: number;
  elevation_m: number | null;
  timezone: string;
  created_at: string;
};

type LocationSearchResult = {
  id: number | null;
  name: string;
  display_name: string;
  subtitle: string;
  latitude: number;
  longitude: number;
  elevation_m: number | null;
  timezone: string;
  population: number | null;
  country: string | null;
  country_code: string | null;
  admin1: string | null;
};

type ForecastPoint = {
  horizon: string;
  horizon_hours: number;
  forecast_valid_at: string;
  confidence_percent: number;
  temperature: {
    temperature_f: number;
    apparent_temperature_f: number;
    daily_max_f: number | null;
    daily_min_f: number | null;
    dew_point_f: number;
    likely_low_f: number;
    likely_high_f: number;
  };
  precipitation: {
    probability_percent: number;
    amount_in: number;
    precipitation_type: string;
    start_time: string | null;
    end_time: string | null;
    intensity: string;
  };
  wind: {
    sustained_speed_mph: number;
    direction_degrees: number;
    max_gust_mph: number;
  };
  atmosphere: {
    relative_humidity_percent: number;
    pressure_hpa: number;
    pressure_trend: string;
    cloud_cover_percent: number;
    visibility_mi: number;
  };
  notable_weather: Record<string, number>;
};

type ForecastSnapshot = {
  id: number;
  location: Location;
  forecast_created_at: string;
  data_cutoff_time: string;
  model_version: string;
  feature_version: string;
  training_data_cutoff: string | null;
  generator_kind: string;
  raw_record_count: number;
  points: ForecastPoint[];
  hourly_points: ForecastPoint[];
};

type WeatherProvider = {
  source: string;
  model: string;
  source_url: string;
};

type BackgroundCollectionStatus = {
  enabled: boolean;
  running: boolean;
  interval_seconds: number;
  last_started_at: string | null;
  last_finished_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  last_location_count: number;
  last_forecast_snapshot_count: number;
  last_validation_record_count: number;
  last_errors: string[];
};

type RawWeatherRecord = {
  id: number;
  source: string;
  model: string;
  forecast_valid_time: string;
  retrieval_time: string;
  location_id: number;
  location_name: string;
  variable: string;
  value: string;
  units: string;
};

type NormalizedWeatherRecord = {
  id: number;
  raw_record_id: number;
  source: string;
  normalized_variable: string;
  normalized_value: number | null;
  normalized_text: string | null;
  normalized_units: string;
  quality_status: string;
  quality_score: number;
  quality_reason: string;
};

type CurrentStateValue = {
  value: number | null;
  text: string | null;
  units: string;
  source: string;
  valid_time: string;
  quality_score: number;
};

type CurrentState = {
  generated_at: string;
  data_cutoff_time: string | null;
  values: Record<string, CurrentStateValue>;
  trends: Record<string, number | string | null>;
  evidence_record_count: number;
};

type PhaseLayers = {
  numerical_model_layer: {
    model_count: number;
    sources: string[];
    model_temperature_mean_f: number | null;
    model_temperature_std_f: number | null;
    model_precipitation_agreement_percent: number | null;
  };
  historical_pattern_layer: {
    status: string;
    sample_size: number;
    note: string;
  };
  analog_layer: {
    status: string;
    analog_count: number;
    analog_confidence_percent: number;
    note: string;
  };
  microclimate_layer: {
    elevation_m: number | null;
    learned_bias_status: string;
    estimated_features: Record<string, string | number | null>;
  };
  weather_regime: {
    regime: string;
    confidence_percent: number;
    factors: string[];
  };
  feature_dataset: {
    feature_version: string;
    features: Record<string, string | number | null>;
  };
};

type Phase20Report = {
  machine_learning_forecast: {
    status: string;
    algorithm: string;
    training_sample_count: number;
    temperature_prediction_f: number | null;
  };
  ensemble: {
    status: string;
    weights: Record<string, number>;
    temperature_prediction_f: number | null;
    precipitation_probability_percent: number | null;
  };
  confidence: {
    status: string;
    sample_count: number;
    calibration_error: number | null;
  };
  snapshot_integrity: {
    immutable_snapshot_count: number;
    frozen_feature_row_count: number;
    unresolved_forecast_count: number;
  };
  professional_benchmark: {
    source: string;
    archived_record_count: number;
    comparable_validation_count: number;
    status: string;
  };
  ground_truth: {
    observation_source_count: number;
    validated_record_count: number;
    latest_observation_time: string | null;
  };
  accuracy_metrics: {
    sample_count: number;
    temperature_mae_f: number | null;
    temperature_rmse_f: number | null;
    temperature_bias_f: number | null;
  };
  skill_scores: Array<{
    baseline: string;
    variable: string;
    sample_count: number;
    skill_score: number | null;
    interpretation: string;
  }>;
  statistical_significance: {
    sample_count: number;
    classification: string;
    mean_error_difference: number | null;
  };
  segmented_performance: Array<{
    segment_type: string;
    segment: string;
    sample_count: number;
    temperature_mae_f: number | null;
    skill_score: number | null;
  }>;
};

type Phase35Report = {
  phase_21_error_analysis: {
    sample_count: number;
    failure_categories: Record<string, number>;
  };
  phase_25_visualizations: {
    rolling_mae: Record<string, number | null>;
    performance_matrix: Array<Record<string, string | number | null>>;
  };
  phase_29_data_quality_monitoring: {
    status: string;
    validation_backlog: number;
    missing_models: string[];
  };
  phase_30_transparency: {
    explanation: string;
    missing_data: string[];
  };
  phase_31_fair_comparison: {
    qualifying_pair_count: number;
    model_wins: number;
    professional_wins: number;
    ties: number;
    conclusion: string;
  };
  phase_33_final_scorecard: {
    forecasts_evaluated: number;
    evaluation_period: string;
    overall_conclusion: string;
  };
};

const defaultLocation = {
  name: "New York, NY",
  latitude: "40.7128",
  longitude: "-74.0060",
  elevation_m: "10",
  timezone: "America/New_York"
};

type LocationForm = typeof defaultLocation;

function formatDate(value: string) {
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value);
  const date = new Date(hasTimezone ? value : `${value}Z`);

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    timeZoneName: "short"
  }).format(date);
}

function formatValue(value?: CurrentStateValue) {
  if (!value) return "No data";
  const displayValue = value.value ?? value.text;
  return `${displayValue} ${value.units}`.trim();
}

function formatTrend(value: number | string | null | undefined, suffix = "") {
  if (value === null || value === undefined) return "No data";
  if (typeof value === "number" && value > 0) return `+${value}${suffix}`;
  return `${value}${suffix}`;
}

function formatMetric(value: number | null | undefined, suffix = "") {
  if (value === null || value === undefined) return "No data";
  return `${value}${suffix}`;
}

function conditionLabel(point: ForecastPoint) {
  if (point.notable_weather.thunderstorms_percent >= 30) return "Storm risk";
  if (point.precipitation.precipitation_type === "snow") return "Snow";
  if (point.precipitation.precipitation_type === "sleet") return "Sleet";
  if (point.precipitation.precipitation_type === "freezing_rain") return "Freezing rain";
  if (point.precipitation.probability_percent >= 45) return "Rain likely";
  if (point.atmosphere.visibility_mi < 3) return "Low visibility";
  if (point.atmosphere.cloud_cover_percent >= 70) return "Cloudy";
  if (point.atmosphere.cloud_cover_percent >= 35) return "Partly cloudy";
  return "Mostly clear";
}

function barWidth(value: number, max = 100) {
  return `${Math.max(0, Math.min(100, (value / max) * 100))}%`;
}

function WeatherIcon({ point, size = 26 }: { point: ForecastPoint; size?: number }) {
  if (point.notable_weather.thunderstorms_percent >= 30) return <CloudRain size={size} />;
  if (point.precipitation.precipitation_type === "snow") return <CloudSnow size={size} />;
  if (point.precipitation.precipitation_type === "sleet") return <Snowflake size={size} />;
  if (point.precipitation.precipitation_type === "freezing_rain") return <Snowflake size={size} />;
  if (point.precipitation.probability_percent >= 45) return <CloudRain size={size} />;
  if (point.atmosphere.visibility_mi < 3) return <CloudFog size={size} />;
  if (point.atmosphere.cloud_cover_percent >= 70) return <Cloud size={size} />;
  if (point.atmosphere.cloud_cover_percent >= 35) return <CloudSun size={size} />;
  return <Sun size={size} />;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers
    }
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

function AddLocationDialog({
  loading,
  onClose,
  onCreate
}: {
  loading: boolean;
  onClose: () => void;
  onCreate: (form: LocationForm) => void;
}) {
  const [form, setForm] = useState<LocationForm>(defaultLocation);
  const [locationQuery, setLocationQuery] = useState("");
  const [locationSearchResults, setLocationSearchResults] = useState<LocationSearchResult[]>([]);
  const [locationSearchLoading, setLocationSearchLoading] = useState(false);

  useEffect(() => {
    const query = locationQuery.trim();
    if (query.length < 2) return;

    let isActive = true;
    const timeout = window.setTimeout(() => {
      setLocationSearchLoading(true);
      api<LocationSearchResult[]>(
        `/locations/search?query=${encodeURIComponent(query)}&limit=6`
      )
        .then((results) => {
          if (isActive) setLocationSearchResults(results);
        })
        .catch(() => {
          if (isActive) setLocationSearchResults([]);
        })
        .finally(() => {
          if (isActive) setLocationSearchLoading(false);
        });
    }, 250);

    return () => {
      isActive = false;
      window.clearTimeout(timeout);
    };
  }, [locationQuery]);

  function handleLocationSearchChange(value: string) {
    setLocationQuery(value);
    if (value.trim().length < 2) {
      setLocationSearchResults([]);
      setLocationSearchLoading(false);
    }
  }

  function applyLocationSearchResult(result: LocationSearchResult) {
    setForm({
      name: result.display_name,
      latitude: String(result.latitude),
      longitude: String(result.longitude),
      elevation_m: result.elevation_m === null ? "" : String(result.elevation_m),
      timezone: result.timezone
    });
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onCreate(form);
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        aria-labelledby="add-location-title"
        aria-modal="true"
        className="dialog"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div className="dialog-header">
          <div>
            <h2 id="add-location-title">Add Location</h2>
          </div>
          <button
            aria-label="Close add location dialog"
            className="icon-button"
            onClick={onClose}
            title="Close"
            type="button"
          >
            <X size={17} />
          </button>
        </div>
        <form className="form-grid" onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="location-search">Search city or place</label>
            <div className="search-input-shell">
              <MapPin size={17} />
              <input
                autoComplete="off"
                autoFocus
                id="location-search"
                onChange={(event) => handleLocationSearchChange(event.target.value)}
                placeholder="Boston, Lexington MA, Tokyo..."
                value={locationQuery}
              />
              {locationSearchLoading ? <Loader2 className="spin" size={17} /> : null}
            </div>
            {locationQuery.trim().length >= 2 ? (
              <div className="search-results">
                {locationSearchResults.map((result) => {
                  const isSelected =
                    form.latitude === String(result.latitude) &&
                    form.longitude === String(result.longitude);
                  return (
                    <button
                      className={`search-result ${isSelected ? "active" : ""}`}
                      key={`${result.id ?? result.display_name}-${result.latitude}-${result.longitude}`}
                      onClick={() => applyLocationSearchResult(result)}
                      type="button"
                    >
                      <span className="search-result-icon">
                        <MapPin size={16} />
                      </span>
                      <span>
                        <strong>{result.display_name}</strong>
                        <small>{result.subtitle || result.timezone}</small>
                      </span>
                    </button>
                  );
                })}
                {!locationSearchLoading && locationSearchResults.length === 0 ? (
                  <p className="search-empty">No matches yet. Try a city and state or country.</p>
                ) : null}
              </div>
            ) : (
              <p className="field-hint">Type at least 2 letters, then choose a match.</p>
            )}
          </div>
          <div className="field">
            <label htmlFor="name">Name</label>
            <input
              id="name"
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              required
              value={form.name}
            />
          </div>
          <div className="form-columns">
            <div className="field">
              <label htmlFor="latitude">Latitude</label>
              <input
                id="latitude"
                max="90"
                min="-90"
                onChange={(event) => setForm({ ...form, latitude: event.target.value })}
                required
                step="any"
                type="number"
                value={form.latitude}
              />
            </div>
            <div className="field">
              <label htmlFor="longitude">Longitude</label>
              <input
                id="longitude"
                max="180"
                min="-180"
                onChange={(event) => setForm({ ...form, longitude: event.target.value })}
                required
                step="any"
                type="number"
                value={form.longitude}
              />
            </div>
          </div>
          <div className="form-columns">
            <div className="field">
              <label htmlFor="elevation">Elevation m</label>
              <input
                id="elevation"
                onChange={(event) => setForm({ ...form, elevation_m: event.target.value })}
                step="any"
                type="number"
                value={form.elevation_m}
              />
            </div>
            <div className="field">
              <label htmlFor="timezone">Timezone</label>
              <input
                id="timezone"
                onChange={(event) => setForm({ ...form, timezone: event.target.value })}
                required
                value={form.timezone}
              />
            </div>
          </div>
          <div className="actions end">
            <button
              className="secondary-button"
              disabled={loading}
              onClick={onClose}
              type="button"
            >
              Cancel
            </button>
            <button className="primary-button" disabled={loading} type="submit">
              {loading ? <Loader2 className="spin" size={17} /> : <Plus size={17} />}
              Add
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

export default function Home() {
  const [locations, setLocations] = useState<Location[]>([]);
  const [providers, setProviders] = useState<WeatherProvider[]>([]);
  const [collectionStatus, setCollectionStatus] = useState<BackgroundCollectionStatus | null>(
    null
  );
  const [rawRecords, setRawRecords] = useState<RawWeatherRecord[]>([]);
  const [normalizedRecords, setNormalizedRecords] = useState<NormalizedWeatherRecord[]>([]);
  const [currentState, setCurrentState] = useState<CurrentState | null>(null);
  const [phaseLayers, setPhaseLayers] = useState<PhaseLayers | null>(null);
  const [phase20Report, setPhase20Report] = useState<Phase20Report | null>(null);
  const [phase35Report, setPhase35Report] = useState<Phase35Report | null>(null);
  const [selectedLocationId, setSelectedLocationId] = useState<number | null>(null);
  const [forecast, setForecast] = useState<ForecastSnapshot | null>(null);
  const [isAddLocationOpen, setIsAddLocationOpen] = useState(false);
  const [apiLoading, setApiLoading] = useState(false);
  const [validationLoading, setValidationLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedLocation = useMemo(
    () => locations.find((location) => location.id === selectedLocationId) ?? null,
    [locations, selectedLocationId]
  );

  useEffect(() => {
    api<Location[]>("/locations")
      .then((items) => {
        setLocations(items);
        const savedLocationId = Number(
          window.localStorage.getItem(SELECTED_LOCATION_STORAGE_KEY)
        );
        const savedLocation = items.find((location) => location.id === savedLocationId);
        if (savedLocation?.id ?? items[0]?.id) setApiLoading(true);
        setSelectedLocationId(savedLocation?.id ?? items[0]?.id ?? null);
      })
      .catch(() => setError("Start the FastAPI backend to load saved locations."));

    api<WeatherProvider[]>("/ingestion/providers")
      .then(setProviders)
      .catch(() => setProviders([]));

    api<BackgroundCollectionStatus>("/collection/status")
      .then(setCollectionStatus)
      .catch(() => setCollectionStatus(null));
  }, []);

  useEffect(() => {
    const interval = window.setInterval(() => {
      api<BackgroundCollectionStatus>("/collection/status")
        .then(setCollectionStatus)
        .catch(() => setCollectionStatus(null));
    }, 30000);

    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!selectedLocationId) {
      return;
    }

    let isActive = true;

    const refresh = async () => {
      const [
        forecastResult,
        rawResult,
        normalizedResult,
        currentResult,
        phaseLayersResult,
        phase20Result,
        phase35Result
      ] = await Promise.allSettled([
        api<ForecastSnapshot[]>(`/forecasts?location_id=${selectedLocationId}`),
        api<RawWeatherRecord[]>(`/ingestion/raw-records?location_id=${selectedLocationId}&limit=12`),
        api<NormalizedWeatherRecord[]>(
          `/normalization/records?location_id=${selectedLocationId}&limit=12`
        ),
        api<CurrentState>(`/current-state/${selectedLocationId}`),
        api<PhaseLayers>(`/forecast/layers/${selectedLocationId}`),
        api<Phase20Report>(`/validation/report/${selectedLocationId}`),
        api<Phase35Report>(`/forecast/system-report/${selectedLocationId}`)
      ]);

      if (!isActive) return;

      setForecast(forecastResult.status === "fulfilled" ? forecastResult.value[0] ?? null : null);
      setRawRecords(rawResult.status === "fulfilled" ? rawResult.value : []);
      setNormalizedRecords(
        normalizedResult.status === "fulfilled" ? normalizedResult.value : []
      );
      setCurrentState(currentResult.status === "fulfilled" ? currentResult.value : null);
      setPhaseLayers(
        phaseLayersResult.status === "fulfilled" ? phaseLayersResult.value : null
      );
      setPhase20Report(phase20Result.status === "fulfilled" ? phase20Result.value : null);
      setPhase35Report(phase35Result.status === "fulfilled" ? phase35Result.value : null);
      setApiLoading(false);
    };

    refresh();

    return () => {
      isActive = false;
    };
  }, [selectedLocationId]);

  function clearLocationDetails() {
    setForecast(null);
    setRawRecords([]);
    setNormalizedRecords([]);
    setCurrentState(null);
    setPhaseLayers(null);
    setPhase20Report(null);
    setPhase35Report(null);
  }

  function handleSelectLocation(locationId: number) {
    if (locationId === selectedLocationId) return;
    clearLocationDetails();
    setError(null);
    setApiLoading(true);
    window.localStorage.setItem(SELECTED_LOCATION_STORAGE_KEY, String(locationId));
    setSelectedLocationId(locationId);
  }

  async function handleCreateLocation(form: LocationForm) {
    setError(null);
    setLoading(true);

    try {
      const location = await api<Location>("/locations", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          latitude: Number(form.latitude),
          longitude: Number(form.longitude),
          elevation_m: form.elevation_m === "" ? null : Number(form.elevation_m),
          timezone: form.timezone
        })
      });
      setLocations((current) => [...current, location].sort((a, b) => a.name.localeCompare(b.name)));
      window.localStorage.setItem(SELECTED_LOCATION_STORAGE_KEY, String(location.id));
      setApiLoading(true);
      setSelectedLocationId(location.id);
      clearLocationDetails();
      setIsAddLocationOpen(false);
    } catch {
      setError("Location could not be created. Check the values and API connection.");
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateForecast() {
    if (!selectedLocationId) return;
    setError(null);
    setLoading(true);

    try {
      const snapshot = await api<ForecastSnapshot>(`/locations/${selectedLocationId}/forecasts`, {
        method: "POST"
      });
      setForecast(snapshot);
      const records = await api<RawWeatherRecord[]>(
        `/ingestion/raw-records?location_id=${selectedLocationId}&limit=12`
      );
      const normalized = await api<NormalizedWeatherRecord[]>(
        `/normalization/records?location_id=${selectedLocationId}&limit=12`
      );
      const state = await api<CurrentState>(`/current-state/${selectedLocationId}`);
      const layers = await api<PhaseLayers>(`/forecast/layers/${selectedLocationId}`);
      const phase20 = await api<Phase20Report>(`/validation/report/${selectedLocationId}`);
      const phase35 = await api<Phase35Report>(`/forecast/system-report/${selectedLocationId}`);
      setRawRecords(records);
      setNormalizedRecords(normalized);
      setCurrentState(state);
      setPhaseLayers(layers);
      setPhase20Report(phase20);
      setPhase35Report(phase35);
      api<BackgroundCollectionStatus>("/collection/status")
        .then(setCollectionStatus)
        .catch(() => setCollectionStatus(null));
    } catch {
      setError("Forecast snapshot could not be generated.");
    } finally {
      setLoading(false);
    }
  }

  async function handleRunValidation() {
    if (!selectedLocationId) return;
    setError(null);
    setValidationLoading(true);

    try {
      await api<{ created_records: number }>(`/validation/run/${selectedLocationId}`, {
        method: "POST"
      });
      const phase20 = await api<Phase20Report>(`/validation/report/${selectedLocationId}`);
      const phase35 = await api<Phase35Report>(`/forecast/system-report/${selectedLocationId}`);
      setPhase20Report(phase20);
      setPhase35Report(phase35);
      api<BackgroundCollectionStatus>("/collection/status")
        .then(setCollectionStatus)
        .catch(() => setCollectionStatus(null));
    } catch {
      setError("Validation could not be run yet. Forecasts must be old enough to compare with observations.");
    } finally {
      setValidationLoading(false);
    }
  }

  async function handleDeleteLocation(location: Location) {
    const confirmed = window.confirm(
      `Remove ${location.name}? Forecast snapshots for this location will also be removed.`
    );
    if (!confirmed) return;

    setError(null);
    setLoading(true);

    try {
      await api<void>(`/locations/${location.id}`, { method: "DELETE" });
      setLocations((current) => {
        const nextLocations = current.filter((item) => item.id !== location.id);
        if (selectedLocationId === location.id) {
          const nextSelectedId = nextLocations[0]?.id ?? null;
          if (nextSelectedId) {
            window.localStorage.setItem(SELECTED_LOCATION_STORAGE_KEY, String(nextSelectedId));
          } else {
            window.localStorage.removeItem(SELECTED_LOCATION_STORAGE_KEY);
            setApiLoading(false);
          }
          if (nextSelectedId) setApiLoading(true);
          setSelectedLocationId(nextSelectedId);
          clearLocationDetails();
        }
        return nextLocations;
      });
    } catch {
      setError("Location could not be removed.");
    } finally {
      setLoading(false);
    }
  }

  function closeAddLocationDialog() {
    setIsAddLocationOpen(false);
  }

  const leadPoint = forecast?.points[0];
  const rawSources = Array.from(new Set(rawRecords.map((record) => record.source)));
  const acceptedCount = normalizedRecords.filter(
    (record) => record.quality_status === "accepted"
  ).length;
  const flaggedCount = normalizedRecords.length - acceptedCount;
  const currentTemperature = currentState?.values.temperature;
  const currentPressure = currentState?.values.pressure;
  const currentWind = currentState?.values.wind_speed;
  const currentVisibility = currentState?.values.visibility;
  const featureCount = phaseLayers
    ? Object.keys(phaseLayers.feature_dataset.features).length
    : 0;
  const primarySkill = phase20Report?.skill_scores[0];
  const topSegments = phase20Report?.segmented_performance.slice(0, 5) ?? [];
  const hourlyPreview = forecast?.hourly_points.slice(0, 18) ?? [];
  const hourlyTemperatures = hourlyPreview.map((point) => point.temperature.temperature_f);
  const hourlyMin = Math.min(...hourlyTemperatures, leadPoint?.temperature.temperature_f ?? 0);
  const hourlyMax = Math.max(...hourlyTemperatures, leadPoint?.temperature.temperature_f ?? 0);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">
            <CloudSun size={22} />
          </span>
          <div>
            <h1>Weather Model</h1>
            <p>Real-data ingestion and frozen forecast snapshots</p>
          </div>
        </div>
      </header>

      <div className="main-grid">
        <aside className="panel sidebar">
          <section>
            <div className="section-title split">
              <span className="title-label">
                <MapPin size={18} />
                <h2>Locations</h2>
              </span>
              <button
                aria-label="Add location"
                className="icon-button"
                onClick={() => setIsAddLocationOpen(true)}
                title="Add location"
                type="button"
              >
                <Plus size={17} />
              </button>
            </div>
            <div className="location-list">
              {locations.map((location) => (
                <div
                  className={`location-row ${selectedLocationId === location.id ? "active" : ""}`}
                  key={location.id}
                >
                  <button
                    className="location-button"
                    onClick={() => handleSelectLocation(location.id)}
                    type="button"
                  >
                    <MapPin size={17} />
                    <strong>
                      {location.name}
                      <span>
                        {location.latitude.toFixed(3)}, {location.longitude.toFixed(3)}
                      </span>
                    </strong>
                  </button>
                  <button
                    aria-label={`Remove ${location.name}`}
                    className="icon-button danger"
                    disabled={loading}
                    onClick={() => handleDeleteLocation(location)}
                    title={`Remove ${location.name}`}
                    type="button"
                  >
                    <Trash2 size={17} />
                  </button>
                </div>
              ))}
            </div>
          </section>
        </aside>

        <section className="content">
          {error ? <div className="error">{error}</div> : null}

          <section className="status-grid">
            <div className="status-panel">
              <span className="status-icon">
                <BadgeCheck size={18} />
              </span>
              <div>
                <strong>Forecast System</strong>
                <p>Real data collection, frozen snapshots, validation, benchmarking, transparency, monitoring, and scorecards are enabled.</p>
              </div>
            </div>
            <div className="status-panel">
              <span className="status-icon">
                <RadioTower size={18} />
              </span>
              <div>
                <strong>{providers.length} Providers</strong>
                <p>{providers.map((provider) => provider.source).join(", ") || "Provider list unavailable"}</p>
              </div>
            </div>
            <div className="status-panel">
              <span className="status-icon">
                {collectionStatus?.running ? (
                  <Loader2 className="spin" size={18} />
                ) : (
                  <Activity size={18} />
                )}
              </span>
              <div>
                <strong>
                  Auto Collection {collectionStatus?.enabled === false ? "Off" : "On"}
                </strong>
                <p>
                  Every{" "}
                  {collectionStatus
                    ? Math.round(collectionStatus.interval_seconds / 60)
                    : 60}{" "}
                  min · last{" "}
                  {collectionStatus?.last_finished_at
                    ? formatDate(collectionStatus.last_finished_at)
                    : "waiting for first run"}
                </p>
              </div>
            </div>
          </section>

          <div className="panel forecast-header">
            <div>
              <h2>{selectedLocation?.name ?? "Select a location"}</h2>
              <p className="meta">
                Real Open-Meteo forecasts are frozen into snapshots. NWS official forecasts and
                METAR observations are archived, normalized, and quality-scored for this location.
              </p>
              {forecast ? (
                <p className="snapshot-note">
                  <Database size={16} />
                  Snapshot #{forecast.id} created {formatDate(forecast.forecast_created_at)} with{" "}
                  {forecast.raw_record_count.toLocaleString()} raw records
                </p>
              ) : null}
              {apiLoading ? (
                <p className="snapshot-note">
                  <Loader2 className="spin" size={16} />
                  Refreshing location data
                </p>
              ) : null}
            </div>
            <button
              className="primary-button"
              disabled={!selectedLocationId || loading}
              onClick={handleGenerateForecast}
              type="button"
            >
              {loading ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
              Generate
            </button>
          </div>

          {leadPoint ? (
            <>
              <section className="forecast-visual-grid">
                <div className="panel forecast-hero-card">
                  <div className="weather-orb">
                    <WeatherIcon point={leadPoint} size={58} />
                  </div>
                  <div className="forecast-hero-main">
                    <span>{conditionLabel(leadPoint)}</span>
                    <strong>{leadPoint.temperature.temperature_f} F</strong>
                    <p>
                      Feels like {leadPoint.temperature.apparent_temperature_f} F · range{" "}
                      {leadPoint.temperature.likely_low_f}-{leadPoint.temperature.likely_high_f} F
                    </p>
                  </div>
                  <div className="forecast-radar">
                    <div>
                      <span>Rain</span>
                      <strong>{leadPoint.precipitation.probability_percent}%</strong>
                    </div>
                    <div>
                      <span>Clouds</span>
                      <strong>{leadPoint.atmosphere.cloud_cover_percent}%</strong>
                    </div>
                    <div>
                      <span>Confidence</span>
                      <strong>{leadPoint.confidence_percent}%</strong>
                    </div>
                  </div>
                </div>

                <div className="panel forecast-compass-card">
                  <div className="compass-face">
                    <Navigation
                      size={42}
                      style={{ transform: `rotate(${leadPoint.wind.direction_degrees}deg)` }}
                    />
                  </div>
                  <div>
                    <span>Wind</span>
                    <strong>{leadPoint.wind.sustained_speed_mph} mph</strong>
                    <p>
                      Gust {leadPoint.wind.max_gust_mph} mph · direction{" "}
                      {leadPoint.wind.direction_degrees} deg
                    </p>
                  </div>
                </div>
              </section>

              <section className="forecast-card-grid">
                {forecast.points.slice(0, 9).map((point) => (
                  <article className="forecast-card" key={point.horizon}>
                    <div className="forecast-card-top">
                      <span>{point.horizon}</span>
                      <WeatherIcon point={point} size={24} />
                    </div>
                    <strong>{point.temperature.temperature_f} F</strong>
                    <p>{formatDate(point.forecast_valid_at)}</p>
                    <div className="mini-bars">
                      <div>
                        <span>
                          <Umbrella size={13} />
                          Rain {point.precipitation.probability_percent}%
                        </span>
                        <i>
                          <b style={{ width: barWidth(point.precipitation.probability_percent) }} />
                        </i>
                      </div>
                      <div>
                        <span>
                          <Cloud size={13} />
                          Clouds {point.atmosphere.cloud_cover_percent}%
                        </span>
                        <i>
                          <b style={{ width: barWidth(point.atmosphere.cloud_cover_percent) }} />
                        </i>
                      </div>
                      <div>
                        <span>
                          <Activity size={13} />
                          Confidence {point.confidence_percent}%
                        </span>
                        <i>
                          <b style={{ width: barWidth(point.confidence_percent) }} />
                        </i>
                      </div>
                    </div>
                  </article>
                ))}
              </section>

              <section className="panel hourly-visual-panel">
                <div className="section-title">
                  <span className="title-label">
                    <TrendingUp size={18} />
                    <h3>Next 18 Hours</h3>
                  </span>
                </div>
                <div className="hourly-strip">
                  {hourlyPreview.map((point) => {
                    const range = Math.max(1, hourlyMax - hourlyMin);
                    const tempOffset = ((point.temperature.temperature_f - hourlyMin) / range) * 100;
                    return (
                      <div className="hourly-card" key={`${point.horizon_hours}-${point.forecast_valid_at}`}>
                        <span>{point.horizon_hours}h</span>
                        <WeatherIcon point={point} size={20} />
                        <strong>{point.temperature.temperature_f} F</strong>
                        <div className="temp-track">
                          <b style={{ left: `${tempOffset}%` }} />
                        </div>
                        <small>
                          <Droplets size={12} />
                          {point.precipitation.probability_percent}%
                        </small>
                      </div>
                    );
                  })}
                </div>
              </section>

              <section className="metric-grid">
                <div className="metric visual-metric">
                  <Thermometer size={22} />
                  <span>Dew Point</span>
                  <strong>{leadPoint.temperature.dew_point_f} F</strong>
                </div>
                <div className="metric visual-metric">
                  <Droplets size={22} />
                  <span>Humidity</span>
                  <strong>{leadPoint.atmosphere.relative_humidity_percent}%</strong>
                </div>
                <div className="metric visual-metric">
                  <Gauge size={22} />
                  <span>Pressure</span>
                  <strong>{leadPoint.atmosphere.pressure_hpa} hPa</strong>
                </div>
                <div className="metric visual-metric">
                  <Eye size={22} />
                  <span>Visibility</span>
                  <strong>{leadPoint.atmosphere.visibility_mi} mi</strong>
                </div>
              </section>

              <section className="phase-grid">
                <div className="panel table-shell">
                  <div className="section-title">
                    <span className="title-label">
                      <BadgeCheck size={18} />
                      <h3>Final Scorecard</h3>
                    </span>
                  </div>
                  <div className="quality-strip">
                    <div>
                      <span>Evaluated</span>
                      <strong>{phase35Report?.phase_33_final_scorecard.forecasts_evaluated ?? 0}</strong>
                    </div>
                    <div>
                      <span>Health</span>
                      <strong>{phase35Report?.phase_29_data_quality_monitoring.status ?? "No data"}</strong>
                    </div>
                    <div>
                      <span>Pairs</span>
                      <strong>
                        {phase35Report?.phase_31_fair_comparison.qualifying_pair_count ?? 0}
                      </strong>
                    </div>
                  </div>
                  <div className="record-list">
                    <div className="record-row">
                      <strong>Conclusion</strong>
                      <span>
                        {phase35Report?.phase_31_fair_comparison.conclusion ??
                          "Insufficient evidence"}
                      </span>
                    </div>
                    <div className="record-row">
                      <strong>Evaluation period</strong>
                      <span>
                        {phase35Report?.phase_33_final_scorecard.evaluation_period ??
                          "No resolved forecasts yet"}
                      </span>
                    </div>
                    <div className="record-row">
                      <strong>Data gaps</strong>
                      <span>
                        {phase35Report?.phase_30_transparency.missing_data.join(", ") ||
                          "No gaps reported"}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="panel table-shell">
                  <div className="section-title">
                    <span className="title-label">
                      <Filter size={18} />
                      <h3>Transparency & Monitoring</h3>
                    </span>
                  </div>
                  <div className="record-list">
                    <div className="record-row">
                      <strong>Why this forecast?</strong>
                      <span>
                        {phase35Report?.phase_30_transparency.explanation ??
                          "Generate a forecast to freeze feature evidence."}
                      </span>
                    </div>
                    <div className="record-row">
                      <strong>Error analysis</strong>
                      <span>
                        {phase35Report?.phase_21_error_analysis.sample_count ?? 0} samples ·{" "}
                        {Object.keys(
                          phase35Report?.phase_21_error_analysis.failure_categories ?? {}
                        ).join(", ") || "no categories yet"}
                      </span>
                    </div>
                    <div className="record-row">
                      <strong>Validation backlog</strong>
                      <span>
                        {phase35Report?.phase_29_data_quality_monitoring.validation_backlog ?? 0} unresolved · missing{" "}
                        {phase35Report?.phase_29_data_quality_monitoring.missing_models.join(", ") ||
                          "none"}
                      </span>
                    </div>
                  </div>
                </div>
              </section>

              <section className="phase-grid">
                <div className="panel table-shell">
                  <div className="section-title split">
                    <span className="title-label">
                      <BadgeCheck size={18} />
                      <h3>Validation Box</h3>
                    </span>
                    <button
                      className="secondary-button compact"
                      disabled={validationLoading || loading || !selectedLocationId}
                      onClick={handleRunValidation}
                      type="button"
                    >
                      {validationLoading ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
                      Run
                    </button>
                  </div>
                  <div className="quality-strip">
                    <div>
                      <span>Validated</span>
                      <strong>{phase20Report?.ground_truth.validated_record_count ?? 0}</strong>
                    </div>
                    <div>
                      <span>Temp MAE</span>
                      <strong>
                        {formatMetric(phase20Report?.accuracy_metrics.temperature_mae_f, " F")}
                      </strong>
                    </div>
                    <div>
                      <span>Skill</span>
                      <strong>{formatMetric(primarySkill?.skill_score)}</strong>
                    </div>
                  </div>
                  <div className="record-list">
                    <div className="record-row">
                      <strong>Benchmark</strong>
                      <span>
                        {phase20Report?.professional_benchmark.source ?? "No benchmark"} ·{" "}
                        {phase20Report?.professional_benchmark.comparable_validation_count ?? 0} comparable
                      </span>
                    </div>
                    <div className="record-row">
                      <strong>Significance</strong>
                      <span>
                        {phase20Report?.statistical_significance.classification ?? "No data"} ·{" "}
                        {phase20Report?.statistical_significance.sample_count ?? 0} paired samples
                      </span>
                    </div>
                    <div className="record-row">
                      <strong>Frozen rows</strong>
                      <span>
                        {phase20Report?.snapshot_integrity.immutable_snapshot_count ?? 0} snapshots ·{" "}
                        {phase20Report?.snapshot_integrity.frozen_feature_row_count ?? 0} feature rows
                      </span>
                    </div>
                  </div>
                </div>

                <div className="panel table-shell">
                  <div className="section-title">
                    <span className="title-label">
                      <TrendingUp size={18} />
                      <h3>ML & Segments</h3>
                    </span>
                  </div>
                  <div className="record-list">
                    <div className="record-row">
                      <strong>{phase20Report?.machine_learning_forecast.algorithm ?? "ML baseline"}</strong>
                      <span>
                        {phase20Report?.machine_learning_forecast.status ?? "No data"} ·{" "}
                        {phase20Report?.machine_learning_forecast.training_sample_count ?? 0} training samples
                      </span>
                    </div>
                    <div className="record-row">
                      <strong>Ensemble</strong>
                      <span>
                        {phase20Report?.ensemble.status ?? "No data"} · temp{" "}
                        {formatMetric(phase20Report?.ensemble.temperature_prediction_f, " F")}
                      </span>
                    </div>
                    {topSegments.map((segment) => (
                      <div
                        className="record-row"
                        key={`${segment.segment_type}-${segment.segment}`}
                      >
                        <strong>
                          {segment.segment_type}: {segment.segment}
                        </strong>
                        <span>
                          {segment.sample_count} samples · MAE{" "}
                          {formatMetric(segment.temperature_mae_f, " F")} · skill{" "}
                          {formatMetric(segment.skill_score)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </section>

              <section className="phase-grid">
                <div className="panel table-shell">
                  <div className="section-title">
                    <span className="title-label">
                      <Database size={18} />
                      <h3>Layers 5-10</h3>
                    </span>
                  </div>
                  <div className="quality-strip">
                    <div>
                      <span>Models</span>
                      <strong>{phaseLayers?.numerical_model_layer.model_count ?? 0}</strong>
                    </div>
                    <div>
                      <span>Regime</span>
                      <strong>{phaseLayers?.weather_regime.regime ?? "No data"}</strong>
                    </div>
                    <div>
                      <span>Features</span>
                      <strong>{featureCount}</strong>
                    </div>
                  </div>
                  <div className="record-list">
                    <div className="record-row">
                      <strong>Numerical temperature mean</strong>
                      <span>
                        {formatMetric(
                          phaseLayers?.numerical_model_layer.model_temperature_mean_f,
                          " F"
                        )}
                      </span>
                    </div>
                    <div className="record-row">
                      <strong>Precipitation agreement</strong>
                      <span>
                        {formatMetric(
                          phaseLayers?.numerical_model_layer
                            .model_precipitation_agreement_percent,
                          "%"
                        )}
                      </span>
                    </div>
                    <div className="record-row">
                      <strong>Sources</strong>
                      <span>
                        {phaseLayers?.numerical_model_layer.sources.join(", ") ||
                          "No model sources yet"}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="panel table-shell">
                  <div className="section-title">
                    <span className="title-label">
                      <Filter size={18} />
                      <h3>Learning Readiness</h3>
                    </span>
                  </div>
                  <div className="record-list">
                    <div className="record-row">
                      <strong>Historical patterns</strong>
                      <span>
                        {phaseLayers?.historical_pattern_layer.status ?? "No data"} ·{" "}
                        {phaseLayers?.historical_pattern_layer.sample_size ?? 0} samples
                      </span>
                    </div>
                    <div className="record-row">
                      <strong>Analog matches</strong>
                      <span>
                        {phaseLayers?.analog_layer.status ?? "No data"} · confidence{" "}
                        {phaseLayers?.analog_layer.analog_confidence_percent ?? 0}%
                      </span>
                    </div>
                    <div className="record-row">
                      <strong>Microclimate bias</strong>
                      <span>
                        {phaseLayers?.microclimate_layer.learned_bias_status ?? "No data"} ·{" "}
                        {String(
                          phaseLayers?.microclimate_layer.estimated_features.elevation_band ??
                            "unknown"
                        )}
                      </span>
                    </div>
                    <div className="record-row">
                      <strong>Regime confidence</strong>
                      <span>
                        {phaseLayers?.weather_regime.confidence_percent ?? 0}% ·{" "}
                        {phaseLayers?.weather_regime.factors[0] ?? "No regime evidence yet"}
                      </span>
                    </div>
                  </div>
                </div>
              </section>

              <section className="phase-grid">
                <div className="panel table-shell">
                  <div className="section-title">
                    <span className="title-label">
                      <Gauge size={18} />
                      <h3>Current State Layer</h3>
                    </span>
                  </div>
                  <div className="quality-strip">
                    <div>
                      <span>Temperature</span>
                      <strong>{formatValue(currentTemperature)}</strong>
                    </div>
                    <div>
                      <span>Pressure</span>
                      <strong>{formatValue(currentPressure)}</strong>
                    </div>
                    <div>
                      <span>Wind</span>
                      <strong>{formatValue(currentWind)}</strong>
                    </div>
                  </div>
                  <div className="source-summary">
                    <strong>{currentState?.evidence_record_count ?? 0}</strong>
                    <span>
                      normalized evidence records through{" "}
                      {currentState?.data_cutoff_time
                        ? formatDate(currentState.data_cutoff_time)
                        : "no cutoff yet"}
                    </span>
                  </div>
                </div>

                <div className="panel table-shell">
                  <div className="section-title">
                    <span className="title-label">
                      <TrendingUp size={18} />
                      <h3>Atmospheric Momentum</h3>
                    </span>
                  </div>
                  <div className="record-list">
                    <div className="record-row">
                      <strong>Temperature 1h</strong>
                      <span>
                        {formatTrend(currentState?.trends.temperature_change_1h_f, " F")}
                      </span>
                    </div>
                    <div className="record-row">
                      <strong>Pressure 3h</strong>
                      <span>{formatTrend(currentState?.trends.pressure_change_3h_hpa, " hPa")}</span>
                    </div>
                    <div className="record-row">
                      <strong>Wind Shift</strong>
                      <span>{formatTrend(currentState?.trends.wind_shift_degrees, " deg")}</span>
                    </div>
                    <div className="record-row">
                      <strong>Visibility</strong>
                      <span>{formatValue(currentVisibility)}</span>
                    </div>
                  </div>
                </div>
              </section>

              <section className="phase-grid">
                <div className="panel table-shell">
                  <div className="section-title">
                    <span className="title-label">
                      <RadioTower size={18} />
                      <h3>Active Sources</h3>
                    </span>
                  </div>
                  <div className="provider-list">
                    {providers.map((provider) => (
                      <div className="provider-row" key={`${provider.source}-${provider.model}`}>
                        <strong>{provider.source}</strong>
                        <span>{provider.model}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="panel table-shell">
                  <div className="section-title">
                    <span className="title-label">
                      <Archive size={18} />
                      <h3>Latest Raw Records</h3>
                    </span>
                  </div>
                  <div className="source-summary">
                    <strong>{rawRecords.length}</strong>
                    <span>recent records shown from {rawSources.length || 0} source groups</span>
                  </div>
                  <div className="record-list">
                    {rawRecords.slice(0, 6).map((record) => (
                      <div className="record-row" key={record.id}>
                        <strong>{record.source}</strong>
                        <span>
                          {record.variable}: {record.value} {record.units}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </section>

              <section className="panel table-shell">
                <div className="section-title">
                  <span className="title-label">
                    <Filter size={18} />
                    <h3>Normalization Quality Control</h3>
                  </span>
                </div>
                <div className="quality-strip">
                  <div>
                    <span>Accepted</span>
                    <strong>{acceptedCount}</strong>
                  </div>
                  <div>
                    <span>Flagged</span>
                    <strong>{flaggedCount}</strong>
                  </div>
                  <div>
                    <span>Shown</span>
                    <strong>{normalizedRecords.length}</strong>
                  </div>
                </div>
                <div className="record-list">
                  {normalizedRecords.slice(0, 6).map((record) => (
                    <div className="record-row" key={record.id}>
                      <strong>
                        {record.normalized_variable} · {record.quality_status}
                      </strong>
                      <span>
                        {record.normalized_value ?? record.normalized_text}{" "}
                        {record.normalized_units} · score {record.quality_score}
                      </span>
                    </div>
                  ))}
                </div>
              </section>

              <section className="panel table-shell">
                <h3>Required Horizons</h3>
                <div className="forecast-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Horizon</th>
                        <th>Valid</th>
                        <th>Temp</th>
                        <th>Likely Range</th>
                        <th>Precip</th>
                        <th>Wind</th>
                        <th>Humidity</th>
                        <th>Pressure</th>
                        <th>Confidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {forecast.points.map((point) => (
                        <tr key={point.horizon}>
                          <td>{point.horizon}</td>
                          <td>{formatDate(point.forecast_valid_at)}</td>
                          <td>{point.temperature.temperature_f} F</td>
                          <td>
                            {point.temperature.likely_low_f} to {point.temperature.likely_high_f} F
                          </td>
                          <td>
                            {point.precipitation.probability_percent}% /{" "}
                            {point.precipitation.amount_in} in
                          </td>
                          <td>
                            {point.wind.sustained_speed_mph} mph, gust {point.wind.max_gust_mph}
                          </td>
                          <td>{point.atmosphere.relative_humidity_percent}%</td>
                          <td>
                            {point.atmosphere.pressure_hpa} hPa, {point.atmosphere.pressure_trend}
                          </td>
                          <td>{point.confidence_percent}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="panel table-shell">
                <h3>Hourly Forecast Preview</h3>
                <div className="forecast-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Hour</th>
                        <th>Temp</th>
                        <th>Feels Like</th>
                        <th>Dew Point</th>
                        <th>Precip Type</th>
                        <th>Clouds</th>
                        <th>Visibility</th>
                      </tr>
                    </thead>
                    <tbody>
                      {forecast.hourly_points.slice(0, 24).map((point) => (
                        <tr key={`${point.horizon_hours}-${point.forecast_valid_at}`}>
                          <td>{point.horizon_hours}</td>
                          <td>{point.temperature.temperature_f} F</td>
                          <td>{point.temperature.apparent_temperature_f} F</td>
                          <td>{point.temperature.dew_point_f} F</td>
                          <td>{point.precipitation.precipitation_type}</td>
                          <td>{point.atmosphere.cloud_cover_percent}%</td>
                          <td>{point.atmosphere.visibility_mi} mi</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          ) : !selectedLocationId ? (
            <div className="panel empty-state">
              <AlertTriangle size={28} />
              <p>Create or select a location, then generate the first frozen forecast snapshot.</p>
            </div>
          ) : (
            null
          )}
        </section>
      </div>

      {isAddLocationOpen ? (
        <AddLocationDialog
          loading={loading}
          onClose={closeAddLocationDialog}
          onCreate={handleCreateLocation}
        />
      ) : null}
    </main>
  );
}
