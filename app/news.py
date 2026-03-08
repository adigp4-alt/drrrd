"""News fetching and sentiment scoring."""

import yfinance as yf

BULLISH_WORDS = {
    "surge", "soar", "rally", "gain", "rise", "jump", "bull", "boost",
    "record", "high", "upgrade", "beat", "outperform", "growth", "profit",
    "buy", "strong", "positive", "recover", "breakout", "upside",
}

BEARISH_WORDS = {
    "drop", "fall", "plunge", "crash", "decline", "loss", "bear", "cut",
    "low", "downgrade", "miss", "underperform", "risk", "sell", "weak",
    "negative", "warning", "fear", "collapse", "downside", "layoff",
}


def score_sentiment(text):
    """Score text sentiment: 1 (bullish), -1 (bearish), 0 (neutral)."""
    words = set(text.lower().split())
    bull_count = len(words & BULLISH_WORDS)
    bear_count = len(words & BEARISH_WORDS)
    if bull_count > bear_count:
        return 1
    elif bear_count > bull_count:
        return -1
    return 0


def sentiment_label(score):
    """Convert score to label."""
    if score > 0:
        return "bullish"
    elif score < 0:
        return "bearish"
    return "neutral"


def fetch_news(ticker):
    """Fetch recent news for a ticker using yfinance."""
    try:
        stock = yf.Ticker(ticker)
        news_items = stock.news or []
        results = []
        for item in news_items[:10]:
            title = item.get("title", "")
            score = score_sentiment(title)
            results.append({
                "title": title,
                "publisher": item.get("publisher", ""),
                "link": item.get("link", ""),
                "published": item.get("providerPublishTime", ""),
                "sentiment": sentiment_label(score),
                "sentiment_score": score,
            })
        return results
    except Exception:
        return []
