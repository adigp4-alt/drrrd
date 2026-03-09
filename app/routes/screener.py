from flask import Blueprint, render_template, jsonify
from app.data_fetcher import CACHE, fetch_history_data
from app.indicators import compute_indicators, calculate_bullish_score

bp = Blueprint("screener", __name__, url_prefix="/screener")

@bp.route("")
def index():
    """Render the main screener page."""
    return render_template("screener.html")

@bp.route("/api/data")
def api_data():
    """Returns JSON payload of all tracked assets with their bullish scores."""
    # Ensure we have recent history data
    history_data = CACHE.get("history_data_30d", {})
    if not history_data:
        # Fallback if scheduler hasn't run it
        history_data = fetch_history_data(30)
        
    prices = CACHE.get("data", {})
    
    results = []
    for ticker, ohlcv in history_data.items():
        if not ohlcv:
            continue
            
        # Compute indicators
        records_with_inds = compute_indicators(ohlcv)
        score, signal = calculate_bullish_score(records_with_inds)
        
        current_price = prices.get(ticker, {}).get("price", "N/A")
        change_pct = prices.get(ticker, {}).get("change_pct", "N/A")
        
        # Add a confidence indicator based on how strong the signal is
        if signal in ["Strong Buy", "Strong Sell"]:
            confidence = "High"
        elif signal in ["Buy", "Sell"]:
            confidence = "Medium"
        else:
            confidence = "Low"
            
        results.append({
            "ticker": ticker,
            "price": current_price,
            "change_pct": change_pct,
            "score": score,
            "signal": signal,
            "confidence": confidence
        })
        
    # Sort by score descending (Strong Buys at the top)
    results = sorted(results, key=lambda x: x["score"], reverse=True)
        
    return jsonify(results)
