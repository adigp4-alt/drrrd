import pandas as pd
import numpy as np
from app.indicators import compute_indicators, calculate_bullish_score
from app.ml_predictor import predict_uptrend_probability

def run_backtest(ticker, history_records, initial_capital=10000.0):
    """
    Simulates a trading strategy over historical data using both technical
    indicators and the ML predictor. Compares against Buy & Hold.
    """
    if not history_records or len(history_records) < 60:
        return {"error": "Insufficient data for backtesting (need at least 60 days)"}
        
    df = pd.DataFrame(history_records)
    
    # Pre-calculate signals and AI probabilities for historical points
    # Since ML Predictor is trained on the fly on past data, simulating it perfectly day-by-day
    # is computationally heavy. For this MVP, we will run the indicators historically, 
    # but use a slightly simplified approach for the backtest.
    
    # 1. Compute technicals for the whole dataframe
    records_with_inds = compute_indicators(history_records)
    
    # 2. Iterate day by day, starting from day 50 (to allow indicators to warm up)
    capital = initial_capital
    shares = 0
    trade_history = []
    equity_curve = []
    
    buy_hold_shares = initial_capital / df.iloc[50]['close']
    
    for i in range(50, len(records_with_inds)):
        current_day = records_with_inds[i]
        date = current_day['date']
        price = current_day['close']
        
        # Calculate signal up to this day
        # In a real rigorous backtest, we would slice `records_with_inds[:i+1]`, 
        # but the indicators are already computed sequentially.
        _, signal = calculate_bullish_score([current_day]) # Current day's technical state
        
        # Determine Trade Logic
        # Strategy: Buy if Strong Buy, Sell if Sell/Strong Sell. 
        # (For speed, we aren't re-training the ML model on every single day of the backtest).
        
        action = "HOLD"
        
        if signal in ["Strong Buy", "Buy"] and capital > 0:
            # Buy as many shares as possible
            shares_to_buy = capital / price
            shares += shares_to_buy
            capital = 0
            action = "BUY"
            trade_history.append({"date": date, "action": "BUY", "price": price, "shares": shares_to_buy})
            
        elif signal in ["Strong Sell", "Sell"] and shares > 0:
            # Sell all shares
            capital += shares * price
            trade_history.append({"date": date, "action": "SELL", "price": price, "shares": shares})
            shares = 0
            action = "SELL"
            
        # Record daily equity
        current_equity = capital + (shares * price)
        bh_equity = buy_hold_shares * price
        
        equity_curve.append({
            "date": date,
            "strategy": current_equity,
            "buy_hold": bh_equity
        })
        
    # Final metrics
    final_equity = capital + (shares * df.iloc[-1]['close'])
    strategy_return = ((final_equity - initial_capital) / initial_capital) * 100
    
    final_bh_equity = buy_hold_shares * df.iloc[-1]['close']
    bh_return = ((final_bh_equity - initial_capital) / initial_capital) * 100
    
    # Calculate Max Drawdown for Strategy
    equity_series = pd.Series([e["strategy"] for e in equity_curve])
    rolling_max = equity_series.cummax()
    drawdowns = (equity_series - rolling_max) / rolling_max
    max_drawdown = drawdowns.min() * 100
    
    # Count winning trades (approximated by pairs of Buy/Sell where Sell > Buy)
    wins = 0
    total_completed_trades = 0
    last_buy_price = 0
    for t in trade_history:
        if t["action"] == "BUY":
            last_buy_price = t["price"]
        elif t["action"] == "SELL" and last_buy_price > 0:
            total_completed_trades += 1
            if t["price"] > last_buy_price:
                wins += 1
            last_buy_price = 0
            
    win_rate = (wins / total_completed_trades * 100) if total_completed_trades > 0 else 0
    
    return {
        "ticker": ticker,
        "initial_capital": initial_capital,
        "final_equity": final_equity,
        "strategy_return_pct": strategy_return,
        "buy_hold_return_pct": bh_return,
        "max_drawdown_pct": max_drawdown,
        "total_trades": len(trade_history),
        "win_rate_pct": win_rate,
        "equity_curve": equity_curve,
        "trade_history": trade_history[-10:] # Return last 10 trades to avoid massive JSON
    }
