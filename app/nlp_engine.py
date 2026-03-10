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

def generate_daily_briefing(holdings_data, screener_cache):
    """
    Synthesizes portfolio performance and Screener ML probabilities into 
    a personalized, conversational Natural Language brief.
    """
    if not holdings_data:
        return "Good morning! You currently have no assets in your portfolio. Head over to the Portfolio tab to add some positions so I can analyze them."
        
    total_val = sum(h['market_value'] for h in holdings_data)
    total_pnl = sum(h['pnl'] for h in holdings_data)
    
    # Sort holdings by allocation size
    top_holdings = sorted(holdings_data, key=lambda x: x['allocation'], reverse=True)[:3]
    
    # Sentence 1: Macro Performance
    direction = "up" if total_pnl >= 0 else "down"
    briefing = f"Good morning! Your portfolio is currently valued at **${total_val:,.2f}**, and you are {direction} **${abs(total_pnl):,.2f}** overall. "
    
    # Sentence 2: Top Holdings Analysis
    briefing += "Looking at your top allocations: "
    holding_briefs = []
    
    for h in top_holdings:
        ticker = h['ticker']
        # Try to find ML data for this holding
        ml_prob = None
        for asset in screener_cache:
            if asset.get('ticker') == ticker:
                ml_prob = asset.get('ai_prob_num')
                break
                
        if ml_prob:
            if ml_prob >= 60:
                outlook = "strong bullish accumulation"
            elif ml_prob <= 40:
                outlook = "bearish distribution"
            else:
                outlook = "neutral consolidation"
                
            holding_briefs.append(f"our Deep Learning ensemble detects **{outlook}** for **{ticker}** ({ml_prob}% uptrend probability)")
        else:
            holding_briefs.append(f"**{ticker}** is currently hovering around **${h['current_price']:.2f}**")
            
    if holding_briefs:
        briefing += ", ".join(holding_briefs)[:-2] + ". "
        
    briefing += "You can use the AI Portfolio Optimizer to automatically balance your risk distribution for these assets."
    
    return briefing
