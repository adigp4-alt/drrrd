# CLAUDE.md — Iran Investment Tracker

AI assistant guide for working in this repository.

---

## Project Overview

**Iran Investment Tracker** is a full-stack web application that tracks 36 publicly traded US-listed stocks across five investment tiers related to a geopolitical investment thesis. It displays live prices, % changes, volume, alerts, and 30-day history sparklines on a single-page dashboard.

- **Backend:** Python / Flask (`main.py`)
- **Frontend:** Vanilla HTML/CSS/JS with Bootstrap 4 and Chart.js (`templates/index.html`)
- **Deployment:** Render.com (free tier via `render.yaml`)
- **CI:** GitHub Actions (`.github/workflows/python-package-conda.yml`)

---

## Repository Structure

```
drrrd/
├── main.py                          # Flask app: routes, data fetching, scheduler
├── templates/
│   └── index.html                   # Single-page dashboard (HTML/CSS/JS)
├── requirements.txt                 # Python dependencies (pinned versions)
├── render.yaml                      # Render.com deployment config
├── .github/
│   └── workflows/
│       └── python-package-conda.yml # CI: install deps + flake8 lint
├── README.md                        # Deployment instructions and architecture docs
└── Idk                              # Scratch notes file (not application code)
```

`data/` is auto-created at runtime and holds `snapshots.csv` (price history log). It is not committed to the repo.

---

## Key Application Concepts

### Ticker Tiers

All tickers live in the `TIERS` dict in `main.py`. Five tiers group stocks by investment strategy:

| Tier | Name | Count |
|------|------|-------|
| T1 | Post-Conflict Reconstruction | 8 tickers |
| T2 | Defense & Energy Stock Picking | 10 tickers |
| T3 | Israeli Equities & Cybersecurity | 9 tickers |
| T4 | Tanker & Shipping (TACTICAL) | 5 tickers |
| T5 | Broad Sector ETFs | 4 tickers |

`ALL_TICKERS` (flat list) and `TICKER_META` (lookup by symbol) are derived from `TIERS` at module load time.

### In-Memory Cache

All live data is stored in the module-level `CACHE` dict:

```python
CACHE = {"data": {}, "last_updated": None, "alerts": [], "history": {}}
```

- `data`: Latest price payload per symbol
- `last_updated`: ISO timestamp string of last fetch
- `alerts`: List of tickers that moved ±5% in a session
- `history`: 30-day close series per symbol (for sparklines)

The cache is never persisted to disk directly; it is rebuilt from Yahoo Finance on each scheduler run.

### Data Fetching

- `fetch_prices()` — downloads last 5 days of OHLCV data for all tickers via `yf.download()`, computes day-over-day % change, updates `CACHE`, and appends a row to `data/snapshots.csv`.
- `fetch_history_data(days=30)` — downloads 30 days of close prices into `CACHE["history"]`.
- `_save_snapshot(results)` — appends a CSV row per ticker to `data/snapshots.csv`.

### Scheduler

`APScheduler.BackgroundScheduler` is started inside a daemon thread at module import time (so it works under both `gunicorn` and `python main.py`):

```python
threading.Thread(target=_startup, daemon=True).start()
```

Jobs:
- `fetch_prices` every **5 minutes**
- `fetch_history_data(30)` every **6 hours**

### Alert Threshold

Any ticker with `abs(change_pct) >= 5` triggers an alert entry in `CACHE["alerts"]`. Change the threshold in `fetch_prices()`.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Renders `templates/index.html` |
| GET | `/api/prices` | Returns full cache: tickers, alerts, tier metadata, ticker order |
| GET | `/api/history` | Returns 30-day close history per symbol |
| POST | `/api/refresh` | Forces an immediate `fetch_prices()` call |
| GET | `/api/download/csv` | Streams `data/snapshots.csv` as a file download |

---

## Frontend

