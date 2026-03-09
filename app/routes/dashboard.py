"""Dashboard routes — main page and price API."""

from flask import Blueprint, jsonify, render_template, send_file

from app.config import ALL_TICKERS, TIERS, SNAPSHOT_CSV
from app.data_fetcher import CACHE, fetch_prices

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    return render_template("dashboard.html")


@bp.route("/api/prices")
def api_prices():
    return jsonify({
        "tickers": CACHE["data"],
        "last_updated": CACHE["last_updated"],
        "alerts": CACHE["alerts"],
        "tiers": {k: {i: v[i] for i in ("name", "difficulty", "horizon", "min_capital", "color")}
                  for k, v in TIERS.items()},
        "ticker_order": ALL_TICKERS,
    })


@bp.route("/api/history")
def api_history():
    return jsonify(CACHE.get("history", {}))


@bp.route("/api/refresh", methods=["POST"])
def api_refresh():
    fetch_prices()
    return jsonify({"status": "ok", "last_updated": CACHE["last_updated"]})


@bp.route("/api/download/csv")
def download_csv():
    if SNAPSHOT_CSV.exists():
        return send_file(SNAPSHOT_CSV, as_attachment=True, download_name="stock_snapshots.csv")
    return jsonify({"error": "No data yet"}), 404
