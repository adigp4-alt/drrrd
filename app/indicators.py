"""Technical analysis indicator calculations."""


def sma(closes, window):
    """Simple Moving Average."""
    result = []
    for i in range(len(closes)):
        if i < window - 1:
            result.append(None)
        else:
            avg = sum(closes[i - window + 1:i + 1]) / window
            result.append(round(avg, 2))
    return result


def ema(closes, window):
    """Exponential Moving Average."""
    if len(closes) < window:
        return [None] * len(closes)
    multiplier = 2 / (window + 1)
    result = [None] * (window - 1)
    # Seed with SMA
    seed = sum(closes[:window]) / window
    result.append(round(seed, 2))
    for i in range(window, len(closes)):
        val = (closes[i] - result[-1]) * multiplier + result[-1]
        result.append(round(val, 2))
    return result


def rsi(closes, period=14):
    """Relative Strength Index."""
    if len(closes) < period + 1:
        return [None] * len(closes)
    result = [None] * period
    gains = []
    losses = []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        result.append(100.0)
    else:
        rs = avg_gain / avg_loss
        result.append(round(100 - 100 / (1 + rs), 2))
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gain = max(diff, 0)
        loss = max(-diff, 0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(round(100 - 100 / (1 + rs), 2))
    return result


def macd(closes, fast=12, slow=26, signal=9):
    """MACD line, signal line, and histogram."""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = []
    for f, s in zip(ema_fast, ema_slow):
        if f is None or s is None:
            macd_line.append(None)
        else:
            macd_line.append(round(f - s, 4))
    # Signal line: EMA of MACD values (skip Nones)
    valid_macd = [v for v in macd_line if v is not None]
    signal_line_values = ema(valid_macd, signal) if len(valid_macd) >= signal else []
    signal_line = [None] * (len(macd_line) - len(signal_line_values))
    signal_line.extend(signal_line_values)
    histogram = []
    for m, s in zip(macd_line, signal_line):
        if m is None or s is None:
            histogram.append(None)
        else:
            histogram.append(round(m - s, 4))
    return macd_line, signal_line, histogram


def bollinger_bands(closes, window=20, num_std=2):
    """Bollinger Bands: upper, middle (SMA), lower."""
    middle = sma(closes, window)
    upper = []
    lower = []
    for i in range(len(closes)):
        if middle[i] is None:
            upper.append(None)
            lower.append(None)
        else:
            window_data = closes[i - window + 1:i + 1]
            mean = middle[i]
            variance = sum((x - mean) ** 2 for x in window_data) / window
            std = variance ** 0.5
            upper.append(round(mean + num_std * std, 2))
            lower.append(round(mean - num_std * std, 2))
    return upper, middle, lower


def compute_indicators(ohlcv_records):
    """Compute all indicators from OHLCV data records."""
    closes = [r["close"] for r in ohlcv_records]
    dates = [r["date"] for r in ohlcv_records]

    sma_20 = sma(closes, 20)
    sma_50 = sma(closes, 50)
    ema_12 = ema(closes, 12)
    ema_26 = ema(closes, 26)
    rsi_14 = rsi(closes, 14)
    macd_line, signal_line, hist = macd(closes)
    bb_upper, bb_middle, bb_lower = bollinger_bands(closes)

    result = []
    for i in range(len(ohlcv_records)):
        result.append({
            **ohlcv_records[i],
            "sma_20": sma_20[i],
            "sma_50": sma_50[i],
            "ema_12": ema_12[i],
            "ema_26": ema_26[i],
            "rsi": rsi_14[i],
            "macd": macd_line[i],
            "macd_signal": signal_line[i],
            "macd_hist": hist[i],
            "bb_upper": bb_upper[i],
            "bb_middle": bb_middle[i],
            "bb_lower": bb_lower[i],
        })
    return result
