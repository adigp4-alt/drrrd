"""Correlation matrix and diversification analysis."""

import numpy as np

from app.config import TIERS


def compute_correlation_matrix(history_data, tickers=None):
    """Compute Pearson correlation matrix from historical close prices."""
    if tickers is None:
        tickers = list(history_data.keys())

    # Build aligned price series
    all_dates = set()
    for sym in tickers:
        if sym in history_data:
            for point in history_data[sym]:
                all_dates.add(point["date"])
    all_dates = sorted(all_dates)

    if len(all_dates) < 5:
        return None, tickers

    # Build price matrix
    valid_tickers = []
    price_matrix = []
    for sym in tickers:
        if sym not in history_data:
            continue
        date_price = {p["date"]: p["close"] for p in history_data[sym]}
        prices = [date_price.get(d) for d in all_dates]
        if None not in prices and len(prices) >= 5:
            valid_tickers.append(sym)
            price_matrix.append(prices)

    if len(valid_tickers) < 2:
        return None, valid_tickers

    # Compute returns
    returns = []
    for prices in price_matrix:
        daily_returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] != 0:
                daily_returns.append((prices[i] - prices[i - 1]) / prices[i - 1])
            else:
                daily_returns.append(0)
        returns.append(daily_returns)

    returns_array = np.array(returns)
    corr_matrix = np.corrcoef(returns_array)
    corr_list = [[round(float(v), 3) for v in row] for row in corr_matrix]

    return corr_list, valid_tickers


def find_high_correlations(corr_matrix, tickers, threshold=0.8):
    """Find pairs with correlation above threshold."""
    if corr_matrix is None:
        return []

    pairs = []
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            corr = corr_matrix[i][j]
            if abs(corr) >= threshold:
                pairs.append({
                    "ticker_a": tickers[i],
                    "ticker_b": tickers[j],
                    "correlation": corr,
                    "warning": "highly correlated" if corr > 0 else "inversely correlated",
                })
    return sorted(pairs, key=lambda p: abs(p["correlation"]), reverse=True)


def diversification_score(corr_matrix, tickers):
    """Compute a simple diversification score (0-100, higher is more diversified)."""
    if corr_matrix is None or len(tickers) < 2:
        return 100

    total = 0
    count = 0
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            total += abs(corr_matrix[i][j])
            count += 1

    avg_corr = total / count if count else 0
    return round((1 - avg_corr) * 100, 1)
