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
    # For speed, we will use the standard cached 30-day history.
    history_data = CACHE.get("history", {})
    
    if not history_data:
        import threading
        threading.Thread(target=fetch_history_data, args=(120,), daemon=True).start()
        return jsonify([])

    try:
        pairs = find_cointegrated_pairs(history_data)
        return jsonify(pairs)
    except Exception as e:
        print(f"Error computing pairs: {e}")
        return jsonify({"error": str(e)}), 500
