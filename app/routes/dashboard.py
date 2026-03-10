"""Dashboard routes — main page and price API."""

from flask import Blueprint, jsonify, render_template, send_file

from app.config import ALL_TICKERS, TIERS, SNAPSHOT_CSV
from app.data_fetcher import CACHE, fetch_prices

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    return render_template("dashboard.html")


from app.models import query_db
from app.nlp_engine import generate_daily_briefing

@bp.route("/api/prices")
def api_prices():
    # Gather holdings data to feed into the Copilot NLP engine
    try:
        holdings = query_db("SELECT * FROM holdings")
        current_prices = CACHE.get("data", {})
        enriched_holdings = []
        total_val = 0
        
        for h in holdings:
            ticker = h["ticker"]
            price_data = current_prices.get(ticker, {})
            current_price = price_data.get("price", h["buy_price"])
            cost_basis = h["shares"] * h["buy_price"]
            market_value = h["shares"] * current_price
            pnl = market_value - cost_basis
            total_val += market_value
            enriched_holdings.append({
                "ticker": ticker,
                "current_price": current_price,
                "market_value": market_value,
                "pnl": pnl
            })
            
        for h in enriched_holdings:
            h["allocation"] = (h["market_value"] / total_val * 100) if total_val else 0
            
        # Get screener ML cache
        screener_cache = CACHE.get('screener_data', [])
        
        briefing = generate_daily_briefing(enriched_holdings, screener_cache)
        
    except Exception as e:
        briefing = f"Copilot is currently unavailable: {e}"

    return jsonify({
        "tickers": CACHE["data"],
        "last_updated": CACHE["last_updated"],
        "alerts": CACHE["alerts"],
        "copilot_briefing": briefing,
        "tiers": {k: {i: v[i] for i in ("name", "difficulty", "horizon", "min_capital", "color")}
                  for k, v in TIERS.items()},
        "ticker_order": ALL_TICKERS,
    })


@bp.route("/api/history")
def api_history():
    return jsonify(CACHE.get("history", {}))


import threading

@bp.route("/api/refresh", methods=["POST"])
def api_refresh():
    threading.Thread(target=fetch_prices, daemon=True).start()
    return jsonify({"status": "ok", "last_updated": CACHE["last_updated"]})


@bp.route("/api/download/csv")
def download_csv():
    if SNAPSHOT_CSV.exists():
        return send_file(SNAPSHOT_CSV, as_attachment=True, download_name="stock_snapshots.csv")
    return jsonify({"error": "No data yet"}), 404
