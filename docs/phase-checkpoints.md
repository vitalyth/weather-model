# Phase Checkpoints

## Phase 1 - Define the Forecast

Status: implemented foundation.

Scope:

- Configurable forecast locations
- Required forecast horizons:
  - 1 hour
  - 3 hours
  - 6 hours
  - 12 hours
  - 24 hours
  - 48 hours
  - 72 hours
  - 5 days
  - 7 days
- Hourly predictions for the first 72 hours
- Forecast variables for temperature, precipitation, wind, atmospheric
  conditions, and notable weather probabilities
- Frozen forecast snapshots persisted before validation phases exist
- FastAPI endpoints for locations and forecasts
- Next.js dashboard for selecting locations, inspecting forecast details, and
  seeing current ingestion status

Notes:

- Forecast values now come from the Open-Meteo forecast API using its best-match
  model selection for each coordinate.
- This is real forecast data, but it is still a single-provider Phase 1
  implementation. Phase 2 expands this into modular ingestion with raw-source
  preservation and multiple independent sources.
- Old forecasts are never overwritten. Every forecast request creates a new
  persisted snapshot.

## Phase 2 - Data Ingestion

Status: first source implemented.

Implemented scope:

- Formal provider protocol for source adapters
- Open-Meteo forecast retrieval for configurable locations
- National Weather Service official hourly forecast ingestion for supported US
  locations
- Aviation Weather Center METAR observation ingestion using nearest known airport
  station
- Raw record persistence with source/model/init/valid/retrieval metadata
- Location, latitude, longitude, elevation, variable, value, and units preserved
- API endpoint to inspect ingested raw records:
  - `GET /ingestion/raw-records`
  - supports `location_id`, `source`, and `limit` query filters
- API endpoint to inspect configured providers:
  - `GET /ingestion/providers`
- No overwrite policy for incoming forecast versions or raw source records
- Dashboard displays the actual active phase, configured providers, and latest
  raw ingested records after snapshot generation

Remaining Phase 2 scope:

- Replace the initial METAR station catalog with full station-cache ingestion
- Add historical data providers
- Archive professional benchmark forecasts at issue time

## Phase 3 - Data Normalization

Status: first pass implemented.

Implemented scope:

- Normalized records are created from raw ingested records without altering the
  raw source archive
- Common units are applied for core numeric fields:
  - Fahrenheit for temperatures and dew point
  - mph for wind speed and gusts
  - miles for visibility
  - hPa for pressure
  - percent for humidity and precipitation probability
- Variable names are mapped to internal names such as `temperature`,
  `dew_point`, `wind_speed`, `pressure`, and `visibility`
- Basic quality control assigns:
  - `accepted`
  - `suspicious`
  - `rejected`
- Each normalized record stores a quality score and reason
- API endpoint to inspect normalized records:
  - `GET /normalization/records`
  - supports `location_id`, `source`, `quality_status`, and `limit` filters
- Dashboard displays Phase 3 status and recent normalization quality counts

Remaining Phase 3 scope:

- Add duplicate, stale-record, sudden-change, and spatial-consistency checks
- Record correction decisions separately from accepted/rejected decisions
- Add batch-level normalization summaries by source and variable

## Phase 4 - Current Atmospheric State

Status: first pass implemented.

Implemented scope:

- Current State Layer is computed from normalized records for a location
- Observation sources are prioritized over forecast sources when available:
  - METAR observations
  - NWS official forecast records
  - Open-Meteo forecast records
- Current values include source, valid time, unit, and quality score
- Initial atmospheric momentum features are calculated where source-consistent
  history exists:
  - `temperature_change_1h_f`
  - `temperature_change_3h_f`
  - `temperature_change_6h_f`
  - `pressure_change_3h_hpa`
  - `pressure_change_6h_hpa`
  - `dewpoint_change_f`
  - `humidity_change_percent`
  - `wind_shift_degrees`
  - `precipitation_recent_in`
  - `cloud_trend`
- API endpoint:
  - `GET /current-state/{location_id}`
- Dashboard displays Phase 4 status, current conditions, evidence count, and
  momentum features

Remaining Phase 4 scope:

- Add station distance and elevation weighting
- Separate observation-derived current state from forecast-derived fallback state
- Add radar/satellite/model-analysis inputs when providers exist

## Phase 5 - Numerical Model Layer

Status: first pass implemented.

Implemented scope:

