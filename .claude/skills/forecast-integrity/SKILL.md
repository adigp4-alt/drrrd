---
name: forecast-integrity
description: Use when changing anything under app/forecast_*.py, app/market_data.py, the /foresight routes, the backtest, or the accuracy ledger — the invariants that keep this project's published probabilities honest (no lookahead, bounded catalyst overlay, proper scoring, backtests never touching the live ledger) and the commands that prove they still hold.
---

# Forecast Integrity

## Overview

This project publishes probabilities and then grades itself on them. That only
means something while a short list of properties holds. Each one is load-bearing
and each one is cheap to break by accident.

**Core principle:** A forecast engine that can quietly cheat is worse than no
engine, because it manufactures confidence. Every change here is judged on
whether it preserves the ability to be wrong in public.

**Announce at start:** "I'm using the forecast-integrity skill for this change."

## The invariants

### 1. No lookahead — ever

`app/forecast_backtest.py` replays strictly walk-forward: the forecast for
session `i + 1` is handed `bars[:i + 1]` and nothing else. Volatility, every
directional signal and the volatility percentile are recomputed from that
truncated slice.

- Never pass a full history to a replayed forecast and slice afterwards.
- Never precompute anything across the whole series (a rolling mean, a
  percentile, a scaler fit) and reuse it inside the replay loop.
- `tests/test_backtest.py::NoLookaheadTests::test_future_bars_cannot_change_a_forecast`
  rewrites the future and asserts forecasts do not move. If you touch the
  replay, run it and read the output.

### 2. Backtest results never enter the ledger

`/foresight/api/backtest` reports simulated history. The `forecasts` table holds
live, pre-registered calls only. Writing replay output into it inflates the
track record with predictions nobody actually published. Keep the write paths
separate.

### 3. The catalyst overlay is bounded and optional

`app/forecast_catalyst.py` returns a *tilt*, never a forecast:

- `logit_shift` clamped to ±`MAX_LOGIT_SHIFT` (0.6)
- `vol_multiplier` clamped to `[MIN_VOL_MULTIPLIER, MAX_VOL_MULTIPLIER]` (0.7–1.8)
- The numbers on the board always originate in market data.

Every failure path degrades to the pure quant forecast rather than raising: no
`ANTHROPIC_API_KEY`, no network, a refusal, a malformed response. **An unset key
is a supported configuration, not an error.** The key is read from the server
environment and must never reach the browser or a template.

The overlay is excluded from backtests on purpose — past web research cannot be
reconstructed, and asking a model today about a past session leaks the outcome.
Do not "fix" that exclusion.

### 4. Scoring stays proper

- **Brier score** is the primary metric because it is strictly proper — it is
  minimised only by reporting your true belief. Do not replace it with hit rate.
- **Skill** is measured against the coin flip (`1 - brier / 0.25`). Negative
  skill must be displayed as negative.
- **Always-up** is reported alongside, because equities drift and a blind "up"
  already beats 50%. An engine that cannot beat it has no directional edge.
- **Doji is a first-class call** (`DOJI_EDGE_RATIO` in `app/forecast_quant.py`)
  and is excluded from the hit rate. "No edge" is an allowed answer; do not
  force a direction to make the board look decisive.

### 5. The engine cannot claim a large edge

Probability bounds, `MAX_COMPOSITE_Z`, drift shrink and the doji threshold exist
so the engine cannot claim more than a modest edge on a daily candle. Widening
them to make the board look smarter is the failure mode this project is built
against. `tests/test_forecast.py::QuantForecastTests::test_probability_never_escapes_designed_bounds`
is the guard.

### 6. Market data has three independent paths

`app/market_data.py` tries Yahoo's chart API directly, then yfinance, then
Stooq — each asked only for the tickers the previous one could not supply. Keep
that property: a provider change must not turn a partial success into a total
failure. Isolate a single path with `MARKET_DATA_SOURCE=chart|yfinance|yahoo|stooq`
and probe it with `python diagnose.py` before blaming the engine for empty bars.

### 7. Storage goes through one module

All relational access funnels through `get_db`, `query_db` and `execute_db` in
`app/models.py`, using SQLite-style `?` placeholders that are rewritten for
Postgres there. Never open a connection or hand-write `%s` in a caller — that is
how the SQLite and Postgres paths silently diverge.

## Verification

Claim nothing until these have run and you have read the output:

```bash
python -m unittest discover -s tests          # the whole suite
python -m unittest tests.test_backtest         # after any replay change
python -m unittest tests.test_forecast         # after any engine/overlay change

# the CI gate (.github/workflows/python-package-conda.yml)
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

python diagnose.py                             # market-data providers, standalone
python main.py                                 # then open /foresight
```

Pair this with `verification-before-completion`: evidence before assertions.
For a UI change to the foresight board, drive the real page with
`webapp-testing` rather than asserting it renders.

## Red flags

Stop and reconsider if you catch yourself about to:

- Compute a statistic over the full price series inside a backtest loop
- Persist backtest output to the `forecasts` table "just for the demo"
- Raise instead of degrading when the Anthropic API is unavailable
- Widen a clamp or a bound to make a number look better
- Replace Brier with hit rate, or hide a negative skill score
- Report a forecast the doji rule says the engine does not have
- Add a fourth data provider that runs *instead of* the fallback chain
- Log, template, or return `ANTHROPIC_API_KEY`

Every one of these makes the board look better and the project worthless.
