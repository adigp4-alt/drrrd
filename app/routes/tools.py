"""Comparison and heatmap routes."""

from flask import Blueprint, jsonify, render_template, request

from app.config import ALL_TICKERS, TICKER_META
from app.data_fetcher import CACHE

bp = Blueprint("tools", __name__)


@bp.route("/compare")
def compare_page():
    return render_template("compare.html")


@bp.route("/api/compare")
def api_compare():
    """Return normalized (base=100) close series for selected tickers.

    Uses cached 30-day history so the overlay is instant. Each series is
    rebased to 100 at its first point for fair visual comparison.
    """
    history = CACHE.get("history", {})
    if not history:
        return jsonify({"error": "History not loaded yet"}), 503

    tickers_param = request.args.get("tickers", "")
    tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()]
    tickers = [t for t in tickers if t in ALL_TICKERS][:8]
    if not tickers:
        return jsonify({"error": "Provide 1-8 tickers via ?tickers=A,B,C"}), 400

    # Use the union of dates from the first available ticker as the axis
    series_out = []
    label_dates = None
    for ticker in tickers:
        pts = history.get(ticker)
        if not pts or len(pts) < 2:
            continue
        closes = [p["close"] for p in pts]
        base = closes[0]
        if not base:
            continue
        normalized = [round(c / base * 100, 2) for c in closes]
        if label_dates is None:
            label_dates = [p["date"] for p in pts]
        meta = TICKER_META.get(ticker, {})
        series_out.append({
            "ticker": ticker,
            "name": meta.get("name", ticker),
            "color": meta.get("color", "#666"),
            "normalized": normalized,
            "change_pct": round(normalized[-1] - 100, 2),
        })

    if not series_out:
        return jsonify({"error": "No history for selected tickers"}), 404

    return jsonify({"dates": label_dates, "series": series_out})


@bp.route("/heatmap")
def heatmap_page():
    return render_template("heatmap.html")
