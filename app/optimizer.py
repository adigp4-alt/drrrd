import numpy as np
import scipy.optimize as sco

def optimize_portfolio(tickers, returns_df, risk_free_rate=0.0):
    """
    Given a pandas DataFrame, where columns are ticker symbols and rows are daily percentage returns,
    this function calculates the optimal portfolio weights to maximize the Sharpe ratio.
    """
    if returns_df.empty or len(tickers) < 2:
        # Cannot optimize a single asset (100% is the only answer)
        # Or empty data
        return {t: 1.0 / len(tickers) for t in tickers}

    num_assets = len(tickers)
    
    # Calculate annualized mean returns and covariance matrix (assuming 252 trading days)
    mean_returns = returns_df.mean() * 252
    cov_matrix = returns_df.cov() * 252

    def portfolio_annualized_performance(weights, mean_returns, cov_matrix):
        """Returns portfolio return and portfolio volatility"""
        returns = np.sum(mean_returns * weights)
        std = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        return std, returns

    def negative_sharpe_ratio(weights, mean_returns, cov_matrix, risk_free_rate):
        """We want to maximize Sharpe Ratio -> minimize negative SR"""
        p_std, p_ret = portfolio_annualized_performance(weights, mean_returns, cov_matrix)
        # Avoid division by zero
        if p_std == 0:
            return 0
        return -(p_ret - risk_free_rate) / p_std

    # Constraints: weights sum to 1
    constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
    
    # Bounds: No short selling (weights between 0 and 1)
    bounds = tuple((0.0, 1.0) for asset in range(num_assets))
    
    # Initial guess: equal weighting
    init_guess = num_assets * [1. / num_assets,]

    # Optimization
    try:
        opt_results = sco.minimize(
            negative_sharpe_ratio, 
            init_guess, 
            args=(mean_returns, cov_matrix, risk_free_rate), 
            method='SLSQP', 
            bounds=bounds, 
            constraints=constraints
        )
        
        if not opt_results.success:
            print("Optimization failed:", opt_results.message)
            return {t: 1.0 / num_assets for t in tickers}
            
        optimal_weights = opt_results.x
        
        # Clip tiny values to 0 to make it cleaner
        optimal_weights = [round(w, 4) if w > 0.001 else 0.0 for w in optimal_weights]
        
        # Re-normalize just in case clipping messed up sum slightly
        total = sum(optimal_weights)
        if total > 0:
            optimal_weights = [w/total for w in optimal_weights]
        
        return {tickers[i]: optimal_weights[i] for i in range(num_assets)}
        
    except Exception as e:
        print(f"Error during optimization: {e}")
        return {t: 1.0 / num_assets for t in tickers}
