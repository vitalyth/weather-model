# Weather Model

Multi-layer weather prediction, validation, and benchmarking system.

This repository is intentionally built phase by phase. The current checkpoint is
Phase 35: real-source ingestion, normalization, current-state estimation,
first-pass model layers, frozen feature rows, validation contracts, benchmark
comparison, skill scoring, statistical guardrails, segmented performance,
transparency, health monitoring, final scorecards, and a live completion report.

## Structure

- `backend/` - FastAPI service and SQLite persistence
- `frontend/` - Next.js dashboard
- `docs/` - phase checkpoints and implementation notes

## Phase 1 Quick Start

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend expects the API at `http://localhost:8000`. Override with
`NEXT_PUBLIC_API_BASE_URL` when needed.

## Current Data Source

Forecast snapshots are generated from the Open-Meteo forecast API. Raw source
records are stored in SQLite before mapping to dashboard forecast points and
feature layers.

The ingestion layer also archives National Weather Service official hourly
forecast records for supported US locations. NWS availability depends on whether
the coordinate maps to a weather.gov grid point.

It also archives METAR airport observations from the Aviation Weather Center
when a configured location is near one of the initial known airport stations.

Historical patterns now use Open-Meteo Historical archive data for a recent
same-calendar-window baseline. Analog matching and learned local bias
corrections still expose their API contracts but return insufficient-data
statuses until enough historical state and validation datasets are added.

Machine-learning and statistical comparison layers also expose their contracts
now. They refuse strong claims until enough resolved forecast/observation pairs
exist.

Useful endpoints:

- `GET /locations`
- `POST /locations`
- `DELETE /locations/{location_id}`
- `POST /locations/{location_id}/forecasts`
- `GET /forecasts`
- `GET /ingestion/providers`
- `GET /ingestion/raw-records?location_id=1&source=Open-Meteo`
- `GET /normalization/records?location_id=1&quality_status=accepted`
- `GET /current-state/{location_id}`
- `GET /forecast/layers/{location_id}`
- `POST /validation/run/{location_id}`
- `GET /validation/report/{location_id}`
- `GET /predictions/history`
- `GET /predictions/{prediction_id}`
- `GET /errors`
- `GET /accuracy/head-to-head`
- `GET /accuracy/calibration?location_id=1`
- `GET /models/performance?location_id=1`
- `GET /models/versions`
- `GET /system/health`
- `GET /forecast/transparency/{location_id}`
- `GET /scorecard`
- `GET /api/catalog`
- `GET /forecast/system-report/{location_id}`
