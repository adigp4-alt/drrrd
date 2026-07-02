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

    # Build a master timeline of all unique dates so series with different
    # calendars or gaps stay aligned in the chart instead of shifting by index
    ticker_pts = {}
    all_dates = set()
    for ticker in tickers:
        pts = history.get(ticker)
        if pts and len(pts) >= 2:
            ticker_pts[ticker] = pts
            all_dates.update(p["date"] for p in pts)

    if not ticker_pts:
        return jsonify({"error": "No history for selected tickers"}), 404

    label_dates = sorted(all_dates)
    series_out = []
    for ticker, pts in ticker_pts.items():
        date_map = {p["date"]: p["close"] for p in pts}
        base = next((p["close"] for p in pts if p["close"]), None)
        if not base:
            continue
        normalized = [
            round(date_map[d] / base * 100, 2) if date_map.get(d) is not None else None
            for d in label_dates
        ]
        last_close = next((p["close"] for p in reversed(pts) if p["close"]), base)
        meta = TICKER_META.get(ticker, {})
        series_out.append({
            "ticker": ticker,
            "name": meta.get("name", ticker),
            "color": meta.get("color", "#666"),
            "normalized": normalized,
            "change_pct": round((last_close - base) / base * 100, 2),
        })

    if not series_out:
        return jsonify({"error": "No history for selected tickers"}), 404

    return jsonify({"dates": label_dates, "series": series_out})


@bp.route("/heatmap")
def heatmap_page():
    return render_template("heatmap.html")
