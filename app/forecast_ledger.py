"""Forecast ledger: persist every prediction, then grade it against reality.

A forecasting system that never scores itself is indistinguishable from one that
makes numbers up. Every row the engine publishes is written here with the
probability it claimed, and once the target session closes it is resolved
against the realized return and scored.

Metrics reported:

* **Hit rate** — fraction of directional calls that landed. Intuitive, but a
  weak measure: it ignores how confident each call was.
* **Brier score** — mean squared error of the probability, ``(p - outcome)^2``.
  Lower is better. This is the primary metric because it is a strictly proper
  scoring rule: it is minimised only by reporting your true belief, so it cannot
  be gamed by shading probabilities toward the extremes.
* **Brier skill score** — improvement over always predicting 50/50
  (``1 - brier / 0.25``). Positive means the engine beats a coin flip; zero or
  negative means it does not, and the board should say so.
* **Log loss** — punishes confident misses far harder than Brier does.
* **Calibration table** — of the sessions forecast at 55-60%, how many were
  actually up? A well-calibrated engine tracks the diagonal.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from app.models import get_db, query_db

logger = logging.getLogger(__name__)

# Probabilities are clipped before scoring so a single confident miss cannot
# send log loss to infinity.
_EPS = 1e-6

BASELINE_BRIER = 0.25  # always predicting 0.5


def record_forecasts(rows: list[dict]) -> int:
    """Persist forecasts, one row per (ticker, session).

    Re-running a scan for the same session updates the stored forecast rather
    than creating a duplicate, but a row that has already been resolved is left
    alone — rewriting history after the outcome is known would corrupt the
    scorecard.
    """
    if not rows:
        return 0

    written = 0
    with get_db() as db:
        for row in rows:
            cur = db.execute(
                """
                INSERT INTO forecasts (
                    ticker, asof_date, horizon, direction, p_up,
                    expected_move_pct, sigma_pct, conviction, source,
                    catalyst_shift, vol_multiplier, rationale, ref_close
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, asof_date, horizon) DO UPDATE SET
                    direction = excluded.direction,
                    p_up = excluded.p_up,
                    expected_move_pct = excluded.expected_move_pct,
                    sigma_pct = excluded.sigma_pct,
                    conviction = excluded.conviction,
                    source = excluded.source,
                    catalyst_shift = excluded.catalyst_shift,
                    vol_multiplier = excluded.vol_multiplier,
                    rationale = excluded.rationale,
                    ref_close = excluded.ref_close
                WHERE forecasts.resolved_at IS NULL
                """,
                (
                    row["ticker"], row["asof_date"], row.get("horizon", "next_session"),
                    row["direction"], row["p_up"], row.get("expected_move_pct"),
                    row.get("sigma_pct"), row.get("conviction"),
                    row.get("source", "quant"), row.get("catalyst_shift", 0.0),
                    row.get("vol_multiplier", 1.0), row.get("rationale", ""),
                    row.get("ref_close"),
                ),
            )
            written += cur.rowcount or 0
    return written


def pending_forecasts(limit: int = 500) -> list[dict]:
    """Unresolved forecasts, oldest first."""
    return query_db(
        "SELECT * FROM forecasts WHERE resolved_at IS NULL "
        "ORDER BY asof_date ASC LIMIT ?",
        (limit,),
    )


def resolve_forecasts(bars_by_ticker: dict[str, list[dict]]) -> int:
    """Score every pending forecast whose target session has now closed.

    ``bars_by_ticker`` maps a ticker to its recent OHLCV bars. The target
    session is the first bar strictly after the forecast's ``asof_date``; if no
    such bar exists yet the forecast stays pending.
    """
    pending = pending_forecasts()
    if not pending:
        return 0

    resolved = 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as db:
        for row in pending:
            bars = bars_by_ticker.get(row["ticker"])
            if not bars:
                continue

            target = next(
                (b for b in bars if b.get("date", "") > row["asof_date"]), None
            )
            if not target:
                continue

            ref_close = row["ref_close"]
            target_close = target.get("close")
            if not ref_close or not target_close or ref_close <= 0:
                continue

            realized_pct = (target_close - ref_close) / ref_close * 100.0
            outcome = 1 if realized_pct > 0 else 0

            p = min(max(float(row["p_up"]), _EPS), 1.0 - _EPS)
            brier = (p - outcome) ** 2
            log_loss = -(math.log(p) if outcome else math.log(1.0 - p))

            db.execute(
                """
                UPDATE forecasts SET
                    target_date = ?, resolved_at = ?, realized_return_pct = ?,
                    outcome = ?, brier = ?, log_loss = ?
                WHERE id = ?
                """,
                (target["date"], now, round(realized_pct, 4), outcome,
                 round(brier, 6), round(log_loss, 6), row["id"]),
            )
            resolved += 1

    if resolved:
        logger.info("Resolved %d forecast(s) against realized outcomes", resolved)
    return resolved


def scorecard(days: int = 90, ticker: str | None = None) -> dict:
    """Aggregate accuracy over resolved forecasts in the trailing window."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    sql = (
        "SELECT ticker, direction, p_up, conviction, source, outcome, brier, "
        "log_loss, realized_return_pct FROM forecasts "
        "WHERE resolved_at IS NOT NULL AND asof_date >= ?"
    )
    args: list = [cutoff]
    if ticker:
        sql += " AND ticker = ?"
        args.append(ticker.upper())

    rows = query_db(sql, tuple(args))
    if not rows:
        return {
            "resolved": 0,
            "window_days": days,
            "message": "No forecasts have resolved yet. Accuracy appears here "
                       "once the first forecast session closes.",
        }

    n = len(rows)
    brier = sum(r["brier"] for r in rows) / n
    log_loss = sum(r["log_loss"] for r in rows) / n
    mean_p = sum(r["p_up"] for r in rows) / n
    base_rate = sum(r["outcome"] for r in rows) / n

    # Hit rate is only meaningful for rows that actually took a side.
    directional = [r for r in rows if r["direction"] in ("bull", "bear")]
    hits = sum(
        1 for r in directional
        if (r["direction"] == "bull") == bool(r["outcome"])
    )
    hit_rate = hits / len(directional) if directional else None

    # High-conviction subset: does confidence actually mean anything?
    confident = [r for r in directional if (r["conviction"] or 0) >= 60]
    confident_hits = sum(
        1 for r in confident if (r["direction"] == "bull") == bool(r["outcome"])
    )

    return {
        "resolved": n,
        "window_days": days,
        "ticker": ticker.upper() if ticker else None,
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
        "calibration": _calibration_bins(rows),
        "by_source": _by_source(rows),
    }


