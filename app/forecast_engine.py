"""Forecast orchestration: quant prior + catalyst overlay -> published board.

This is the module the routes talk to. It owns the pipeline:

    OHLCV bars -> quant prior -> (optional) catalyst tilt -> blended forecast
              -> ledger -> board rows

Blending happens in log-odds space, which is the natural scale for combining
evidence about a probability: a tilt of +0.4 means the same thing whether the
prior was 50% or 60%, and the result can never leave (0, 1). The expected move
is then re-derived from the blended probability and volatility so the published
row stays internally consistent — the probability, the direction and the
expected range always describe the same distribution.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime

import pandas as pd
import yfinance as yf

from app.config import ALL_TICKERS, TICKER_META
from app import market_data
from app.market_data import extract_symbol_frame
from app.forecast_quant import (
    classify_direction,
    conviction_score,
    forecast_next_session,
    signal_agreement,
    student_t_ppf,
    t_scale_for_sigma,
)
from app import forecast_catalyst
from app import forecast_ledger

logger = logging.getLogger(__name__)

# How much history to pull per ticker. A year gives the volatility-percentile
# calculation a full cycle to rank against.
HISTORY_PERIOD = "1y"

MAX_WATCHLIST_TICKERS = 12


def _logit(p: float) -> float:
    p = min(max(p, 1e-9), 1.0 - 1e-9)
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def fetch_bars(tickers: list[str], period: str = HISTORY_PERIOD) -> dict[str, list[dict]]:
    """Batch-download OHLCV bars for ``tickers``."""
    bars, _ = fetch_bars_with_reasons(tickers, period=period)
    return bars


# Which providers each MARKET_DATA_SOURCE setting permits, in the order they
# are tried. "chart" and "yfinance" exist to isolate one path when diagnosing.
_PROVIDER_MODES = {
    "auto":     ("chart", "yfinance", "stooq"),
    "yahoo":    ("chart", "yfinance"),
    "stooq":    ("stooq",),
    "chart":    ("chart",),
    "yfinance": ("yfinance",),
}


def fetch_bars_with_reasons(
    tickers: list[str], period: str = HISTORY_PERIOD
) -> tuple[dict[str, list[dict]], list[str]]:
    """Fetch OHLCV bars from the first provider that answers, per ticker.

    Providers are tried in order (see ``market_data`` for why there are three),
    each one asked only for the tickers still missing. The direct chart API goes
    first because it has the least that can break: no library version to drift
    out of sync with Yahoo, and no cookie/crumb handshake to fail silently.

    Returns ``(bars_by_ticker, reasons)``. Failures are collected rather than
    swallowed: an empty board with no explanation is indistinguishable between a
    blocked IP, a yfinance version change and a bad ticker list, and those need
    completely different fixes. Callers surface ``reasons`` to the user.
    """
    if not tickers:
        return {}, []

    unique = sorted(set(tickers))
    reasons: list[str] = []
    providers = _PROVIDER_MODES.get(market_data.SOURCE_MODE,
                                    _PROVIDER_MODES["auto"])

    out: dict[str, list[dict]] = {}
    # Only failures land here, so a clean run on the primary provider leaves it
    # empty and the board reports nothing at all — which is what "it just
    # worked" should look like.
    failures: list[str] = []

    for name in providers:
        missing = [t for t in unique if t not in out]
        if not missing:
            break

        try:
            recovered, detail = _PROVIDERS[name](missing, period)
        except Exception as exc:
            recovered, detail = {}, f"{type(exc).__name__}: {exc}"
            logger.error("Provider %s raised: %s", name, detail)

        if recovered:
            out.update(recovered)
            # Worth saying only when an earlier provider had already failed;
            # otherwise this is just the normal path doing its job.
            if failures:
                reasons.append(
                    f"{_PROVIDER_LABELS[name]} supplied {len(recovered)} "
                    f"ticker(s) that earlier sources could not."
                )
        if detail:
            failures.append(f"{_PROVIDER_LABELS[name]}: {detail}")

    missing = [t for t in unique if t not in out]
    if not out:
        reasons.insert(0, (
            "No market data from any source. " + "; ".join(failures)
            + ". Open /foresight/api/diagnostics for a per-layer breakdown."
        ))
    elif missing:
        reasons.append("No data from any source for: " + ", ".join(missing[:10]))

    return out, reasons


def _fetch_chart(tickers: list[str], period: str
                 ) -> tuple[dict[str, list[dict]], str]:
    """Provider 1 — Yahoo's chart endpoint, called directly."""
    out = market_data.fetch_yahoo_chart_many(tickers, period=period)
    missing = [t for t in tickers if t not in out]
    if not missing:
        return out, ""
    return out, f"no data for {len(missing)} of {len(tickers)} ticker(s)"


