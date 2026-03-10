import os
import pickle
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier, VotingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.mixture import GaussianMixture
import yfinance as yf
from app.ml_predictor import prepare_ml_data
from app.config import ALL_TICKERS

MODEL_PATH = "data/global_model.pkl"
GMM_PATH = "data/global_gmm.pkl"
SCALER_PATH = "data/global_scaler.pkl"

def fetch_and_train():
    os.makedirs("data", exist_ok=True)
    all_X, all_y = [], []
    
    print("Fetching historical data for training...")
    raw = yf.download(" ".join(ALL_TICKERS), period="5y", group_by="ticker", progress=False)
    
    for sym in ALL_TICKERS:
        df = raw[sym] if len(ALL_TICKERS) > 1 else raw
        df = df.dropna(subset=["Close"]).reset_index()
        records = [{"date": row["Date"], "open": row["Open"], "high": row["High"], "low": row["Low"], "close": row["Close"], "volume": row["Volume"]} for _, row in df.iterrows()]
        X, y, _ = prepare_ml_data(records)
        if X is not None and len(X) > 0:
            all_X.append(X)
            all_y.append(y)
            
    if not all_X:
        print("No data collected for training.")
        return
        
    global_X = np.vstack(all_X)
    global_y = np.concatenate(all_y)
    
    print(f"Training on {len(global_X)} aggregated samples...")
    
    scaler_gmm = StandardScaler()
    X_scaled_gmm = scaler_gmm.fit_transform(global_X)
    gmm = GaussianMixture(n_components=2, random_state=42)
    gmm.fit(X_scaled_gmm)
    
    # Re-align clusters so 0 is Bullish
    cluster_labels = gmm.predict(X_scaled_gmm)
    returns = global_X[:, 5]
    mean_return_0 = np.mean(returns[cluster_labels == 0]) if np.sum(cluster_labels == 0) > 0 else 0
    mean_return_1 = np.mean(returns[cluster_labels == 1]) if np.sum(cluster_labels == 1) > 0 else 0
    
    if mean_return_1 > mean_return_0:
        gmm.means_ = gmm.means_[::-1]
        gmm.covariances_ = gmm.covariances_[::-1]
        gmm.weights_ = gmm.weights_[::-1]
        gmm.precisions_cholesky_ = gmm.precisions_cholesky_[::-1]
    
    rf = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42, n_jobs=-1)
    gbm = HistGradientBoostingClassifier(max_iter=50, max_depth=5, random_state=42)
    mlp_pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('mlp', MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=200, random_state=42))
    ])
    
    ensemble = VotingClassifier(
        estimators=[('rf', rf), ('gbm', gbm), ('mlp', mlp_pipeline)],
        voting='soft',
        n_jobs=-1
    )
    
    ensemble.fit(global_X, global_y)
    
    with open(SCALER_PATH, 'wb') as f:
        pickle.dump(scaler_gmm, f)
    with open(GMM_PATH, 'wb') as f:
        pickle.dump(gmm, f)
    with open(MODEL_PATH, 'wb') as f:
        pickle.dump(ensemble, f)
        
    print("Models saved successfully.")

if __name__ == "__main__":
    fetch_and_train()
