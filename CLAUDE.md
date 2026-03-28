# Iran Investment Tracker

Flask web application that tracks 36 investment tickers from the Iran Regime Change Investment Plan across 5 tiers.

## Quick Start

```bash
pip install -r requirements.txt
python main.py  # Runs on port 5000
```

## Architecture

- **Framework**: Flask with Jinja2 templates, Bootstrap 5 UI (glassmorphism dark theme)
- **Data**: Yahoo Finance via `yfinance`, auto-refreshes every 5 min (APScheduler)
- **Storage**: SQLite (`data/tracker.db`), CSV snapshots (`data/snapshots.csv`)
- **ML**: Voting ensemble (RandomForest + HistGradientBoosting + MLP) with Gaussian Mixture regime detection

## Key Directories

- `app/` — Flask application package
  - `config.py` — Tier definitions and 36 ticker symbols
  - `routes/` — API endpoints (dashboard, portfolio, analysis, alerts, backtest, etc.)
  - `models.py` — SQLite models
  - `data_fetcher.py` — Yahoo Finance integration + caching
  - `ml_predictor.py` — ML prediction ensemble
  - `indicators.py` — Technical indicators
  - `backtester.py`, `optimizer.py`, `pairs_trading.py` — Quantitative analysis
- `templates/` — Jinja2 HTML templates
- `main.py` — Entry point

## Commands

- **Run server**: `python main.py`
- **Train ML model**: `python train_model.py`
- **Lint**: `flake8 . --max-line-length=127`

## Conventions

- Python 3.10+
- Max line length: 127 characters
- CI runs flake8 on push (critical errors only block)
- Data directory (`data/`) is gitignored