def _bars_from_frame(raw, symbol: str) -> tuple[list[dict], str]:
    """Pull one symbol's bars out of a yfinance frame.

    Returns ``(bars, failure_reason)`` — exactly one of which is truthy. The
    reason is kept because a frame that parses to nothing means a response-shape
    change, which needs a different fix than a data outage.
    """
    try:
        df = extract_symbol_frame(raw, symbol)
        if df is None:
            return [], f"{symbol} (not present in response)"
        df = df.dropna(subset=["Close", "Open", "High", "Low"])
        if df.empty:
            return [], f"{symbol} (no rows)"
        bars = [{
            "date": date.strftime("%Y-%m-%d"),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]) if pd.notna(row["Volume"]) else 0,
        } for date, row in df.iterrows()]
        return (bars, "") if bars else ([], f"{symbol} (no usable bars)")
    except (KeyError, ValueError, TypeError) as exc:
        return [], f"{symbol} ({type(exc).__name__}: {exc})"


def _fetch_yfinance(tickers: list[str], period: str
                    ) -> tuple[dict[str, list[dict]], str]:
    """Provider 2 — yfinance's batch download.

    Kept behind the direct chart call because this is the path that breaks when
    Yahoo changes its handshake or yfinance changes its response shape, but it
    carries retry and session handling that sometimes succeeds anyway.
    """
    raw = None
    try:
        raw = yf.download(
            " ".join(tickers), period=period, group_by="ticker",
            progress=False, auto_adjust=False, threads=True,
        )
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        logger.error("yfinance download failed: %s", detail)
        return {}, detail

    if raw is None or raw.empty:
        # yfinance reports most failures by logging them and returning an empty
        # frame, so there is nothing more specific to say here.
        return {}, "empty response"

    out: dict[str, list[dict]] = {}
    parse_failures = []
    for symbol in tickers:
        bars, failure = _bars_from_frame(raw, symbol)
        if bars:
            out[symbol] = bars
        else:
            parse_failures.append(failure)

    if not parse_failures:
        return out, ""

    logger.warning("Could not parse bars for: %s", ", ".join(parse_failures[:10]))
    # A populated frame that yields *nothing* points at a response-shape change,
    # not a data outage. Keep that signal — it is the difference between
    # "upgrade yfinance" and "Yahoo is blocking you".
    if not out:
        return out, ("returned a response but nothing could be parsed from it, "
                     "which usually means a yfinance version change (" +
                     ", ".join(parse_failures[:3]) + ")")
    return out, f"could not parse {len(parse_failures)} ticker(s)"


def _fetch_stooq(tickers: list[str], period: str
                 ) -> tuple[dict[str, list[dict]], str]:
    """Provider 3 — Stooq, a different origin entirely."""
    out = market_data.fetch_stooq_many(tickers)
    missing = [t for t in tickers if t not in out]
    if not missing:
        return out, ""
    return out, f"no data for {len(missing)} of {len(tickers)} ticker(s)"


_PROVIDERS = {
    "chart": _fetch_chart,
    "yfinance": _fetch_yfinance,
    "stooq": _fetch_stooq,
}

