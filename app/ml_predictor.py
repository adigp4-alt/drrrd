import pandas as pd
import numpy as np
import logging
import pickle
import os
from app.indicators import rsi, macd, bollinger_bands, sma

logging.getLogger("scikit-learn").setLevel(logging.ERROR)

MODEL_PATH = "data/global_model.pkl"
GMM_PATH = "data/global_gmm.pkl"
SCALER_PATH = "data/global_scaler.pkl"

def prepare_ml_data(history_records, prediction_horizon=5):
    if not history_records or len(history_records) < 50:
        return None, None, None
        
    df = pd.DataFrame(history_records)
    if 'close' not in df.columns:
        return None, None, None
        
    closes = df['close'].tolist()
    df['rsi'] = rsi(closes, 14)
    macd_line, signal_line, hist = macd(closes)
    df['macd_hist'] = hist
    
    bb_upper, bb_middle, bb_lower = bollinger_bands(closes, 20)
    df['bb_width'] = [(u - l) / m if m and u and l else None 
                      for u, m, l in zip(bb_upper, bb_middle, bb_lower)]
                      
    sma_20 = sma(closes, 20)
    df['dist_sma_20'] = [(c - s) / s if s else None for c, s in zip(closes, sma_20)]
    
    df['return'] = df['close'].pct_change()
    df['volatility_10d'] = df['return'].rolling(window=10).std()
    
    df['return_1d_lag'] = df['return'].shift(1)
    df['return_2d_lag'] = df['return'].shift(2)
    
    if 'high' in df.columns and 'low' in df.columns:
        df['tr'] = df[['high', 'low', 'close']].apply(
            lambda row: max(row['high'] - row['low'], 
                            abs(row['high'] - df['close'].shift(1).loc[row.name]) if row.name > 0 else 0,
                            abs(row['low'] - df['close'].shift(1).loc[row.name]) if row.name > 0 else 0), axis=1)
        df['atr_14'] = df['tr'].rolling(window=14).mean()
    else:
        df['atr_14'] = df['return'].rolling(window=14).std() * df['close']
        
    df['roc_10'] = (df['close'] - df['close'].shift(10)) / df['close'].shift(10)
    
    df['future_close'] = df['close'].shift(-prediction_horizon)
    df['target'] = (df['future_close'] > df['close']).astype(int)

    feature_cols = ['rsi', 'macd_hist', 'bb_width', 'dist_sma_20', 
                    'volatility_10d', 'return', 'return_1d_lag', 'return_2d_lag',
                    'atr_14', 'roc_10']
                    
    latest_features = df[feature_cols].iloc[-1:].copy()
    df_clean = df.dropna(subset=feature_cols + ['target'])
    
    if len(df_clean) < 30: 
        return None, None, None
        
    X = df_clean[feature_cols].values
    y = df_clean['target'].values
    latest_features = latest_features.fillna(0).values
    
    return X, y, latest_features


def predict_uptrend_probability(history_records):
    try:
        X, y, latest_features = prepare_ml_data(history_records, prediction_horizon=5)
        
        if latest_features is None:
            return None, "Not Enough Data", None
            
        if not (os.path.exists(MODEL_PATH) and os.path.exists(GMM_PATH) and os.path.exists(SCALER_PATH)):
            return None, "Models Not Trained"

        with open(SCALER_PATH, 'rb') as f:
            scaler_gmm = pickle.load(f)
        with open(GMM_PATH, 'rb') as f:
            gmm = pickle.load(f)
        with open(MODEL_PATH, 'rb') as f:
            ensemble = pickle.load(f)
            
        latest_scaled = scaler_gmm.transform(latest_features)
        current_regime_int = gmm.predict(latest_scaled)[0]
        
        # We assume 0 is Bullish and 1 is Bearish based on training logic
        regime_label = "Bullish Regime" if current_regime_int == 0 else "Bearish/Volatile Regime"

        proba = ensemble.predict_proba(latest_features)[0]
        prob_val = None
        if len(proba) == 2:
            prob_val = round(proba[1] * 100, 1)
            
        # 3. Explainable AI (XAI): Feature Importance
        # Extract the relative importance of each feature from the Random Forest
        feature_names = ['RSI', 'MACD Histogram', 'Bollinger Width', 'Distance to SMA 20', 
                        '10-Day Volatility', 'Daily Return', '1-Day Lag Return', '2-Day Lag Return',
                        'ATR (True Range)', '10-Day Rate of Change']
        
        # Ensure the RF model is fitted before extracting importances
        # The VotingClassifier fits its estimators internally. We can access the fitted RF:
        fitted_rf = ensemble.named_estimators_['rf']
        importances = fitted_rf.feature_importances_
        
        # Zip features with importances, sort by importance descending, take top 5
        feat_imp_list = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)[:5]
        
        # Convert to dictionary with percentage strings
        rationale = {name: f"{round(imp * 100, 1)}%" for name, imp in feat_imp_list}
            
        return prob_val, regime_label, rationale
        
    except Exception as e:
        print(f"ML/Regime Prediction Error: {e}")
        return None, "Error Computing Regime", None
