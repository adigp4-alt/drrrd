"""Walk-forward backtest: does the quant engine actually have any skill?

The live ledger in :mod:`app.forecast_ledger` only accumulates evidence one
session at a time, so a fresh deployment has an empty scorecard for weeks. This
module answers the same question immediately by replaying the forecaster over
history.

**The one property that matters here is the absence of lookahead.** A backtest
that lets the model see the future is worse than no backtest, because it
manufactures confidence. So the replay is strictly walk-forward: to forecast
session ``i + 1`` the engine is handed ``bars[:i + 1]`` and nothing else — the
same slice it would have had in production on the evening of session ``i``. The
volatility estimate, every directional signal and the volatility percentile are
all recomputed from that truncated history. There is a test that enforces this
by rewriting the future and asserting the forecasts do not move.

**The catalyst overlay is deliberately excluded.** There is no way to reconstruct
what the web said on a given past date, and asking a model today about a past
session leaks the outcome. So these numbers isolate the quantitative engine —
which is the honest thing to measure anyway.

Two baselines are reported alongside the engine, because a hit rate on its own
is close to meaningless for daily equity data:

* **Coin flip** (always 0.5) — Brier 0.25 by construction. The skill score is
  measured against this.
* **Always up** — equities drift upward, so a model that blindly predicts "up"
  every session posts a hit rate above 50%. If the engine cannot beat this, its
  directional hit rate is noise dressed up as insight.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from app.forecast_engine import fetch_bars
from app.forecast_quant import MIN_BARS, forecast_next_session

logger = logging.getLogger(__name__)

# Sessions of history required before the first forecast. Above the engine's own
# MIN_BARS so the volatility percentile has a meaningful window to rank against.
DEFAULT_WARMUP = 150

# Cap on replayed sessions per ticker, to bound a request's work.
MAX_SESSIONS = 500

_EPS = 1e-6
BASELINE_BRIER = 0.25


@dataclass
class Prediction:
    """One walk-forward forecast and the outcome that followed it."""

    ticker: str
    asof_date: str
    target_date: str
    direction: str
    p_up: float
    conviction: int
    expected_move_pct: float
    sigma_pct: float
    vol_regime: str
    realized_return_pct: float
    outcome: int

    @property
    def brier(self) -> float:
        return (self.p_up - self.outcome) ** 2

    @property
    def log_loss(self) -> float:
        p = min(max(self.p_up, _EPS), 1.0 - _EPS)
        return -(math.log(p) if self.outcome else math.log(1.0 - p))


@dataclass
class BacktestResult:
    predictions: list[Prediction] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)


def replay_ticker(ticker: str, bars: list[dict], warmup: int = DEFAULT_WARMUP,
                  max_sessions: int = MAX_SESSIONS) -> list[Prediction]:
    """Replay the forecaster across ``bars`` without ever showing it the future."""
    warmup = max(warmup, MIN_BARS)
    if len(bars) < warmup + 2:
        return []

    # Replay the most recent `max_sessions` sessions, keeping the full history
    # behind each one available to the model.
    first = max(warmup, len(bars) - 1 - max_sessions)

    predictions = []
    for i in range(first, len(bars) - 1):
        history = bars[:i + 1]          # everything known as of session i
        target = bars[i + 1]            # the session being predicted

        forecast = forecast_next_session(ticker, history)
        if forecast is None:
            continue

        ref_close = history[-1].get("close")
        target_close = target.get("close")
        if not ref_close or not target_close or ref_close <= 0:
            continue

        realized_pct = (target_close - ref_close) / ref_close * 100.0
        predictions.append(Prediction(
            ticker=ticker,
            asof_date=history[-1]["date"],
            target_date=target["date"],
            direction=forecast.direction,
            p_up=forecast.p_up,
            conviction=forecast.conviction,
            expected_move_pct=forecast.expected_move_pct,
            sigma_pct=forecast.sigma_pct,
            vol_regime=forecast.vol_regime,
            realized_return_pct=round(realized_pct, 4),
            outcome=1 if realized_pct > 0 else 0,
        ))
    return predictions


def run_backtest(tickers: list[str], period: str = "2y",
                 warmup: int = DEFAULT_WARMUP,
                 max_sessions: int = MAX_SESSIONS,
                 bars_by_ticker: dict[str, list[dict]] | None = None) -> dict:
    """Replay every ticker and summarize the engine's out-of-sample accuracy."""
    if bars_by_ticker is None:
        bars_by_ticker = fetch_bars(tickers, period=period)

    result = BacktestResult()
    for ticker in tickers:
        bars = bars_by_ticker.get(ticker)
        if not bars:
            result.skipped.append({"ticker": ticker, "reason": "no market data"})
            continue
        predictions = replay_ticker(ticker, bars, warmup=warmup,
                                    max_sessions=max_sessions)
        if not predictions:
            result.skipped.append({"ticker": ticker, "reason": "insufficient history"})
            continue
        result.predictions.extend(predictions)

    summary = summarize(result.predictions)
    summary["skipped"] = result.skipped
    summary["tickers_tested"] = len(
        {p.ticker for p in result.predictions}
    )
    summary["catalyst_overlay"] = False
    return summary