`templates/index.html` is a self-contained single page using:
- **Bootstrap 4** (CDN) for layout and table styling
- **Chart.js** (CDN) for a bar chart of the top 10 tickers by price
- **Vanilla JS** (`fetch`, async/await, DOM manipulation) — no build step

Key frontend functions:
- `loadData()` — polls `/api/prices`, updates `allStocks`, triggers render
- `applyFilters()` — filters `allStocks` by tier dropdown and search input, then calls `renderTable()`
- `renderChart(stocks)` — destroys and recreates the Chart.js bar chart
- `renderAlerts(alerts)` — renders Bootstrap alert divs for movers ≥ ±5%

The frontend does **not** auto-poll on a timer; refresh is triggered manually or via the "Refresh Now" button.

---

## Dependencies

```
Flask==2.3.2
APScheduler==3.10.4
yfinance==0.2.28
pandas==2.0.3
gunicorn==21.2.0
```

All versions are pinned. When updating dependencies, test locally before bumping versions, as `yfinance` API changes frequently.

---

## Development Setup

```bash
pip install -r requirements.txt
python main.py
# Visit http://localhost:5000
```

For production-equivalent local testing:

```bash
gunicorn main:app --bind 0.0.0.0:5000
```

There is no `.env` file or environment variable configuration required — the only env var used is `PORT` (defaults to `5000`).

---

## Deployment

### Render.com (primary)

Configured via `render.yaml`:
- **Build:** `pip install -r requirements.txt`
- **Start:** `gunicorn main:app --bind 0.0.0.0:$PORT`
- **Region:** Oregon
- **Plan:** Free (sleeps after 15 min of inactivity)
- **Auto-deploy:** On every push to the connected branch

The entrypoint is `main:app` (file `main.py`, Flask instance `app`).

### CI (GitHub Actions)

`.github/workflows/python-package-conda.yml` runs on every push:
1. Checks out code
2. Sets up Python 3.10 with `pip`
3. Installs `requirements.txt`
4. Runs `flake8` — fatal errors only (E9, F63, F7, F82), then advisory lint at max-line-length 127

There are no automated tests beyond linting.

---

## Common Tasks for AI Assistants

### Add or Remove a Ticker

Edit the `TIERS` dict in `main.py`. `ALL_TICKERS` and `TICKER_META` are auto-derived — do not edit them manually.

Also update the `<select id="tierFilter">` options in `templates/index.html` if a new tier is added.

### Change the Refresh Interval

In `main.py`, inside `start_scheduler()`:

```python
scheduler.add_job(fetch_prices, "interval", minutes=5, ...)
```

### Change the Alert Threshold

In `fetch_prices()` in `main.py`:

```python
if abs(change) >= 5:
```

### Add a New API Endpoint

Add a `@app.route(...)` function in `main.py` following the existing pattern. Return `jsonify(...)` for JSON responses.

### Modify the Dashboard UI

Edit `templates/index.html`. There is no build step — changes take effect immediately on the next server request.

---

## Conventions

- **Python style:** Follow PEP 8. Max line length is 127 (matching flake8 config). Use `f-strings` for formatting.
- **No type annotations** are currently used; do not add them unless specifically requested.
- **Error handling:** Data-fetch loops use bare `except Exception: pass` to silently skip bad tickers. This is intentional to avoid crashing the scheduler on transient Yahoo Finance errors.
- **No ORM / database:** All persistence is flat CSV (`data/snapshots.csv`). Do not introduce a database without explicit discussion.
- **No test suite:** Only flake8 linting exists. Do not assume tests exist when making changes.
- **Frontend has no bundler:** Do not introduce npm, webpack, or any JS build tooling. Keep the frontend as plain HTML/JS.
- **Do not commit `data/`:** The `data/` directory is runtime-generated and should not be committed.

---

## Branch Strategy

- `master` — stable, auto-deploys to Render on push
- Feature work is done on `claude/<description>` branches and merged via PR

Always push feature branches and open PRs rather than pushing directly to `master`.
