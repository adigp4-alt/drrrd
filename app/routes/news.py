"""News feed routes — aggregated headlines with sentiment."""

import logging

from flask import Blueprint, jsonify, render_template, request

from app.config import ALL_TICKERS
from app.news import fetch_news

logger = logging.getLogger(__name__)

bp = Blueprint("news", __name__)


@bp.route("/news")
def news_page():
    return render_template("news.html")


@bp.route("/api/news")
def api_news_feed():
    """Fetch aggregated news for selected tickers (or first few by default)."""
    tickers_param = request.args.get("tickers", "")
    if tickers_param:
        tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()]
        tickers = [t for t in tickers if t in ALL_TICKERS]
    else:
        tickers = ALL_TICKERS[:5]

    all_news = []
    for ticker in tickers[:10]:  # cap to keep response snappy
        try:
            for item in fetch_news(ticker):
                item["ticker"] = ticker
                all_news.append(item)
        except Exception:
            logger.warning("Failed to fetch news for %s", ticker)

    # Most recent first
    all_news.sort(key=lambda x: x.get("published", 0) or 0, reverse=True)

    return jsonify({"news": all_news[:50], "tickers_queried": tickers})