_PROVIDER_LABELS = {
    "chart": "Yahoo chart API",
    "yfinance": "yfinance",
    "stooq": "Stooq",
}


def _blend(prior, tilt) -> dict:
    """Apply a bounded catalyst tilt to a quant prior.

    Returns a fully re-derived forecast, not a patched one: the blended
    probability and volatility jointly determine a new expected move, direction
    and conviction.
    """
    sigma = prior.sigma_pct / 100.0
    p_up = prior.p_up
    shift = 0.0
    vol_multiplier = 1.0

    if tilt is not None:
        shift = tilt.logit_shift
        vol_multiplier = tilt.vol_multiplier
        p_up = _sigmoid(_logit(prior.p_up) + shift)
        sigma = sigma * vol_multiplier

    scale = t_scale_for_sigma(sigma)
    expected_move = scale * student_t_ppf(p_up)
    direction = classify_direction(expected_move, sigma)

    conviction = conviction_score(
        p_up=p_up,
        agreement=signal_agreement(prior.signals),
        bars=prior.bars_used,
        volume_ratio=prior.signals.get("volume_ratio", 1.0),
        direction=direction,
    )
    # A catalyst-driven volatility expansion means *less* certainty about
    # direction, so widening the distribution should not raise conviction.
    if vol_multiplier > 1.2:
        conviction = int(conviction / vol_multiplier)

    return {
        "p_up": round(p_up, 4),
        "sigma_pct": round(sigma * 100, 3),
        "expected_move_pct": round(expected_move * 100, 3),
        "band_68_pct": round(student_t_ppf(0.84) * scale * 100, 3),
        "band_95_pct": round(student_t_ppf(0.975) * scale * 100, 3),
        "direction": direction,
        "conviction": max(1, min(100, conviction)),
        "catalyst_shift": round(shift, 4),
        "vol_multiplier": round(vol_multiplier, 3),
    }


def _quant_rationale(prior) -> str:
    """Plain-language summary of what drove the quant prior."""
    s = prior.signals
    parts = []
    labels = [
        ("momentum", "momentum"),
        ("trend", "20d trend"),
        ("reversal", "short-term reversal"),
        ("ma_gap", "mean-reversion pull"),
    ]
    ranked = sorted(labels, key=lambda kv: abs(s.get(kv[0], 0.0)), reverse=True)
    for key, label in ranked[:2]:
        value = s.get(key, 0.0)
        if abs(value) < 0.05:
            continue
        parts.append(f"{label} {'positive' if value > 0 else 'negative'} ({value:+.2f}σ)")
    if not parts:
        parts.append("no directional signal of size")
    return f"{', '.join(parts)}; {prior.vol_regime} volatility regime"


