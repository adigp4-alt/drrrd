"""ForesightTape routes: next-session forecasts and the accuracy scorecard.

The Anthropic API key lives in this process and never reaches the browser — the
client talks to these endpoints, and only the server talks to Anthropic.
"""

import logging

from flask import Blueprint, jsonify, render_template, request

from app import (
    forecast_backtest,
    forecast_catalyst,
    forecast_diagnostics,
    forecast_engine,
    forecast_ledger,
)
from app.config import ALL_TICKERS

logger = logging.getLogger(__name__)

bp = Blueprint("forecast", __name__, url_prefix="/foresight")


def _wants_catalyst() -> bool:
    """Read the ``catalyst`` flag; the overlay is on unless explicitly disabled."""
    raw = (request.args.get("catalyst") or "").strip().lower()
    return raw not in ("0", "false", "off", "no")


@bp.route("")
def index():
    """Render the ForesightTape board."""
    return render_template(
        "foresight.html", catalyst_available=forecast_catalyst.is_configured()
    )


@bp.route("/api/market")
def api_market():
    """Next-session forecast for every tracked ticker."""
    try:
        payload = forecast_engine.build_market_board(use_catalyst=_wants_catalyst())
        return jsonify(payload)
    except Exception as exc:
        logger.exception("Market forecast failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}", "rows": []}), 500


@bp.route("/api/watchlist")
def api_watchlist():
    """Next-session forecast for an ad-hoc ticker list."""
    raw = request.args.get("tickers", "")
    tickers = forecast_engine.parse_tickers(raw)
    if not tickers:
        return jsonify({
            "error": "Supply 1-12 ticker symbols via the 'tickers' parameter.",
            "rows": [],
        }), 400
    try:
        payload = forecast_engine.build_forecasts(
            tickers, use_catalyst=_wants_catalyst()
        )
        return jsonify(payload)
    except Exception as exc:
        logger.exception("Watchlist forecast failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}", "rows": []}), 500


@bp.route("/api/scorecard")
def api_scorecard():
    """Realized accuracy of past forecasts."""
    try:
        days = max(1, min(int(request.args.get("days", 90)), 3650))
    except (TypeError, ValueError):
        days = 90
    ticker = (request.args.get("ticker") or "").strip() or None
    try:
        return jsonify({
            "scorecard": forecast_ledger.scorecard(days=days, ticker=ticker),
            "recent": forecast_ledger.recent_resolved(limit=40, ticker=ticker),
        })
    except Exception as exc:
        logger.exception("Scorecard query failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


@bp.route("/api/diagnostics")
def api_diagnostics():
    """Identify why market data is unavailable.

    Probes DNS, raw HTTPS to Yahoo, both yfinance code paths, and the engine's
    own parser — so a blocked IP, a rate limit and a library version change are
    told apart instead of all surfacing as an empty board.
    """
    try:
        return jsonify(forecast_diagnostics.run_diagnostics())
    except Exception as exc:
        logger.exception("Diagnostics failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


@bp.route("/api/backtest")
def api_backtest():
    """Walk-forward replay of the quant engine over historical sessions.

    Answers "does this thing actually work" without waiting weeks for the live
    ledger to fill. Results are intentionally **not** written to the ledger —
    mixing simulated history into the live scorecard would overstate the real
    track record.
    """
    raw = request.args.get("tickers", "")
    tickers = forecast_engine.parse_tickers(raw) if raw else list(ALL_TICKERS)
    if not tickers:
        return jsonify({"error": "No valid ticker symbols supplied."}), 400

    try:
        sessions = max(20, min(int(request.args.get("sessions", 250)),
                               forecast_backtest.MAX_SESSIONS))
    except (TypeError, ValueError):
        sessions = 250

    period = request.args.get("period", "2y")
    if period not in ("1y", "2y", "5y", "10y", "max"):
        period = "2y"

    try:
        return jsonify(forecast_backtest.run_backtest(
            tickers, period=period, max_sessions=sessions
        ))
    except Exception as exc:
        logger.exception("Backtest failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


@bp.route("/api/resolve", methods=["POST"])
def api_resolve():
    """Force-grade any forecast whose target session has closed."""
    try:
        return jsonify({"resolved": forecast_engine.resolve_outstanding()})
    except Exception as exc:
        logger.exception("Forecast resolution failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500
