import pandas as pd
import numpy as np
import logging
from app.indicators import rsi, macd, bollinger_bands, sma

# Suppress warnings from scikit-learn for clean logs
logging.getLogger("scikit-learn").setLevel(logging.ERROR)

def prepare_ml_data(history_records, prediction_horizon=5):
    """
    Takes a list of OHLCV dictionaries and computes features and targets.
    Target = 1 if the price in `prediction_horizon` days is higher than today, else 0.
    Returns: X (features), y (targets), and latest_features (for prediction today).
    """
    if not history_records or len(history_records) < 50:
        return None, None, None
        
    df = pd.DataFrame(history_records)
    if 'close' not in df.columns:
        return None, None, None
        
    # Recalculate indicators strictly for ML feature engineering
    closes = df['close'].tolist()
    
    df['rsi'] = rsi(closes, 14)
    
    macd_line, signal_line, hist = macd(closes)
    df['macd_hist'] = hist
    
    bb_upper, bb_middle, bb_lower = bollinger_bands(closes, 20)
    df['bb_width'] = [(u - l) / m if m and u and l else None 
                      for u, m, l in zip(bb_upper, bb_middle, bb_lower)]
                      
    sma_20 = sma(closes, 20)
    df['dist_sma_20'] = [(c - s) / s if s else None for c, s in zip(closes, sma_20)]
    
    # Calculate daily returns and rolling volatility
    df['return'] = df['close'].pct_change()
    df['volatility_10d'] = df['return'].rolling(window=10).std()
    
    # Feature engineering: past returns
    df['return_1d_lag'] = df['return'].shift(1)
    df['return_2d_lag'] = df['return'].shift(2)
    
    # Target definition: price goes UP in 'prediction_horizon' days
    # (Future price - Current price) > 0
    df['future_close'] = df['close'].shift(-prediction_horizon)
    df['target'] = (df['future_close'] > df['close']).astype(int)

    # Features to use
    feature_cols = ['rsi', 'macd_hist', 'bb_width', 'dist_sma_20', 
                    'volatility_10d', 'return', 'return_1d_lag', 'return_2d_lag']
                    
    # The last row has features but no target 
    # (since future_close is NaN because we are at the end of the array)
    latest_features = df[feature_cols].iloc[-1:].copy()
    
    # Drop NaNs from historical training data
    df_clean = df.dropna(subset=feature_cols + ['target'])
    
    if len(df_clean) < 20: 
        return None, None, None
        
    X = df_clean[feature_cols].values
    y = df_clean['target'].values
    
    # Handle NaNs in latest_features if they exist (forward fill / 0)
    latest_features = latest_features.fillna(0).values
    
    return X, y, latest_features


def predict_uptrend_probability(history_records):
    """
    Trains a lightweight Random Forest model on the fly using the ticker's history
    and predicts the probability of an uptrend in the next 5 days.
    """
    try:
        # Import inside function to avoid slowing down startup if this isn't used immediately
        from sklearn.ensemble import RandomForestClassifier
        
        X, y, latest_features = prepare_ml_data(history_records, prediction_horizon=5)
        
        if X is None or len(X) < 10 or len(np.unique(y)) < 2:
            # Not enough data or only one class present (e.g. it always went up)
            return None
            
        # Train a small RF model. We keep estimators low for speed since this runs per-ticker
        model = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42, n_jobs=-1)
        model.fit(X, y)
        
        # Predict probability of class 1 (Uptrend)
        proba = model.predict_proba(latest_features)[0]
        
        if len(proba) == 2:
            return round(proba[1] * 100, 1) # Return % chance of going up
        return None
        
    except Exception as e:
        print(f"ML Prediction Error: {e}")
        return None
