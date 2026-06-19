"""Backtesting engine — simulate signal strategies against historical data."""

from app.indicators import rsi, sma, macd

STRATEGIES = {
    "rsi": "RSI (buy <30, sell >70)",
    "sma_cross": "SMA Crossover (20/50)",
    "macd": "MACD Crossover",
}


def run_backtest(ohlcv, strategy="rsi", initial_capital=10000):
    """Simulate a long-only strategy on OHLCV records.

    Buys the full cash position on a buy signal (if flat) and sells the
    full share position on a sell signal (if holding). Returns performance
    metrics plus an equity curve, compared against buy-and-hold.
    """
    closes = [r["close"] for r in ohlcv]
    dates = [r["date"] for r in ohlcv]
    n = len(closes)
    if n < 50:
        return None

    rsi_vals = rsi(closes, 14)
    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50)
    _, _, hist = macd(closes)

    cash = float(initial_capital)
    shares = 0.0
    holding = False
    entry_price = 0.0
    trade_returns = []
    equity_curve = []

    for i in range(n):
        price = closes[i]
        buy = sell = False

        if strategy == "rsi":
            r = rsi_vals[i]
            if r is not None:
                if r <= 30:
                    buy = True
                elif r >= 70:
                    sell = True
        elif strategy == "sma_cross":
            if (i > 0 and None not in (sma20[i], sma50[i], sma20[i - 1], sma50[i - 1])):
                if sma20[i - 1] <= sma50[i - 1] and sma20[i] > sma50[i]:
                    buy = True
                elif sma20[i - 1] >= sma50[i - 1] and sma20[i] < sma50[i]:
                    sell = True
        elif strategy == "macd":
            if i > 0 and hist[i] is not None and hist[i - 1] is not None:
                if hist[i - 1] <= 0 and hist[i] > 0:
                    buy = True
                elif hist[i - 1] >= 0 and hist[i] < 0:
                    sell = True

        if buy and not holding:
            shares = cash / price
            cash = 0.0
            holding = True
            entry_price = price
        elif sell and holding:
            cash = shares * price
            trade_returns.append((price - entry_price) / entry_price * 100)
            shares = 0.0
            holding = False

        equity_curve.append({"date": dates[i], "equity": round(cash + shares * price, 2)})

    final_value = cash + shares * closes[-1]
    total_return = (final_value - initial_capital) / initial_capital * 100
    buy_hold_return = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] else 0

    wins = [t for t in trade_returns if t > 0]
    win_rate = (len(wins) / len(trade_returns) * 100) if trade_returns else 0

    # Max drawdown of the strategy equity curve
    peak = equity_curve[0]["equity"]
    max_dd = 0.0
    for pt in equity_curve:
        if pt["equity"] > peak:
            peak = pt["equity"]
        if peak:
            dd = (peak - pt["equity"]) / peak * 100
            if dd > max_dd:
                max_dd = dd

    return {
        "strategy": strategy,
        "strategy_label": STRATEGIES.get(strategy, strategy),
        "initial_capital": initial_capital,
        "final_value": round(final_value, 2),
        "total_return": round(total_return, 2),
        "buy_hold_return": round(buy_hold_return, 2),
        "outperformance": round(total_return - buy_hold_return, 2),
        "num_trades": len(trade_returns),
        "win_rate": round(win_rate, 1),
        "max_drawdown": round(max_dd, 2),
        "best_trade": round(max(trade_returns), 2) if trade_returns else 0,
        "worst_trade": round(min(trade_returns), 2) if trade_returns else 0,
        "still_holding": holding,
        "equity_curve": equity_curve,
    }
