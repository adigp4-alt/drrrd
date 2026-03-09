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
    
    # Feature engineering: True Range / ATR
    # TR = max[H-L, abs(H-P_prev), abs(L-P_prev)]
    if 'high' in df.columns and 'low' in df.columns:
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift(1))
        low_close = np.abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['high', 'low', 'close']].apply(
            lambda row: max(row['high'] - row['low'], 
                            abs(row['high'] - df['close'].shift(1).loc[row.name]) if row.name > 0 else 0,
                            abs(row['low'] - df['close'].shift(1).loc[row.name]) if row.name > 0 else 0), axis=1)
        df['atr_14'] = df['tr'].rolling(window=14).mean()
    else:
        # Fallback if no high/low limits 
        df['atr_14'] = df['return'].rolling(window=14).std() * df['close']
        
    # Feature engineering: Price Rate of Change (ROC - 10 day)
    df['roc_10'] = (df['close'] - df['close'].shift(10)) / df['close'].shift(10)
    
    # Target definition: price goes UP in 'prediction_horizon' days
    # (Future price - Current price) > 0
    df['future_close'] = df['close'].shift(-prediction_horizon)
    df['target'] = (df['future_close'] > df['close']).astype(int)

    # Features to use
    feature_cols = ['rsi', 'macd_hist', 'bb_width', 'dist_sma_20', 
                    'volatility_10d', 'return', 'return_1d_lag', 'return_2d_lag',
                    'atr_14', 'roc_10']
                    
    # The last row has features but no target 
    # (since future_close is NaN because we are at the end of the array)
    latest_features = df[feature_cols].iloc[-1:].copy()
    
    # Drop NaNs from historical training data
    df_clean = df.dropna(subset=feature_cols + ['target'])
    
    if len(df_clean) < 30: 
        return None, None, None
        
    X = df_clean[feature_cols].values
    y = df_clean['target'].values
    
    # Handle NaNs in latest_features if they exist (forward fill / 0)
    latest_features = latest_features.fillna(0).values
    
    return X, y, latest_features


def predict_uptrend_probability(history_records):
    """
    Trains a Deep Learning Ensemble model (Random Forest + Gradient Boosting + Neural Network)
    on the fly using the ticker's history and predicts the probability of an uptrend in the next 5 days.
    
    Also uses Gaussian Mixture Models (Unsupervised Clustering) to detect the current Market Regime.
    Returns: (probability_float, regime_string)
    """
    try:
        from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier, VotingClassifier
        from sklearn.neural_network import MLPClassifier
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
        from sklearn.mixture import GaussianMixture
        
        X, y, latest_features = prepare_ml_data(history_records, prediction_horizon=5)
        
        if X is None or len(X) < 10 or len(np.unique(y)) < 2:
            return None, "Not Enough Data"
            
        # 1. Unsupervised Market Regime Detection (Clustering)
        # We look at recent Volatility and Return to cluster the environment into 2 regimes
        df_for_clustering = pd.DataFrame(X) # Assuming feature indices 4 and 5 are vol and return
        # We will just fit the GMM on the whole feature set to find two distinct structural states
        scaler_gmm = StandardScaler()
        X_scaled_gmm = scaler_gmm.fit_transform(X)
        
        gmm = GaussianMixture(n_components=2, random_state=42)
        gmm.fit(X_scaled_gmm)
        
        # Predict the regime for the latest day
        latest_scaled = scaler_gmm.transform(latest_features)
        current_regime_int = gmm.predict(latest_scaled)[0]
        
        # Figure out which regime is which by calculating the mean return of each cluster
        cluster_labels = gmm.predict(X_scaled_gmm)
        returns = X[:, 5] # 'return' is index 5 in feature_cols
        
        mean_return_0 = np.mean(returns[cluster_labels == 0]) if np.sum(cluster_labels == 0) > 0 else 0
        mean_return_1 = np.mean(returns[cluster_labels == 1]) if np.sum(cluster_labels == 1) > 0 else 0
        
        if current_regime_int == 0:
            regime_label = "Bullish Regime" if mean_return_0 > mean_return_1 else "Bearish/Volatile Regime"
        else:
            regime_label = "Bullish Regime" if mean_return_1 > mean_return_0 else "Bearish/Volatile Regime"


        # 2. Deep Learning Ensemble Prediction
        # Model A: High Variance Handler
        rf = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42, n_jobs=-1)
        
        # Model B: Institutional Gradient Boosting (Tree sequentially correcting errors)
        gbm = HistGradientBoostingClassifier(max_iter=50, max_depth=5, random_state=42)
        
        # Model C: Multi-Layer Perceptron (Neural Network)
        # NNs require scaled data, so we wrap it in a pipeline
        mlp_pipeline = Pipeline([
            ('scaler', StandardScaler()),
            ('mlp', MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=200, random_state=42))
        ])
        
        # Ensemble: Soft Voting (Average the probabilities of all models)
        ensemble = VotingClassifier(
            estimators=[('rf', rf), ('gbm', gbm), ('mlp', mlp_pipeline)],
            voting='soft',
            n_jobs=-1
        )
        
        ensemble.fit(X, y)
        
        # Predict probability of class 1 (Uptrend)
        proba = ensemble.predict_proba(latest_features)[0]
        
        prob_val = None
        if len(proba) == 2:
            prob_val = round(proba[1] * 100, 1) # Return % chance of going up
            
        return prob_val, regime_label
        
    except Exception as e:
        print(f"ML/Regime Prediction Error: {e}")
        return None, "Error Computing Regime"
