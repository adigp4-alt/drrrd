"""ForesightTape routes: next-session forecasts and the accuracy scorecard.

The Anthropic API key lives in this process and never reaches the browser — the
client talks to these endpoints, and only the server talks to Anthropic.
"""

import logging

from flask import Blueprint, jsonify, render_template, request

from app import forecast_catalyst, forecast_engine, forecast_ledger

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


@bp.route("/api/resolve", methods=["POST"])
def api_resolve():
    """Force-grade any forecast whose target session has closed."""
    try:
        return jsonify({"resolved": forecast_engine.resolve_outstanding()})
    except Exception as exc:
        logger.exception("Forecast resolution failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500
