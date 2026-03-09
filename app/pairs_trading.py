import pandas as pd
import numpy as np
import statsmodels.api as sm
from statsmodels.tsa.stattools import coint

def find_cointegrated_pairs(history_data):
    """
    Takes a dict of ticker: [ohlcv dicts].
    Returns a list of highly co-integrated pairs and their spread details.
    Warning: This is O(N^2), so for large portfolios it should be run asynchronously.
    """
    if not history_data:
        return []
        
    tickers = list(history_data.keys())
    n = len(tickers)
    
    # Extract closing price series
    price_series = {}
    for t in tickers:
        df = pd.DataFrame(history_data[t])
        if not df.empty and len(df) > 50:
            # Drop timezone info and use common dates
            df['date'] = pd.to_datetime(df['date'])
            price_series[t] = df.set_index('date')['close']
            
    if len(price_series) < 2:
        return []
        
    # Combine into a single cleanly aligned dataframe
    pricing_df = pd.DataFrame(price_series).dropna()
    valid_tickers = list(pricing_df.columns)
    
    pairs = []
    
    for i in range(len(valid_tickers)):
        for j in range(i+1, len(valid_tickers)):
            t1 = valid_tickers[i]
            t2 = valid_tickers[j]
            
            S1 = pricing_df[t1]
            S2 = pricing_df[t2]
            
            # The coint function returns the t-statistic and the p-value
            try:
                score, pvalue, _ = coint(S1, S2)
                
                # A p-value less than 0.05 indicates statistical co-integration (they move together)
                if pvalue < 0.05:
                    
                    # Calculate the hedge ratio using Ordinary Least Squares regression
                    S1_with_constant = sm.add_constant(S1)
                    model = sm.OLS(S2, S1_with_constant).fit()
                    hedge_ratio = model.params[t1]
                    
                    # Generate the daily spread series
                    spread = S2 - (hedge_ratio * S1)
                    
                    # Calculate the real-time Z-Score of the spread
                    mean_spread = spread.mean()
                    std_spread = spread.std()
                    z_score = (spread.iloc[-1] - mean_spread) / std_spread if std_spread > 0 else 0
                    
                    # Generate a simplified recent history curve of the Z-Score for the frontend graph
                    # We roll a 30-day window to show how the spread deviates over time
                    rolling_mean = spread.rolling(window=30).mean()
                    rolling_std = spread.rolling(window=30).std()
                    historical_z = ((spread - rolling_mean) / rolling_std).fillna(0)
                    
                    # If Z-Score > 2: Short T2, Long T1 (T2 is overpriced relative to T1)
                    # If Z-Score < -2: Long T2, Short T1 (T2 is underpriced relative to T1)
                    signal = "HOLD"
                    if z_score >= 2.0:
                        signal = f"SHORT {t2} / LONG {t1}"
                    elif z_score <= -2.0:
                        signal = f"LONG {t2} / SHORT {t1}"
                        
                    pairs.append({
                        "pair": f"{t2} / {t1}",
                        "asset_a": t2,
                        "asset_b": t1,
                        "p_value": round(pvalue, 4),
                        "hedge_ratio": round(hedge_ratio, 3),
                        "z_score": round(z_score, 2),
                        "signal": signal,
                        "recent_z_history": list(historical_z.values[-30:]),
                        "recent_dates": list(historical_z.index[-30:].strftime('%Y-%m-%d'))
                    })
            except Exception as e:
                # Some pairs might throw exceptions if they have zero variance
                continue
                
    # Sort pairs by absolute Z-Score descending so the most actionable arb opportunities are on top
    pairs.sort(key=lambda x: abs(x['z_score']), reverse=True)
    return pairs