- Numerical model summaries are computed from normalized forecast records
- The layer reports active model/source count, source names, ensemble-style
  temperature mean/median/spread, precipitation probability mean/agreement, wind
  mean, and pressure mean
- Current implementation uses available forecast providers:
  - Open-Meteo
  - National Weather Service, when available for the selected location

Remaining Phase 5 scope:

- Add more independent numerical weather prediction sources
- Preserve model cycle metadata for multi-run trend analysis
- Add source weighting by historical skill once validation exists

## Phase 6 - Historical Pattern Layer

Status: first pass implemented.

Implemented scope:

- API response shape is in place for climatological highs/lows, typical
  precipitation probability, percentile context, sample size, and status
- Open-Meteo Historical archive ingestion retrieves same-calendar-window daily
  history from prior years
- Historical rows are persisted as raw records and normalized into common units
- Historical layer computes:
  - normal high temperature
  - normal low temperature
  - typical precipitation-day probability
  - current temperature percentile against the historical daily-mean baseline
- If the archive provider is unavailable or no historical rows exist, the layer
  still returns `insufficient_data`

Remaining Phase 6 scope:

- Add more historical observation/climatology providers
- Build same-location and nearby-station historical aggregates
- Compare current atmospheric state against normal ranges

## Phase 7 - Analog Weather Layer

Status: contract implemented with explicit insufficient-data output.

Implemented scope:

- API response shape is in place for analog count, confidence, matched analogs,
  status, and explanatory note
- The service returns `insufficient_data` until a historical atmospheric-state
  database exists

Remaining Phase 7 scope:

- Build indexed historical state vectors
- Search past similar setups by current-state, regime, season, and location
- Convert analog outcomes into forecast features

## Phase 8 - Microclimate Layer

Status: first pass implemented.

Implemented scope:

- Geographic features are generated for latitude, longitude, elevation, absolute
  latitude, hemisphere, and elevation band
- Learned bias status is explicitly reported as
  `insufficient_validation_history`

Remaining Phase 8 scope:

- Add station distance, terrain, coast/water, urban, and land-cover features
- Learn local forecast bias from completed forecast-vs-observation records

## Phase 9 - Weather Regime Layer

Status: first pass implemented.

Implemented scope:

- Rule-based weather regime classifier runs from current state and numerical
  model summaries
- Initial regimes include high wind, precipitation, heat, cold, high pressure,
  and low-variability conditions
- Each regime includes confidence and evidence factors

Remaining Phase 9 scope:

- Replace rules with trained clustering/classification once enough labeled
  history exists
- Add upper-air, radar, satellite, and frontal-analysis features

## Phase 10 - Unified Feature Dataset

Status: first pass implemented.

Implemented scope:

- Model-ready feature payload combines current state, atmospheric momentum,
  numerical summaries, historical placeholders, analog readiness,
  microclimate/geographic features, time features, wind direction circular
  encoding, and weather regime
- Feature payload is versioned as `phase-10-feature-contract-v0`
- API endpoint:
  - `GET /phase-layers/{location_id}`
- Dashboard displays Layers 5-10 status, source/model counts, weather regime,
  learning readiness, and feature count

Remaining Phase 10 scope:

- Lock a durable feature schema for model training
- Backfill features for archived snapshots
- Store generated feature rows for validation, benchmarking, and training

## Phase 11 - Machine-Learning Forecast

Status: contract implemented with resolved-data gate.

Implemented scope:

- ML forecast layer reports algorithm, training sample count, status, and current
  temperature fallback
- The layer does not train on unresolved predictions
- It returns `insufficient_training_data` until enough validated forecasts exist
- First planned baseline is a simple bias-corrected linear forecast, not a neural
  model

Remaining Phase 11 scope:

- Persist training datasets from resolved forecasts
- Add out-of-sample model comparison before any production promotion

## Phase 12 - Multi-Layer Ensemble

Status: first pass implemented.

Implemented scope:

- Ensemble response combines numerical, observational trend, and future ML
  layer weights
- Weights are explicit and rule-based while validation history is small
- Historical, analog, and climatology weights remain zero until their data
  sources are real

Remaining Phase 12 scope:

- Learn meta-model weights by location, horizon, season, variable, regime, and
  prior skill

## Phase 13 - Forecast Confidence

Status: first pass implemented.

Implemented scope:

- Confidence/calibration layer reports sample count and a calibration proxy
- Resolved forecast errors are used only after the forecast valid time
- Probability calibration is intentionally deferred until enough probability
  bins have matured

Remaining Phase 13 scope:

