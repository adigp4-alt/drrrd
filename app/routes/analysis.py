"""Technical analysis and correlation routes."""

from flask import Blueprint, jsonify, render_template, request

from app.config import ALL_TICKERS, TICKER_META
from app.data_fetcher import fetch_analysis_data, CACHE
from app.indicators import compute_indicators
from app.news import fetch_news
from app.correlation import (
    compute_correlation_matrix, find_high_correlations, diversification_score
)

bp = Blueprint("analysis", __name__)


@bp.route("/analysis")
def analysis_page():
    return render_template("analysis.html", tickers=ALL_TICKERS, ticker_meta=TICKER_META)


from app.prophet_forecaster import generate_prophet_forecast

@bp.route("/api/analysis/<ticker>")
def api_analysis(ticker):
    ticker = ticker.upper()
    period = request.args.get("period", "6mo")
    if ticker not in TICKER_META:
        return jsonify({"error": "Unknown ticker"}), 404

    ohlcv = fetch_analysis_data(ticker, period)
    if not ohlcv:
        return jsonify({"error": "No data available"}), 404

    data_with_indicators = compute_indicators(ohlcv)
    meta = TICKER_META[ticker]
    
    # Generate the 30-day AI trajectory
    prophet_forecast = generate_prophet_forecast(ohlcv, days_ahead=30)

    return jsonify({
        "ticker": ticker,
        "name": meta["name"],
        "tier": meta["tier"],
        "period": period,
        "data": data_with_indicators,
        "prophet_forecast": prophet_forecast
    })


@bp.route("/api/news/<ticker>")
def api_news(ticker):
    ticker = ticker.upper()
    news = fetch_news(ticker)
    return jsonify({"ticker": ticker, "news": news})


@bp.route("/correlation")
def correlation_page():
    return render_template("correlation.html")


@bp.route("/api/correlation")
def api_correlation():
    history = CACHE.get("history", {})
    if not history:
        return jsonify({"error": "No history data available"}), 404

    corr_matrix, tickers = compute_correlation_matrix(history)
    if corr_matrix is None:
        return jsonify({"error": "Not enough data for correlation"}), 404

    high_corr = find_high_correlations(corr_matrix, tickers)
    div_score = diversification_score(corr_matrix, tickers)

    return jsonify({
        "matrix": corr_matrix,
        "tickers": tickers,
        "high_correlations": high_corr,
        "diversification_score": div_score,
    })
