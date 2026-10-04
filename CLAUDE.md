# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A Flask dashboard tracking 36 tickers, plus **ForesightTape** (`/foresight`) — a
next-session probability board built from a quant prior (`app/forecast_quant.py`)
and an optional, bounded catalyst overlay (`app/forecast_catalyst.py`). Every
published forecast is stored and graded once its session closes.

## Commands

```bash
pip install -r requirements.txt

python main.py                        # serve on $PORT (default 5000)
python -m unittest discover -s tests  # full suite — 182 tests
python diagnose.py                    # probe the market-data providers standalone

# the CI gate (.github/workflows/python-package-conda.yml)
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
```

Run the suite and the lint gate before claiming a change works. Both are fast.

## Layout

- `app/forecast_quant.py` — Student-t prior over the next session's return
- `app/forecast_catalyst.py` — optional Claude-researched tilt, hard-clamped
- `app/forecast_backtest.py` — strictly walk-forward replay, no lookahead
- `app/forecast_ledger.py` — stores and grades live forecasts (Brier, skill, calibration)
- `app/market_data.py` — Yahoo chart API → yfinance → Stooq fallback chain
- `app/models.py` — the only module that talks to SQLite/Postgres directly
- `app/routes/` — one blueprint per surface; `forecast.py` serves `/foresight`

## Configuration

All optional. Defaults run standalone with no keys.

| Variable | Effect |
| --- | --- |
| `ANTHROPIC_API_KEY` | Enables the catalyst overlay. Unset is a supported configuration, not an error. Server-side only — it must never reach the browser. |
| `DATABASE_URL` | Switches storage from SQLite to Postgres. |
| `DATA_DIR` | Where the SQLite DB and CSV snapshots live. Point at a mounted volume to survive redeploys. |
| `MARKET_DATA_SOURCE` | Pins the provider chain to one path for diagnosis: `chart`, `yfinance`, `yahoo`, `stooq`. |

## Skills

Project skills live in `.claude/skills/` and load automatically. See
`.claude/skills/README.md` for the full index and provenance.

**Read `forecast-integrity` before touching `app/forecast_*.py`,
`app/market_data.py`, the `/foresight` routes, the backtest, or the ledger.** It
documents the invariants that keep the published probabilities honest — no
lookahead, a bounded overlay, proper scoring, backtests that never write to the
live ledger — and which test pins each one down.

The imported engineering skills (`test-driven-development`,
`systematic-debugging`, `verification-before-completion`, `brainstorming`,
`writing-plans`, the code-review pair) apply to work anywhere in the repo.
`webapp-testing` drives the dashboard in a real browser.