- Add reliability bins, Brier scores, and probability calibration diagrams

## Phase 14 - Snapshot / Anti-Data-Leakage System

Status: implemented foundation.

Implemented scope:

- Forecast snapshots remain immutable and versioned
- Feature rows are frozen into `feature_snapshots` with a SHA-256 freeze hash
- Phase 20 reports expose immutable snapshot count, frozen feature row count,
  unresolved forecast count, and leakage policy

Remaining Phase 14 scope:

- Add migration tooling and immutable database constraints
- Add explicit training-data cutoff enforcement for future trained models

## Phase 15 - Professional Forecast Benchmark

Status: first pass implemented.

Implemented scope:

- National Weather Service records archived during ingestion are treated as the
  first professional benchmark
- Benchmark comparisons require a matching archived forecast value from around
  the same issue time
- Hindsight professional forecasts are not downloaded after the event for
  comparison

Remaining Phase 15 scope:

- Add more benchmark providers where licensing permits
- Store benchmark products at issue time with dedicated benchmark tables

## Phase 16 - Observation / Ground Truth

Status: first pass implemented.

Implemented scope:

- Validation uses nearest non-rejected METAR observation within a fixed
  +/-3-hour window
- Ground-truth methodology is reported in the API
- Observation source count, validation count, and latest observation time are
  exposed

Remaining Phase 16 scope:

- Add station-distance and elevation weighting
- Add richer verified observation sources and precipitation accumulation logic

## Phase 17 - Accuracy Metrics

Status: first pass implemented.

Implemented scope:

- Validation records persist predicted value, observed value, error, absolute
  error, squared error, and benchmark error where available
- Accuracy report includes temperature MAE, RMSE, median absolute error, bias,
  wind-speed MAE, and pressure MAE

Remaining Phase 17 scope:

- Add precipitation Brier score, log loss, calibration error, and reliability
  diagrams
- Add circular wind-direction error

## Phase 18 - Forecast Skill

Status: first pass implemented.

Implemented scope:

- Skill score is calculated against the archived NWS benchmark when paired
  comparisons exist
- Interpretation text refuses strong claims when sample size is small

Remaining Phase 18 scope:

- Add climatology, persistence, and individual numerical-model baselines

## Phase 19 - Statistical Significance

Status: first pass implemented.

Implemented scope:

- Paired benchmark error differences are summarized with sample count, mean,
  median, and an approximate 95% interval when possible
- Classification uses the requested categories:
  - `OUTPERFORMING`
  - `POSSIBLY OUTPERFORMING`
  - `TIED / INCONCLUSIVE`
  - `UNDERPERFORMING`
- Strong claims require enough paired samples

Remaining Phase 19 scope:

- Add bootstrap confidence intervals and Diebold-Mariano-style tests

## Phase 20 - Segmented Performance Analysis

Status: first pass implemented.

Implemented scope:

- Performance is segmented by:
  - horizon bucket
  - season
  - weather regime
  - daytime/nighttime
  - location
- API endpoints:
  - `POST /validation/run/{location_id}`
  - `GET /phase-20/{location_id}`
- Dashboard displays validation counts, benchmark status, skill, significance,
  ML readiness, ensemble status, frozen snapshot rows, and top segments

Remaining Phase 20 scope:

- Expand segments to precipitation, wind, storm regimes, and all locations
- Add dashboard charts after enough resolved samples exist

## Phase 21 - Error Analysis Engine

Status: first pass implemented.

Implemented scope:

- Error analysis report identifies largest misses from validation records
- Rule-based failure categories are assigned for temperature, wind, and pressure
- Bias by horizon is exposed
- API endpoints:
  - `GET /errors`
  - `GET /errors/{prediction_id}`

Remaining scope:

- Store human-reviewable error categories
- Add synoptic factors such as fronts, storm tracks, and convective setup

## Phase 22 - Continuous Learning

Status: policy implemented.

Implemented scope:

- Phase 35 report exposes a continuous-learning gate
- Training is restricted to resolved forecast/observation pairs
- Promotion requires future out-of-sample improvement

Remaining scope:

- Add model-version tables and candidate promotion workflow

## Phase 23 - Walk-Forward Backtesting

Status: methodology documented in API.

Implemented scope:

- Phase 35 report defines chronological walk-forward validation as the required
  method once enough history exists

Remaining scope:

- Add backtest job runner and period-by-period result persistence

## Phase 24 - Dashboard

Status: implemented foundation.

