"""Authenticated remote-control API endpoints."""

from flask import Blueprint, jsonify, request

from app.auth import require_api_key
from app.config import TICKER_META
from app.data_fetcher import CACHE, fetch_prices
from app.models import execute_db, query_db

bp = Blueprint("remote_api", __name__, url_prefix="/remote")


@bp.route("/refresh", methods=["POST"])
@require_api_key
def remote_refresh():
    fetch_prices()
    try:
        from app.extensions import socketio
        socketio.emit("refresh_complete", {
            "tickers": CACHE["data"],
            "last_updated": CACHE["last_updated"],
            "alerts": CACHE["alerts"],
        })
    except Exception:
        pass
    return jsonify({"status": "ok", "last_updated": CACHE["last_updated"]})


@bp.route("/prices", methods=["GET"])
@require_api_key
def remote_prices():
    return jsonify({
        "tickers": CACHE["data"],
        "last_updated": CACHE["last_updated"],
        "alerts": CACHE["alerts"],
    })


@bp.route("/portfolio", methods=["GET"])
@require_api_key
def remote_portfolio():
    holdings = query_db("SELECT * FROM holdings ORDER BY created_at DESC")
    current = CACHE.get("data", {})
    total_value = total_cost = 0.0
    enriched = []
    for h in holdings:
        price = current.get(h["ticker"], {}).get("price", h["buy_price"])
        cost = h["shares"] * h["buy_price"]
        mv = h["shares"] * price
        pnl = mv - cost
        pnl_pct = (pnl / cost * 100) if cost else 0.0
        total_value += mv
        total_cost += cost
        meta = TICKER_META.get(h["ticker"], {})
        enriched.append({
            **h,
            "current_price": price,
            "cost_basis": round(cost, 2),
            "market_value": round(mv, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "name": meta.get("name", h["ticker"]),
        })
    return jsonify({
        "holdings": enriched,
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_pnl": round(total_value - total_cost, 2),
    })


@bp.route("/alert", methods=["POST"])
@require_api_key
def remote_create_alert():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400
    if not all(data.get(k) for k in ("ticker", "condition", "threshold")):
        return jsonify({"error": "ticker, condition, and threshold required"}), 400
    valid_conditions = ("above", "below", "change_pct_above", "volume_spike")
    if data["condition"] not in valid_conditions:
        return jsonify({"error": f"condition must be one of {valid_conditions}"}), 400
    try:
        threshold = float(data["threshold"])
    except (ValueError, TypeError):
        return jsonify({"error": "threshold must be a number"}), 400
    row_id = execute_db(
        "INSERT INTO alert_rules (ticker, condition, threshold) VALUES (?, ?, ?)",
        (data["ticker"].upper(), data["condition"], threshold),
    )
    return jsonify({"id": row_id, "status": "created"}), 201


@bp.route("/holding", methods=["POST"])
@require_api_key
def remote_add_holding():
    data = request.get_json()
    if not data or not data.get("ticker") or not data.get("shares") or not data.get("buy_price"):
        return jsonify({"error": "ticker, shares, and buy_price required"}), 400
    try:
        shares = float(data["shares"])
        buy_price = float(data["buy_price"])
    except (ValueError, TypeError):
        return jsonify({"error": "shares and buy_price must be numbers"}), 400
    row_id = execute_db(
        "INSERT INTO holdings (ticker, shares, buy_price, buy_date, notes) VALUES (?, ?, ?, ?, ?)",
        (data["ticker"].upper(), shares, buy_price,
         data.get("buy_date", ""), data.get("notes", "")),
    )
    return jsonify({"id": row_id, "status": "created"}), 201
