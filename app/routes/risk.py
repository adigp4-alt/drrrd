"""Risk metrics routes."""

import logging

from flask import Blueprint, jsonify, render_template

from app.config import ALL_TICKERS, TICKER_META
from app.data_fetcher import CACHE, fetch_analysis_data
from app.risk import compute_risk_metrics

logger = logging.getLogger(__name__)

bp = Blueprint("risk", __name__)

# Benchmark for beta (SPY = S&P 500 ETF), fetched lazily and cached
_BENCHMARK = {"closes": None}


def _get_benchmark_closes():
    """Fetch SPY closes once for beta calculation; cache in-process."""
    if _BENCHMARK["closes"] is None:
        try:
            data = fetch_analysis_data("SPY", "3mo")
            if data:
                _BENCHMARK["closes"] = [r["close"] for r in data]
        except Exception:
            logger.warning("Could not fetch SPY benchmark for beta")
    return _BENCHMARK["closes"]


@bp.route("/risk")
def risk_page():
    return render_template("risk.html")


@bp.route("/api/risk")
def api_risk_all():
    """Risk metrics for every ticker, from cached 30-day history (fast)."""
    history = CACHE.get("history", {})
    if not history:
        return jsonify({"error": "History not loaded yet"}), 503

    results = []
    for ticker in ALL_TICKERS:
        series = history.get(ticker)
        if not series or len(series) < 5:
            continue
        closes = [pt["close"] for pt in series]
        metrics = compute_risk_metrics(closes)
        if metrics is None:
            continue
        meta = TICKER_META.get(ticker, {})
        results.append({
            "ticker": ticker,
            "name": meta.get("name", ticker),
            "tier": meta.get("tier", ""),
            **metrics,
        })

    return jsonify({"metrics": results, "window": "30-day"})


@bp.route("/api/risk/<ticker>")
def api_risk_one(ticker):
    """Detailed risk for one ticker over a longer window, with beta vs SPY."""
    ticker = ticker.upper()
    if ticker not in ALL_TICKERS:
        return jsonify({"error": "Unknown ticker"}), 404

    data = fetch_analysis_data(ticker, "3mo")
    if not data:
        return jsonify({"error": "No data available"}), 404

    closes = [r["close"] for r in data]
    bench = _get_benchmark_closes()
    # Align benchmark length to the ticker series for beta
    bench_aligned = None
    if bench and len(bench) >= len(closes):
        bench_aligned = bench[-len(closes):]

    metrics = compute_risk_metrics(closes, bench_aligned)
    if metrics is None:
        return jsonify({"error": "Not enough data"}), 422

    meta = TICKER_META[ticker]
    return jsonify({
        "ticker": ticker,
        "name": meta["name"],
        "tier": meta["tier"],
        "window": "3-month",
        **metrics,
    })
