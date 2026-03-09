from flask import Blueprint, render_template, jsonify
from app.data_fetcher import CACHE, fetch_history_data
from app.indicators import compute_indicators, calculate_bullish_score
from app.ml_predictor import predict_uptrend_probability
from app.nlp_engine import analyze_ticker_sentiment, get_sentiment_label

bp = Blueprint("screener", __name__, url_prefix="/screener")

@bp.route("")
def index():
    """Render the main screener page."""
    return render_template("screener.html")

@bp.route("/api/data")
def api_data():
    """Returns JSON payload of all tracked assets with their bullish scores."""
    # Ensure we have recent history data
    history_data = CACHE.get("history", {})
    if not history_data:
        import threading
        threading.Thread(target=fetch_history_data, args=(30,), daemon=True).start()
        return jsonify([])
        
    prices = CACHE.get("data", {})

    results = []
    for ticker, ohlcv in history_data.items():
        if not ohlcv:
            continue
            
        # Compute technical indicators
        records_with_inds = compute_indicators(ohlcv)
        score, signal = calculate_bullish_score(records_with_inds)
        
        # 2. AI Probabilistic Forecasting & Regime Detection
        ai_prob, market_regime = predict_uptrend_probability(ohlcv)
        
        if ai_prob is not None:
             ai_forecast_display = f"{ai_prob}% probability of +5D uptrend"
        else:
             ai_forecast_display = "Insufficient data"
             
        if not market_regime:
             market_regime = "Unknown Regime"
        
        # Compute NLP Sentiment
        nlp_score = analyze_ticker_sentiment(ticker)
        nlp_label = get_sentiment_label(nlp_score)
        
        current_price = prices.get(ticker, {}).get("price", "N/A")
        change_pct = prices.get(ticker, {}).get("change_pct", "N/A")
        
        # Add a confidence indicator based on how strong the signal is
        if signal in ["Strong Buy", "Strong Sell"]:
            confidence = "High"
        elif signal in ["Buy", "Sell"]:
            confidence = "Medium"
        else:
            confidence = "Low"
            
        # Optional: Adjust the 'Super Signal' by combining ML and NLP
        if nlp_score > 0.4 and ai_prob is not None and ai_prob > 60:
            super_signal = "SUPER BUY"
        elif nlp_score < -0.4 and ai_prob is not None and ai_prob < 40:
            super_signal = "SUPER SELL"
        else:
            super_signal = signal

        # Calculate Kelly Criterion fraction if it's a Buy signal
        # Kelly = W - ((1 - W) / R)
        # W = Win probability (from our AI forecast)
        # R = Expected Reward/Risk ratio (We'll assume a conservative 1.5 for this strategy)
        kelly_fraction = 0.0
        kelly_display = "N/A"
        
        if ai_prob is not None and ai_prob > 50 and super_signal in ["Buy", "Strong Buy", "SUPER BUY"]:
            w = ai_prob / 100.0
            r = 1.5
            k = w - ((1.0 - w) / r)
            
            # Half-Kelly is often used in practice to reduce volatility
            half_kelly = k / 2.0
            
            # Cap maximum allocation at 25% of bankroll to prevent ruin, floor at 0%
            final_kelly = max(0.0, min(0.25, half_kelly))
            
            if final_kelly > 0:
                kelly_fraction = final_kelly
                kelly_display = f"{final_kelly * 100:.1f}%"

        results.append({
            "ticker": ticker,
            "price": current_price,
            "change_pct": change_pct,
            "score": score,
            "signal": super_signal,
            "confidence": confidence,
            "ai_forecast": ai_forecast_display,
            "ai_prob_num": ai_prob if ai_prob is not None else 50.0,
            "nlp_score": nlp_score,
            "nlp_label": nlp_label,
            "kelly_fraction": kelly_fraction,
            "kelly_display": kelly_display
        })
        
    # Sort by score descending (Strong Buys at the top)
    results = sorted(results, key=lambda x: x["score"], reverse=True)
        
    return jsonify(results)
