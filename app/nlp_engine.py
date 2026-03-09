import yfinance as yf
import logging
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Initialize VADER globally so it doesn't reload the lexicon every function call
analyzer = SentimentIntensityAnalyzer()
logger = logging.getLogger(__name__)

def analyze_ticker_sentiment(ticker):
    """
    Fetches the latest news headlines for a ticker using yfinance,
    runs VADER NLP analysis on each headline, and returns an aggregated score.
    
    Returns: A float between -1 (Extremely Bearish) and 1 (Extremely Bullish)
    """
    try:
        # yf.Ticker(ticker).news fetches a list of ~8 recent news dictionaries
        ticker_obj = yf.Ticker(ticker)
        news_items = ticker_obj.news
        
        if not news_items:
            return 0.0
            
        total_compound_score = 0.0
        analyzed_count = 0
        
        for item in news_items:
            # We analyze both the headline and the summary snippet if it exists
            text_to_analyze = item.get("title", "") + ". " + item.get("summary", "")
            
            if text_to_analyze.strip() == ".":
                continue
                
            scores = analyzer.polarity_scores(text_to_analyze)
            
            # 'compound' score is a normalized, weighted composite score between -1 and +1
            total_compound_score += scores['compound']
            analyzed_count += 1
            
        if analyzed_count == 0:
            return 0.0
            
        average_sentiment = total_compound_score / analyzed_count
        
        # Round to 2 decimal places for cleaner output
        return round(average_sentiment, 2)
        
    except Exception as e:
        print(f"NLP Engine Error for {ticker}: {e}")
        return 0.0

def get_sentiment_label(score):
    """Converts a raw float score to a human readable label."""
    if score >= 0.25:
        return "Bullish"
    elif score <= -0.25:
        return "Bearish"
    else:
        return "Neutral"
