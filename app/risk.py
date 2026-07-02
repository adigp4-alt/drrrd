"""Risk metrics — volatility, Sharpe, Sortino, drawdown, VaR, beta."""

import math

TRADING_DAYS = 252


def _daily_returns(closes):
    """Simple daily returns from a close-price series."""
    return [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1]
    ]


def compute_risk_metrics(closes, benchmark_closes=None, risk_free=0.0):
    """Compute a suite of risk metrics from a close-price series.

    Metrics are annualized using a 252 trading-day year. Beta is computed
    against benchmark_closes when its return series aligns in length.
    """
    returns = _daily_returns(closes)
    if len(returns) < 2:
        return None

    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance)

    ann_return = mean_r * TRADING_DAYS * 100
    ann_vol = std * math.sqrt(TRADING_DAYS) * 100
    sharpe = ((mean_r - risk_free) / std * math.sqrt(TRADING_DAYS)) if std else 0

    downside = [r for r in returns if r < 0]
    if downside:
        dstd = math.sqrt(sum(r ** 2 for r in downside) / len(downside))
        sortino = (mean_r / dstd * math.sqrt(TRADING_DAYS)) if dstd else 0
    else:
        sortino = 0

    peak = closes[0]
    max_dd = 0.0
    for p in closes:
        if p > peak:
            peak = p
        if peak:
            dd = (peak - p) / peak * 100
            if dd > max_dd:
                max_dd = dd

    sorted_r = sorted(returns)
    var_idx = max(0, int(len(sorted_r) * 0.05) - 1)
    var95 = abs(sorted_r[var_idx] * 100)

    beta = None
    if benchmark_closes:
        bench_returns = _daily_returns(benchmark_closes)
        if len(bench_returns) == len(returns) and len(bench_returns) >= 2:
            mb = sum(bench_returns) / len(bench_returns)
            cov = sum((returns[i] - mean_r) * (bench_returns[i] - mb)
                      for i in range(len(returns))) / len(returns)
            bvar = sum((r - mb) ** 2 for r in bench_returns) / len(bench_returns)
            beta = (cov / bvar) if bvar else None

    return {
        "annualized_return": round(ann_return, 2),
        "annualized_volatility": round(ann_vol, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "max_drawdown": round(max_dd, 2),
        "value_at_risk_95": round(var95, 2),
        "beta": round(beta, 2) if beta is not None else None,
        "sample_days": len(closes),
    }
