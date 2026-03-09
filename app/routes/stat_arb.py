from flask import Blueprint, render_template, jsonify
from app.data_fetcher import CACHE, fetch_history_data
from app.pairs_trading import find_cointegrated_pairs

bp = Blueprint("stat_arb", __name__, url_prefix="/stat-arb")

@bp.route("")
def stat_arb_page():
    """Render the Statistical Arbitrage Dashboard."""
    return render_template("statarb.html")

@bp.route("/api/pairs")
def api_pairs_data():
    """Scans historical data for co-integrated pairs and returns actionable spreads."""
    
    # We need historical data to run the Dickey-Fuller tests structure
    # For speed, we will use the cached 30-day or 365-day history.
    history_cache_key = "backtest_history"
    cached_hist = CACHE.get(history_cache_key, {})
    
    if not cached_hist:
        # If the backtester never ran, fetch minimum required history
        # We need at least 60 days to find meaningful co-integration.
        history_data = fetch_history_data(120, "1d")
        CACHE[history_cache_key] = history_data
    else:
        history_data = cached_hist

    try:
        pairs = find_cointegrated_pairs(history_data)
        return jsonify(pairs)
    except Exception as e:
        print(f"Error computing pairs: {e}")
        return jsonify({"error": str(e)}), 500