def _calibration_bins(rows: list[dict]) -> list[dict]:
    """Bucket forecasts by claimed probability and report the realized rate."""
    edges = [0.0, 0.40, 0.45, 0.475, 0.50, 0.525, 0.55, 0.60, 1.01]
    bins = []
    for lo, hi in zip(edges, edges[1:]):
        bucket = [r for r in rows if lo <= r["p_up"] < hi]
        if not bucket:
            continue
        bins.append({
            "range": f"{lo:.3f}-{min(hi, 1.0):.3f}",
            "count": len(bucket),
            "mean_forecast": round(sum(r["p_up"] for r in bucket) / len(bucket), 4),
            "realized_up_rate": round(
                sum(r["outcome"] for r in bucket) / len(bucket), 4
            ),
        })
    return bins


def _by_source(rows: list[dict]) -> list[dict]:
    """Split the scorecard by whether the catalyst overlay was applied."""
    out = []
    for source in sorted({r["source"] or "quant" for r in rows}):
        bucket = [r for r in rows if (r["source"] or "quant") == source]
        brier = sum(r["brier"] for r in bucket) / len(bucket)
        out.append({
            "source": source,
            "count": len(bucket),
            "brier": round(brier, 4),
            "brier_skill_score": round(1.0 - brier / BASELINE_BRIER, 4),
        })
    return out


def recent_resolved(limit: int = 50, ticker: str | None = None) -> list[dict]:
    """Most recently graded forecasts, newest first."""
    sql = (
        "SELECT ticker, asof_date, target_date, direction, p_up, conviction, "
        "expected_move_pct, realized_return_pct, outcome, brier, source, rationale "
        "FROM forecasts WHERE resolved_at IS NOT NULL"
    )
    args: list = []
    if ticker:
        sql += " AND ticker = ?"
        args.append(ticker.upper())
    sql += " ORDER BY target_date DESC, ticker ASC LIMIT ?"
    args.append(limit)
    return query_db(sql, tuple(args))
