"""Portfolio CRUD routes."""

from flask import Blueprint, jsonify, render_template, request

from app.config import TICKER_META
from app.data_fetcher import CACHE
from app.models import query_db, execute_db, get_db

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
        if key in data:
            fields.append(f"{key} = ?")
            values.append(data[key])

    if not fields:
        return jsonify({"error": "No valid fields to update"}), 400

    values.append(holding_id)
    with get_db() as db:
        db.execute(f"UPDATE holdings SET {', '.join(fields)} WHERE id = ?", values)
    return jsonify({"status": "updated"})


@bp.route("/api/portfolio/<int:holding_id>", methods=["DELETE"])
def delete_holding(holding_id):
    with get_db() as db:
        db.execute("DELETE FROM holdings WHERE id = ?", (holding_id,))
    return jsonify({"status": "deleted"})


@bp.route("/api/portfolio/optimize", methods=["GET"])
def optimize_portfolio_route():
    import pandas as pd
    from app.optimizer import optimize_portfolio
    from app.data_fetcher import fetch_history_data
    
    holdings = query_db("SELECT DISTINCT ticker FROM holdings")
    tickers = [h["ticker"] for h in holdings]
    
    if len(tickers) < 2:
        return jsonify({"error": "Need at least 2 distinct assets to optimize"}), 400
        
    # Get 1 year of data for better covariance estimates
    history_data = fetch_history_data(365)
    
    # Build dataframe of daily returns
    returns_dict = {}
    for ticker in tickers:
        data = history_data.get(ticker, [])
        if not data:
            continue
        # Convert to pandas series
        df = pd.DataFrame(data)
        if df.empty or 'close' not in df.columns:
            continue
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        # Calculate daily percentage change
        returns_dict[ticker] = df['close'].pct_change().dropna()
        
    if len(returns_dict) < 2:
        return jsonify({"error": "Not enough historical data for these assets"}), 400
        
    # Combine into single dataframe
    returns_df = pd.DataFrame(returns_dict)
    
    # Fill missing values with 0
    returns_df.fillna(0, inplace=True)
    
    # Run optimizer
    optimal_weights = optimize_portfolio(list(returns_dict.keys()), returns_df)
    
    # Convert weights to percentages
    results = [{"ticker": k, "optimal_allocation": round(v * 100, 2)} for k, v in optimal_weights.items()]
    
    # Sort by allocation descending
    results = sorted(results, key=lambda x: x["optimal_allocation"], reverse=True)
    
    return jsonify({"optimized_portfolio": results})