def build_forecasts(tickers: list[str], use_catalyst: bool = True,
                    persist: bool = True) -> dict:
    """Run the full pipeline for ``tickers`` and return the published board."""
    started = datetime.now()
    bars_by_ticker, fetch_reasons = fetch_bars_with_reasons(tickers)

    priors = []
    skipped = []
    for ticker in tickers:
        bars = bars_by_ticker.get(ticker)
        if not bars:
            skipped.append({"ticker": ticker, "reason": "no market data"})
            continue
        prior = forecast_next_session(ticker, bars)
        if prior is None:
            skipped.append({"ticker": ticker, "reason": "insufficient history"})
            continue
        priors.append(prior)

    if not priors:
        # Lead with the fetch-layer reason when there is one: "no market data"
        # is a symptom, and the cause is what the user needs.
        detail = fetch_reasons[0] if fetch_reasons else (
            "No ticker had enough clean history to forecast."
        )
        return {
            "rows": [],
            "skipped": skipped,
            "fetch_reasons": fetch_reasons,
            "catalyst_applied": False,
            "generated_at": started.strftime("%Y-%m-%d %H:%M:%S"),
            "error": detail,
            "diagnostics_url": "/foresight/api/diagnostics",
        }

    tilts: dict = {}
    if use_catalyst and forecast_catalyst.is_configured():
        tilts = forecast_catalyst.fetch_tilts(
            [p.to_dict() for p in priors],
            session_label=started.strftime("%A, %d %B %Y"),
        )

    rows = []
    for prior in priors:
        tilt = tilts.get(prior.ticker)
        blended = _blend(prior, tilt)
        meta = TICKER_META.get(prior.ticker, {})

        rationale = _quant_rationale(prior)
        if tilt is not None and tilt.is_material and tilt.rationale:
            rationale = f"{rationale}. Catalyst: {tilt.rationale}"

        rows.append({
            "ticker": prior.ticker,
            "name": meta.get("name", ""),
            "tier": meta.get("tier"),
            "asof_date": prior.asof_date,
            "ref_close": prior.ref_close,
            "direction": blended["direction"],
            "p_up": blended["p_up"],
            "expected_move_pct": blended["expected_move_pct"],
            "sigma_pct": blended["sigma_pct"],
            "band_68_pct": blended["band_68_pct"],
            "band_95_pct": blended["band_95_pct"],
            "conviction": blended["conviction"],
            "annualized_vol_pct": prior.annualized_vol_pct,
            "vol_regime": prior.vol_regime,
            "vol_percentile": prior.vol_percentile,
            "signals": prior.signals,
            "bars_used": prior.bars_used,
            "quant_p_up": prior.p_up,
            "catalyst_shift": blended["catalyst_shift"],
            "vol_multiplier": blended["vol_multiplier"],
            "catalyst": tilt.catalyst if tilt else "",
            "source": "blended" if (tilt and tilt.is_material) else "quant",
            "rationale": rationale,
        })

    rows.sort(key=lambda r: r["conviction"], reverse=True)

    if persist:
        try:
            forecast_ledger.record_forecasts(rows)
        except Exception as exc:
            logger.error("Failed to record forecasts: %s", exc)

    return {
        "rows": rows,
        "skipped": skipped,
        "fetch_reasons": fetch_reasons,
        "catalyst_applied": bool(tilts),
        "catalyst_available": forecast_catalyst.is_configured(),
        "generated_at": started.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round((datetime.now() - started).total_seconds(), 2),
    }


def build_market_board(use_catalyst: bool = True) -> dict:
    """Forecast every tracked ticker in the configured tiers."""
    return build_forecasts(ALL_TICKERS, use_catalyst=use_catalyst)


def build_watchlist(raw_input: str, use_catalyst: bool = True) -> dict:
    """Forecast an ad-hoc, user-supplied ticker list."""
    tickers = parse_tickers(raw_input)
    if not tickers:
        return {
            "rows": [], "skipped": [], "catalyst_applied": False,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": "No valid ticker symbols supplied.",
        }
    return build_forecasts(tickers, use_catalyst=use_catalyst)


# Yahoo symbol grammar: an optional index caret, then alphanumeric runs joined
# by single dots or dashes (SPY, BRK-B, BP.L, ^VIX). Anything else is junk.
_TICKER_RE = re.compile(r"^\^?[A-Z0-9]+(?:[.\-][A-Z0-9]+)*$")


def parse_tickers(raw: str) -> list[str]:
    """Parse a comma/space separated ticker string into clean symbols."""
    if not raw:
        return []
    seen, out = set(), []
    for chunk in str(raw).replace(",", " ").split():
        symbol = chunk.strip().upper()
        if not symbol or len(symbol) > 12:
            continue
        if not _TICKER_RE.match(symbol):
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        out.append(symbol)
        if len(out) >= MAX_WATCHLIST_TICKERS:
            break
    return out


def resolve_outstanding() -> int:
    """Grade every pending forecast whose target session has closed."""
    pending = forecast_ledger.pending_forecasts()
    if not pending:
        return 0
    tickers = sorted({row["ticker"] for row in pending})
    bars = fetch_bars(tickers, period="3mo")
    return forecast_ledger.resolve_forecasts(bars)
