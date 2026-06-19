"""Backtesting routes."""

from flask import Blueprint, jsonify, render_template, request

from app.config import ALL_TICKERS, TICKER_META
from app.data_fetcher import fetch_analysis_data
from app.backtest import run_backtest, STRATEGIES

bp = Blueprint("backtest", __name__)

VALID_PERIODS = {"3mo", "6mo", "1y", "2y"}


@bp.route("/backtest")
def backtest_page():
    return render_template("backtest.html", strategies=STRATEGIES)


@bp.route("/api/backtest/<ticker>")
def api_backtest(ticker):
    ticker = ticker.upper()
    if ticker not in ALL_TICKERS:
        return jsonify({"error": "Unknown ticker"}), 404

    strategy = request.args.get("strategy", "rsi")
    if strategy not in STRATEGIES:
        return jsonify({"error": f"strategy must be one of {list(STRATEGIES)}"}), 400

    period = request.args.get("period", "1y")
    if period not in VALID_PERIODS:
        return jsonify({"error": f"period must be one of {sorted(VALID_PERIODS)}"}), 400

    ohlcv = fetch_analysis_data(ticker, period)
    if not ohlcv:
        return jsonify({"error": "No data available"}), 404

    result = run_backtest(ohlcv, strategy)
    if result is None:
        return jsonify({"error": "Not enough data for this period"}), 422

    result["ticker"] = ticker
    result["name"] = TICKER_META[ticker]["name"]
    result["period"] = period
    return jsonify(result)
