from flask import Blueprint, render_template, jsonify, request
from app.data_fetcher import CACHE, fetch_history_data
from app.backtester import run_backtest

bp = Blueprint("backtest", __name__, url_prefix="/backtest")

@bp.route("")
def backtest_page():
    """Render the Backtest Dashboard."""
    # We pass the list of available tickers so the user can select one.
    prices = CACHE.get("data", {})
    tickers = list(prices.keys())
    return render_template("backtest.html", tickers=tickers)

@bp.route("/api/run")
def api_run_backtest():
    """Runs a backtest on a specific ticker and returns the metrics."""
    ticker = request.args.get("ticker")
    if not ticker:
        return jsonify({"error": "No ticker provided"}), 400
        
    # We fetch a larger chunk of data (e.g. 1 year) for a meaningful backtest
    # The normal API fetches 30 days, so we force-fetch 365 here if we don't have it.
    
    # Check if we have 365d data in cache, otherwise fetch it.
    history_cache_key = "backtest_history"
    cached_hist = CACHE.get(history_cache_key, {})
    
    if ticker not in cached_hist or len(cached_hist.get(ticker, [])) < 60:
        # We need historical data. 
        # Note: the standard fetch_history_data fetches ALL tracked tickers. 
        # For a single backtest, returning all tickers for 365d takes a very long time.
        # But for this MVP, we will use what we have in the 365d cache from the optimizer
        # or fetch 365 days for the whole app.
        
        # In a real app, you'd write a function to fetch history for JUST one ticker.
        # For now, let's trigger a full 365d fetch if missing.
        history_data = fetch_history_data(365, "1d")
        CACHE[history_cache_key] = history_data
    else:
        history_data = cached_hist

    ticker_history = history_data.get(ticker)
    
    if not ticker_history:
        return jsonify({"error": f"Could not fetch enough history for {ticker}"}), 404
        
    results = run_backtest(ticker, ticker_history)
    return jsonify(results)
