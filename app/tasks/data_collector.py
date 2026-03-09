import logging
from datetime import datetime
from app.config import ALL_TICKERS
from app.data_fetcher import fetch_analysis_data
from app.indicators import compute_indicators, calculate_bullish_score
from app.ml_predictor import predict_uptrend_probability
from app.nlp_engine import analyze_ticker_sentiment
from app.prophet_forecaster import generate_prophet_forecast
from app.models import execute_db

logger = logging.getLogger(__name__)

def run_daily_ai_collection():
    """
    Background job that iterates through all tracked tickers, 
    calculates the proprietary AI signals (which are legal to monetize),
    and saves them to the internal SQLite database.
    """
    logger.info("Starting Daily AI Data Collection...")
    today = datetime.utcnow().date().isoformat()
    
    saved_count = 0
    
    for ticker in ALL_TICKERS:
        try:
            # 1. Fetch minimum data
            ohlcv = fetch_analysis_data(ticker, "6mo")
            if not ohlcv or len(ohlcv) < 30:
                logger.warning(f"[{ticker}] Not enough data to collect signals.")
                continue
                
            current_price = ohlcv[-1]['close']
            
            # Simple change percentage (today vs yesterday)
            change_pct = 0.0
            if len(ohlcv) > 1:
                prev_price = ohlcv[-2]['close']
                change_pct = ((current_price - prev_price) / prev_price) * 100
            
            # 2. Technical Confluence
            records_with_inds = compute_indicators(ohlcv)
            bullish_score, technical_signal = calculate_bullish_score(records_with_inds)
            
            # 3. Random Forest Machine Learning
            ai_prob, market_regime, _ = predict_uptrend_probability(ohlcv)
            
            # 4. Prophet Forecasting (Accuracy tracking)
            prophet = generate_prophet_forecast(ohlcv, days_ahead=30)
            prophet_accuracy = prophet.get("accuracy_score", "N/A") if prophet else "N/A"
            
            # 5. Natural Language Processing (News Sentiment)
            nlp_score = analyze_ticker_sentiment(ticker)
            
            # 6. Consensus Engine
            consensus = "Neutral"
            conviction = "Low"
            
            is_tech_bullish = technical_signal in ["Buy", "Strong Buy"]
            is_tech_bearish = technical_signal in ["Sell", "Strong Sell"]
            is_ml_bullish = ai_prob is not None and ai_prob > 60.0
            is_ml_bearish = ai_prob is not None and ai_prob < 40.0
            is_nlp_bullish = nlp_score > 0.2
            is_nlp_bearish = nlp_score < -0.2
            
            if is_tech_bullish and is_ml_bullish and is_nlp_bullish:
                consensus = "Bullish Consensus"
                conviction = "High"
            elif is_tech_bearish and is_ml_bearish and is_nlp_bearish:
                consensus = "Bearish Consensus"
                conviction = "High"
            elif is_tech_bullish and (is_ml_bullish or is_nlp_bullish):
                consensus = "Leaning Bullish"
                conviction = "Medium"
            elif is_tech_bearish and (is_ml_bearish or is_nlp_bearish):
                consensus = "Leaning Bearish"
                conviction = "Medium"
            else:
                consensus = "Mixed Signals"
                conviction = "Low"
                
            # Insert into database using parameter binding
            sql = """
            INSERT INTO ai_signal_logs 
            (date, ticker, price, change_pct, bullish_score, technical_signal, 
             ai_probability, ai_regime, prophet_accuracy, nlp_sentiment_score, consensus, conviction)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            args = (
                today,
                ticker,
                current_price,
                change_pct,
                bullish_score,
                technical_signal,
                ai_prob,
                market_regime,
                prophet_accuracy,
                nlp_score,
                consensus,
                conviction
            )
            
            execute_db(sql, args)
            saved_count += 1
            
        except Exception as e:
            logger.error(f"Error collecting data for {ticker}: {e}")
            
    logger.info(f"Daily AI Data Collection Complete: Logged {saved_count} assets.")
