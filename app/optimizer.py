import numpy as np
import scipy.optimize as sco

def optimize_portfolio(tickers, returns_df, risk_free_rate=0.0, risk_profile="Moderate"):
    """
    Calculates the optimal portfolio weights using SciPy, adjusting the objective function
    based on the user's personalized risk profile.
    """
    if returns_df.empty or len(tickers) < 2:
        return {t: 1.0 / len(tickers) for t in tickers}

    num_assets = len(tickers)
    mean_returns = returns_df.mean() * 252
    cov_matrix = returns_df.cov() * 252

    def portfolio_annualized_performance(weights, mean_returns, cov_matrix):
        returns = np.sum(mean_returns * weights)
        std = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        return std, returns

    # --- Objective Functions based on Risk Profile ---

    def objective_moderate(weights, mean_returns, cov_matrix, risk_free_rate):
        """Moderate: Maximize Sharpe Ratio (balance return/risk)"""
        p_std, p_ret = portfolio_annualized_performance(weights, mean_returns, cov_matrix)
        if p_std == 0: return 0
        return -(p_ret - risk_free_rate) / p_std

    def objective_conservative(weights, mean_returns, cov_matrix, *args):
        """Conservative: Minimize Volatility (ignoring returns)"""
        p_std, _ = portfolio_annualized_performance(weights, mean_returns, cov_matrix)
        return p_std

    def objective_aggressive(weights, mean_returns, cov_matrix, risk_free_rate):
        """Aggressive: Maximize Returns, penalty for extreme volatility"""
        p_std, p_ret = portfolio_annualized_performance(weights, mean_returns, cov_matrix)
        # We want high returns, but still constrain variance slightly
        # Subtract return (to maximize it), add a small penalty for standard deviation
        return -(p_ret) + (0.5 * p_std)

    # Map the profile to the objective
    if risk_profile == "Conservative":
        obj_func = objective_conservative
    elif risk_profile == "Aggressive":
        obj_func = objective_aggressive
    else:
        obj_func = objective_moderate

    # Constraints & Bounds
    constraints = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1})
    bounds = tuple((0.0, 1.0) for asset in range(num_assets))
    init_guess = num_assets * [1. / num_assets,]

    try:
        opt_results = sco.minimize(
            obj_func, 
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
