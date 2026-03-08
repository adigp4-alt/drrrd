"""Portfolio CRUD routes."""

import logging

from flask import Blueprint, jsonify, render_template, request

from app.config import TICKER_META
from app.data_fetcher import CACHE
from app.models import query_db, execute_db, get_db

logger = logging.getLogger(__name__)

ALLOWED_HOLDING_FIELDS = {"shares", "buy_price", "buy_date", "notes"}

bp = Blueprint("portfolio", __name__)


@bp.route("/portfolio")
def portfolio_page():
    return render_template("portfolio.html")


@bp.route("/api/portfolio")
def api_portfolio():
    holdings = query_db("SELECT * FROM holdings ORDER BY created_at DESC")
    current_prices = CACHE.get("data", {})
    total_value = 0
    enriched = []

    for h in holdings:
        ticker = h["ticker"]
        price_data = current_prices.get(ticker, {})
        current_price = price_data.get("price", h["buy_price"])
        cost_basis = h["shares"] * h["buy_price"]
        market_value = h["shares"] * current_price
        pnl = market_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100) if cost_basis else 0
        total_value += market_value

        meta = TICKER_META.get(ticker, {})
        enriched.append({
            **h,
            "current_price": current_price,
            "cost_basis": round(cost_basis, 2),
            "market_value": round(market_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "name": meta.get("name", ticker),
            "tier": meta.get("tier", ""),
            "color": meta.get("color", "#666"),
        })

    # Add allocation percentages
    for item in enriched:
        item["allocation"] = round(item["market_value"] / total_value * 100, 2) if total_value else 0

    return jsonify({
        "holdings": enriched,
        "total_value": round(total_value, 2),
        "total_cost": round(sum(h["cost_basis"] for h in enriched), 2),
        "total_pnl": round(sum(h["pnl"] for h in enriched), 2),
    })


@bp.route("/api/portfolio", methods=["POST"])
def add_holding():
    data = request.get_json()
    if not data or not data.get("ticker") or not data.get("shares") or not data.get("buy_price"):
        return jsonify({"error": "ticker, shares, and buy_price are required"}), 400

    ticker = data["ticker"].upper().strip()
    try:
        shares = float(data["shares"])
        buy_price = float(data["buy_price"])
    except (ValueError, TypeError):
        return jsonify({"error": "shares and buy_price must be numbers"}), 400

    row_id = execute_db(
        "INSERT INTO holdings (ticker, shares, buy_price, buy_date, notes) VALUES (?, ?, ?, ?, ?)",
        (ticker, shares, buy_price, data.get("buy_date", ""), data.get("notes", ""))
    )
    return jsonify({"id": row_id, "status": "created"}), 201


@bp.route("/api/portfolio/<int:holding_id>", methods=["PUT"])
def update_holding(holding_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    fields = []
    values = []
    for key in ("shares", "buy_price", "buy_date", "notes"):
        if key in data and key in ALLOWED_HOLDING_FIELDS:
            fields.append(f"{key} = ?")
            values.append(data[key])

    if not fields:
        return jsonify({"error": "No valid fields to update"}), 400

    values.append(holding_id)
    try:
        with get_db() as db:
            db.execute(f"UPDATE holdings SET {', '.join(fields)} WHERE id = ?", values)
        return jsonify({"status": "updated"})
    except Exception:
        logger.exception("Failed to update holding %d", holding_id)
        return jsonify({"error": "Database error"}), 500


@bp.route("/api/portfolio/<int:holding_id>", methods=["DELETE"])
def delete_holding(holding_id):
    try:
        with get_db() as db:
            db.execute("DELETE FROM holdings WHERE id = ?", (holding_id,))
        return jsonify({"status": "deleted"})
    except Exception:
        logger.exception("Failed to delete holding %d", holding_id)
        return jsonify({"error": "Database error"}), 500
