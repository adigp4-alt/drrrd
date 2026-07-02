"""Historical price chart routes."""

from flask import Blueprint, jsonify, render_template, request

from app.config import ALL_TICKERS
from app.data_fetcher import fetch_analysis_data

bp = Blueprint("history", __name__)

# Map UI period labels to yfinance period strings
PERIOD_MAP = {"7d": "7d", "1mo": "1mo", "3mo": "3mo"}


@bp.route("/history")
def history_page():
    return render_template("history.html")


@bp.route("/api/history/<ticker>")
def api_ticker_history(ticker):
    ticker = ticker.upper()
    if ticker not in ALL_TICKERS:
        return jsonify({"error": "Unknown ticker"}), 404

    period = request.args.get("period", "1mo")
    if period not in PERIOD_MAP:
        return jsonify({"error": f"period must be one of {list(PERIOD_MAP)}"}), 400

    data = fetch_analysis_data(ticker, PERIOD_MAP[period])
    if not data:
        return jsonify({"error": "No data available"}), 404

    return jsonify({"ticker": ticker, "period": period, "data": data})
