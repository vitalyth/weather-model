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

## Docker / CasaOS / OMV

Local build from this repo:

```bash
docker compose up -d --build
```

Open the dashboard at `http://YOUR_SERVER_IP:3000`. In Docker, the backend API
is internal to the Compose network and the frontend proxies API requests to it.
Only the frontend port needs to be published on the host.

The SQLite database is stored in the named Docker volume `weather-model-data`,
so locations, hourly snapshots, validation rows, cached reports, and background
collection history survive container updates.

Docker runs three services:

- `frontend` - the Next.js dashboard exposed on port `3000`
- `backend` - the FastAPI API, reachable inside Docker as `http://backend:8000`
- `collector` - an hourly background worker that samples every saved location,
  generates forecasts, validates matured forecasts, refreshes calculated
  reports, and stores the results in SQLite

To stop it:

```bash
docker compose down
```

To use images built by GitHub Actions instead of building on the server:

```bash
docker compose -f docker-compose.ghcr.yml up -d
```

The GitHub workflow publishes:

- `ghcr.io/vitalyth/weather-model/backend:latest`
- `ghcr.io/vitalyth/weather-model/frontend:latest`

If the GHCR packages are private, log in on the server first:

```bash
echo YOUR_GITHUB_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

For CasaOS or OMV Compose, use the same compose file contents. If port `3000`
is already used on your server, change the left side of the frontend mapping,
for example `"3010:3000"`.

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
