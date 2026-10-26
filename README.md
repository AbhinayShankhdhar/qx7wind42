# WindCast: day-ahead wind forecast desk

A web app for a UK energy supplier's day-ahead trading team. It answers two questions for
purchase decisions made in **January 2026**:

1. **What wind forecast did we actually have when we made the decision?**
   For every period on delivery day D, it shows the latest national wind forecast published
   before the decision time on day D-1.
2. **How accurate was that forecast?**
   It quantifies the error (typical miss, bias, worst miss, shortfall buffer) and breaks it down by
   lead time, hour of day and delivery day.

**Live app:** `<add your Vercel link here>`

Data: Elexon BMRS, national level only:
[FUELHH](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream) (actual generation, `fuelType = WIND`) and
[WINDFOR](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream) (wind forecasts).

---

## Key assumptions

| Topic | Assumption |
|---|---|
| Decision window | Decisions made 1–31 Jan 2026, each buying power for the next day, so **delivery days are 2 Jan – 1 Feb 2026**. |
| Decision time | Default **10:00 UK time on D-1** (before day-ahead auction gate closure). Adjustable in the UI in 30-minute steps. |
| Forecast used | For each target period, the **latest WINDFOR forecast with `publishTime` ≤ decision time**. Later forecasts are ignored, because the desk could not have seen them. |
| Days and times | Delivery days are UK calendar days (`Europe/London`, daylight saving handled). Raw data is UTC. |
| Error sign | `error = forecast − actual`. Positive means the forecast was too high, so less wind arrived (shortfall risk). |
| Revisions | If an actual period was published more than once, the latest publication is used. |
| Matching | Forecasts and actuals are compared only where both exist for the same `startTime`. |

## Metrics

| Metric | Meaning for the desk |
|---|---|
| MAE | Average size of the miss, in MW |
| nMAE | MAE as % of average actual wind output |
| Bias | Average of forecast − actual. Shows systematic over- or under-forecasting |
| RMSE | Like MAE but penalises large misses more |
| P90 / P95 shortfall | In 90% / 95% of periods, actual wind was at most this far **below** the forecast. A ready-to-use procurement buffer |
| Accuracy by lead time | MAE of **all** forecasts grouped by hours between publish time and target time (0–48 h, 6 h buckets) |

---

## Project structure

```
.
├── backend/                  Python API (FastAPI)
│   ├── app/
│   │   ├── config.py         Business assumptions: date windows, default decision time, bins
│   │   ├── elexon.py         Elexon API client (standard library only, retries, chunked requests)
│   │   ├── data_store.py     Loads data once: from the cache file, or live from Elexon
│   │   ├── analysis.py       Core logic: decision-time forecast selection + error metrics (pure functions)
│   │   └── main.py           HTTP endpoints: /api/health, /api/meta, /api/analysis
│   ├── scripts/build_cache.py  Downloads January 2026 data into backend/data/
│   ├── data/                 Cached Elexon snapshot (elexon_wind_jan2026.json)
│   ├── tests/                Unit tests (pytest)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                 React app (Vite)
│   ├── src/
│   │   ├── App.jsx           Page layout, controls, KPI tiles, findings, charts
│   │   ├── components/charts.jsx  Lightweight SVG line and bar charts with hover tooltips
│   │   ├── api.js            Calls to the backend
│   │   ├── format.js         Number/time formatting (UK local time)
│   │   └── styles.css        Styling, light and dark mode
│   ├── nginx.conf            Serves the built app and forwards /api to the backend (Docker)
│   └── Dockerfile
├── api/index.py              Vercel entry point (exposes the same FastAPI app)
├── vercel.json               Vercel build and routing config
├── requirements.txt          Python dependencies for Vercel
└── docker-compose.yml        Runs backend + frontend together
```

## Architecture

```
Elexon BMRS API ──(one-off fetch)──> backend/data/*.json cache
                                            │
                       FastAPI  (data_store → analysis → main)
                                            │  JSON over /api/*
                       React (Vite) dashboard in the browser
```

Design decisions:

- **All business logic lives in `analysis.py`** as pure functions (no network, no files), so it is easy to read and unit-test.
- **Data is cached.** The live download takes about 70 API calls. A snapshot makes the deployed app fast and keeps it working if Elexon is slow. If no cache exists, the backend fetches live on first request.
- **Fast lookup.** Forecasts are indexed by target time with publish times sorted, so "latest forecast before the cutoff" is a binary search.
- **Few dependencies.** The backend needs only FastAPI; the frontend only React. Charts are hand-written SVG, which keeps the bundle small and gives full control over tooltips and styling.
- **Assumptions in one place** (`config.py`), and the decision time is a UI control rather than hard-coded.

API:

| Endpoint | Description |
|---|---|
| `GET /api/health` | Health check |
| `GET /api/meta` | Date windows, default decision time, data snapshot info |
| `GET /api/analysis?start=2026-01-02&end=2026-02-01&cutoff_hour=10&cutoff_minute=0` | Time series, metrics, breakdowns |

Interactive API docs: `http://localhost:8000/docs` when the backend is running.

---

## How to run

### Option 1: Docker (recommended)

```bash
docker compose up --build
```

Open http://localhost:3000. The API is at http://localhost:8000.

### Option 2: Without Docker

Backend (Python 3.11+):

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
python -m scripts.build_cache   # one-off: download January 2026 data (~1–2 min)
uvicorn app.main:app --reload --port 8000
```

Frontend (Node 18+), in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

### Tests

```bash
cd backend
python -m pytest
```

### Deploy to Vercel

1. Run `python -m scripts.build_cache` and commit `backend/data/elexon_wind_jan2026.json`.
2. Import the GitHub repo in Vercel. No settings needed; `vercel.json` handles the build.
3. The React app is served as static files; `/api/*` runs the FastAPI app as a Python serverless function.

---

## Possible next steps

- Daily scheduled refresh of the data instead of a fixed snapshot
- Probabilistic buffers per hour of day and per forecast level
- Extend to solar and regional data, and to demand forecasts, to estimate the full net purchase requirement
- Store data in a database for longer history and seasonal comparison

## Use of AI tools

This project was built with help from **Claude (Anthropic)**, an AI assistant, which was used to
generate and review code, structure the project and draft this README. All design choices,
assumptions and results were reviewed and understood by the author.