def summarize(predictions: list[Prediction]) -> dict:
    """Turn a set of graded predictions into the accuracy report."""
    n = len(predictions)
    if not n:
        return {
            "predictions": 0,
            "message": "Not enough history to replay any forecasts.",
        }

    brier = sum(p.brier for p in predictions) / n
    log_loss = sum(p.log_loss for p in predictions) / n
    base_rate = sum(p.outcome for p in predictions) / n
    mean_p = sum(p.p_up for p in predictions) / n

    directional = [p for p in predictions if p.direction in ("bull", "bear")]
    hits = sum(1 for p in directional if (p.direction == "bull") == bool(p.outcome))
    hit_rate = hits / len(directional) if directional else None

    # Baselines. "Always up" is the one that matters: equities drift, so a naive
    # always-bullish caller already beats 50% and the engine has to clear it.
    always_up_brier = sum((1.0 - p.outcome) ** 2 for p in predictions) / n

    confident = [p for p in directional if p.conviction >= 60]
    confident_hits = sum(
        1 for p in confident if (p.direction == "bull") == bool(p.outcome)
    )

    dates = sorted(p.asof_date for p in predictions)

    return {
        "predictions": n,
        "date_range": {"start": dates[0], "end": dates[-1]},
        "brier": round(brier, 4),
        "brier_skill_score": round(1.0 - brier / BASELINE_BRIER, 4),
        "log_loss": round(log_loss, 4),
        "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
        "directional_calls": len(directional),
        "doji_calls": n - len(directional),
        "high_conviction_calls": len(confident),
        "high_conviction_hit_rate": (
            round(confident_hits / len(confident), 4) if confident else None
        ),
        "mean_forecast_p_up": round(mean_p, 4),
        "realized_up_rate": round(base_rate, 4),
        "baselines": {
            "coin_flip_brier": BASELINE_BRIER,
            "always_up_brier": round(always_up_brier, 4),
            "always_up_hit_rate": round(base_rate, 4),
            "beats_coin_flip": bool(brier < BASELINE_BRIER),
            "beats_always_up": bool(brier < always_up_brier),
        },
        "calibration": _calibration(predictions),
        "by_regime": _by_regime(predictions),
        "by_ticker": _by_ticker(predictions),
    }


def _calibration(predictions: list[Prediction]) -> list[dict]:
    edges = [0.0, 0.40, 0.45, 0.475, 0.50, 0.525, 0.55, 0.60, 1.01]
    bins = []
    for lo, hi in zip(edges, edges[1:]):
        bucket = [p for p in predictions if lo <= p.p_up < hi]
        if not bucket:
            continue
        bins.append({
            "range": f"{lo:.3f}-{min(hi, 1.0):.3f}",
            "count": len(bucket),
            "mean_forecast": round(sum(p.p_up for p in bucket) / len(bucket), 4),
            "realized_up_rate": round(
                sum(p.outcome for p in bucket) / len(bucket), 4
            ),
        })
    return bins


def _by_regime(predictions: list[Prediction]) -> list[dict]:
    out = []
    for regime in ("calm", "normal", "stressed"):
        bucket = [p for p in predictions if p.vol_regime == regime]
        if not bucket:
            continue
        brier = sum(p.brier for p in bucket) / len(bucket)
        out.append({
            "regime": regime,
            "count": len(bucket),
            "brier": round(brier, 4),
            "brier_skill_score": round(1.0 - brier / BASELINE_BRIER, 4),
            "realized_up_rate": round(
                sum(p.outcome for p in bucket) / len(bucket), 4
            ),
        })
    return out


def _by_ticker(predictions: list[Prediction]) -> list[dict]:
    out = []
    for ticker in sorted({p.ticker for p in predictions}):
        bucket = [p for p in predictions if p.ticker == ticker]
        brier = sum(p.brier for p in bucket) / len(bucket)
        directional = [p for p in bucket if p.direction in ("bull", "bear")]
        hits = sum(
            1 for p in directional if (p.direction == "bull") == bool(p.outcome)
        )
        out.append({
            "ticker": ticker,
            "count": len(bucket),
            "brier": round(brier, 4),
            "brier_skill_score": round(1.0 - brier / BASELINE_BRIER, 4),
            "hit_rate": round(hits / len(directional), 4) if directional else None,
        })
    out.sort(key=lambda r: r["brier_skill_score"], reverse=True)
    return out