Implemented scope:

- Dashboard now displays forecast, layers, validation, skill, scorecard,
  transparency, monitoring, source records, normalization, and history-ready
  status

Remaining scope:

- Add navigation tabs once the data volume justifies separate screens

## Phase 25 - Dashboard Visualizations

Status: visualization data contracts implemented.

Implemented scope:

- Visualization summary includes actual-vs-predicted series, rolling MAE,
  contribution weights, and performance-matrix data
- API endpoints:
  - `GET /accuracy/calibration`
  - `GET /models/performance`

Remaining scope:

- Render line charts, reliability diagrams, and heatmaps in the UI

## Phase 26 - Database Design

Status: core tables implemented.

Implemented scope:

- Current tables:
  - `locations`
  - `forecast_snapshots`
  - `raw_weather_records`
  - `normalized_weather_records`
  - `feature_snapshots`
  - `forecast_validation_records`

Remaining scope:

- Add dedicated tables for model versions, analog matches, benchmark forecasts,
  model metrics, and persisted error analysis

## Phase 27 - API Design

Status: implemented foundation.

Implemented scope:

- API catalog endpoint:
  - `GET /api/catalog`
- Prediction history endpoints:
  - `GET /predictions/history`
  - `GET /predictions/{prediction_id}`
- Model/status endpoints:
  - `GET /models/versions`
  - `GET /system/health`
  - `GET /scorecard`
  - `GET /phase-35/{location_id}`

Remaining scope:

- Add richer filtering for date ranges, variables, horizons, regimes, and seasons

## Phase 28 - Automation Pipeline

Status: manual endpoints and task contract implemented.

Implemented scope:

- Phase 35 report lists planned automation tasks and cadences
- Forecast generation and validation are callable through API endpoints

Remaining scope:

- Add a scheduler for observation retrieval, forecast generation, validation,
  metrics recalculation, weekly reports, and retraining evaluation

## Phase 29 - Data Quality Monitoring

Status: first pass implemented.

Implemented scope:

- System health report exposes status, observation age, missing models,
  validation backlog, database health, and model coverage
- API endpoint:
  - `GET /system/health`

Remaining scope:

- Track provider request failures, latency, stale observations, and source-level
  coverage in persisted health events

## Phase 30 - Model Transparency

Status: first pass implemented.

Implemented scope:

- Transparency report exposes numerical models used, latest observation time,
  ML model version/status, ensemble weights, confidence object, interval,
  missing data, forecast creation time, and a feature-grounded explanation
- API endpoint:
  - `GET /forecast/transparency/{location_id}`

Remaining scope:

- Add per-horizon explanations and clickable source evidence

## Phase 31 - Fair Model vs Meteorologist Comparison

Status: first pass implemented.

Implemented scope:

- Fair comparison report lists strict matching rules
- Qualifying pairs, model wins, professional wins, ties, and cautious conclusion
  are exposed
- API endpoint:
  - `GET /accuracy/head-to-head`

Remaining scope:

- Add probability scoring for precipitation before any rain win/loss summary

## Phase 32 - Determine Whether We Beat Professional Forecasts

Status: statistical guardrail implemented.

Implemented scope:

- Phase 35 report includes professional-outperformance status from Phase 20
  significance classification
- It refuses automatic superiority language

Remaining scope:

- Add variable-specific reports for temperature, precipitation, wind, horizon,
  and regime after larger samples exist

## Phase 33 - Final Performance Scorecard

Status: first pass implemented.

Implemented scope:

- Scorecard reports evaluated forecasts, locations, evaluation period,
  temperature status, precipitation readiness, wind readiness, and an overall
  multidimensional conclusion
- API endpoint:
  - `GET /scorecard`

Remaining scope:

- Add downloadable scorecard periods and all-location aggregate comparisons

## Phase 34 - Development Approach

Status: documented in API.

Implemented scope:

- Phase 35 report identifies current stage and next development steps

Remaining scope:

- Add project milestones and migration plan for production data growth

## Phase 35 - Required Output From Development Agent

Status: implemented as live report.

Implemented scope:

- Phase 35 report includes architecture, data-source strategy, database schema,
  data flow, validation methodology, anti-leakage strategy, benchmark
  methodology, ML strategy, dashboard architecture, API architecture, technology
  stack, project structure, and development phases
- API endpoint:
  - `GET /phase-35/{location_id}`

Remaining scope:

- Convert the live report into generated project documentation once the
  production schema stabilizes
