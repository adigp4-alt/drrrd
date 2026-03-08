"""Watchlist and notes routes."""

import logging

from flask import Blueprint, jsonify, render_template, request

from app.config import TICKER_META
from app.data_fetcher import CACHE
from app.models import query_db, execute_db, get_db

logger = logging.getLogger(__name__)

ALLOWED_WATCHLIST_FIELDS = {"price_target_high", "price_target_low", "notes", "tags"}

bp = Blueprint("watchlist", __name__)


@bp.route("/watchlist")
def watchlist_page():
    return render_template("watchlist.html")


@bp.route("/api/watchlist")
def api_watchlist():
    items = query_db("SELECT * FROM watchlist ORDER BY created_at DESC")
    current_prices = CACHE.get("data", {})
    enriched = []

    for item in items:
        ticker = item["ticker"]
        price_data = current_prices.get(ticker, {})
        current_price = price_data.get("price")
        meta = TICKER_META.get(ticker, {})

        dist_high = None
        dist_low = None
        near_target = False

        if current_price and item["price_target_high"]:
            dist_high = round((item["price_target_high"] - current_price) / current_price * 100, 2)
            if abs(dist_high) <= 5:
                near_target = True

        if current_price and item["price_target_low"]:
            dist_low = round((item["price_target_low"] - current_price) / current_price * 100, 2)
            if abs(dist_low) <= 5:
                near_target = True

        enriched.append({
            **item,
            "current_price": current_price,
            "change_pct": price_data.get("change_pct"),
            "name": meta.get("name", ticker),
            "tier": meta.get("tier", ""),
            "dist_to_high": dist_high,
            "dist_to_low": dist_low,
            "near_target": near_target,
        })

    return jsonify({"watchlist": enriched})


@bp.route("/api/watchlist", methods=["POST"])
def add_to_watchlist():
    data = request.get_json()
    if not data or not data.get("ticker"):
        return jsonify({"error": "ticker is required"}), 400

    ticker = data["ticker"].upper().strip()

    try:
        row_id = execute_db(
            """INSERT INTO watchlist (ticker, price_target_high, price_target_low, notes, tags)
               VALUES (?, ?, ?, ?, ?)""",
            (ticker, data.get("price_target_high"), data.get("price_target_low"),
             data.get("notes", ""), data.get("tags", ""))
        )
    except Exception:
        logger.exception("Failed to add ticker %s to watchlist", ticker)
        return jsonify({"error": "Ticker already in watchlist"}), 409

    return jsonify({"id": row_id, "status": "created"}), 201


@bp.route("/api/watchlist/<int:item_id>", methods=["PUT"])
def update_watchlist(item_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    fields = []
    values = []
    for key in ("price_target_high", "price_target_low", "notes", "tags"):
        if key in data and key in ALLOWED_WATCHLIST_FIELDS:
            fields.append(f"{key} = ?")
            values.append(data[key])

    if not fields:
        return jsonify({"error": "No valid fields to update"}), 400

    values.append(item_id)
    try:
        with get_db() as db:
            db.execute(f"UPDATE watchlist SET {', '.join(fields)} WHERE id = ?", values)
        return jsonify({"status": "updated"})
    except Exception:
        logger.exception("Failed to update watchlist item %d", item_id)
        return jsonify({"error": "Database error"}), 500


@bp.route("/api/watchlist/<int:item_id>", methods=["DELETE"])
def delete_from_watchlist(item_id):
    try:
        with get_db() as db:
            db.execute("DELETE FROM watchlist WHERE id = ?", (item_id,))
        return jsonify({"status": "deleted"})
    except Exception:
        logger.exception("Failed to delete watchlist item %d", item_id)
        return jsonify({"error": "Database error"}), 500
