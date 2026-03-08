"""Autonomous strategy engine — signal generation, scoring, and rebalancing."""

import logging
from datetime import datetime

from app.config import ALL_TICKERS, TICKER_META, TIERS
from app.data_fetcher import CACHE, fetch_analysis_data
from app.indicators import sma, ema, rsi, macd, bollinger_bands
from app.models import query_db

logger = logging.getLogger(__name__)

# Target allocation by tier (percentage of total portfolio)
TIER_TARGETS = {
    "T5": 35,   # Broad ETFs — safest, largest allocation
    "T3": 25,   # Israeli equities & cybersecurity
    "T2": 20,   # Defense & energy stock picking
    "T1": 10,   # Post-conflict reconstruction — long horizon
    "T4": 10,   # Tanker/shipping — tactical, smallest
}

# Signal thresholds
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
SIGNIFICANT_VOLUME_MULT = 1.5  # 1.5x average volume = significant

# Autonomous results cache
AUTO_CACHE = {
    "signals": [],
    "rebalance": {},
    "scores": {},
    "recommendations": [],
    "last_run": None,
}


def _generate_signals_for_ticker(ticker, ohlcv):
    """Analyze one ticker and return a list of signal dicts."""
    if not ohlcv or len(ohlcv) < 30:
        return []

    closes = [r["close"] for r in ohlcv]
    volumes = [r["volume"] for r in ohlcv]
    latest = ohlcv[-1]
    price = latest["close"]

    sma_20 = sma(closes, 20)
    sma_50 = sma(closes, 50)
    ema_12 = ema(closes, 12)
    ema_26 = ema(closes, 26)
    rsi_vals = rsi(closes, 14)
    macd_line, signal_line, hist = macd(closes)
    bb_upper, bb_mid, bb_lower = bollinger_bands(closes)

    signals = []
    current_rsi = rsi_vals[-1] if rsi_vals[-1] is not None else 50

    # --- RSI signals ---
    if current_rsi <= RSI_OVERSOLD:
        signals.append({
            "type": "BUY", "indicator": "RSI",
            "reason": f"RSI oversold at {current_rsi:.1f}",
            "strength": min(round((RSI_OVERSOLD - current_rsi) / RSI_OVERSOLD * 100), 100),
        })
    elif current_rsi >= RSI_OVERBOUGHT:
        signals.append({
            "type": "SELL", "indicator": "RSI",
            "reason": f"RSI overbought at {current_rsi:.1f}",
            "strength": min(round((current_rsi - RSI_OVERBOUGHT) / (100 - RSI_OVERBOUGHT) * 100), 100),
        })

    # --- MACD crossover ---
    if len(hist) >= 2 and hist[-1] is not None and hist[-2] is not None:
        if hist[-2] < 0 and hist[-1] > 0:
            signals.append({
                "type": "BUY", "indicator": "MACD",
                "reason": "MACD bullish crossover",
                "strength": 70,
            })
        elif hist[-2] > 0 and hist[-1] < 0:
            signals.append({
                "type": "SELL", "indicator": "MACD",
                "reason": "MACD bearish crossover",
                "strength": 70,
            })

    # --- SMA golden/death cross ---
    if (sma_20[-1] is not None and sma_50[-1] is not None
            and sma_20[-2] is not None and sma_50[-2] is not None):
        if sma_20[-2] < sma_50[-2] and sma_20[-1] > sma_50[-1]:
            signals.append({
                "type": "BUY", "indicator": "SMA",
                "reason": "SMA 20/50 golden cross",
                "strength": 80,
            })
        elif sma_20[-2] > sma_50[-2] and sma_20[-1] < sma_50[-1]:
            signals.append({
                "type": "SELL", "indicator": "SMA",
                "reason": "SMA 20/50 death cross",
                "strength": 80,
            })

    # --- Bollinger Band squeeze/breakout ---
    if bb_upper[-1] is not None and bb_lower[-1] is not None:
        if price <= bb_lower[-1]:
            signals.append({
                "type": "BUY", "indicator": "BB",
                "reason": f"Price at lower Bollinger Band (${bb_lower[-1]:.2f})",
                "strength": 60,
            })
        elif price >= bb_upper[-1]:
            signals.append({
                "type": "SELL", "indicator": "BB",
                "reason": f"Price at upper Bollinger Band (${bb_upper[-1]:.2f})",
                "strength": 60,
            })

    # --- Volume spike ---
    if len(volumes) >= 20:
        avg_vol = sum(volumes[-20:]) / 20
        if avg_vol > 0 and volumes[-1] > avg_vol * SIGNIFICANT_VOLUME_MULT:
            vol_ratio = volumes[-1] / avg_vol
            signals.append({
                "type": "WATCH", "indicator": "VOLUME",
                "reason": f"Volume spike {vol_ratio:.1f}x average",
                "strength": min(round((vol_ratio - 1) * 50), 100),
            })

    # --- Price vs SMA trend ---
    if sma_50[-1] is not None:
        pct_above = (price - sma_50[-1]) / sma_50[-1] * 100
        if pct_above > 10:
            signals.append({
                "type": "SELL", "indicator": "TREND",
                "reason": f"Price {pct_above:.1f}% above SMA50 — extended",
                "strength": min(round(pct_above * 3), 100),
            })
        elif pct_above < -10:
            signals.append({
                "type": "BUY", "indicator": "TREND",
                "reason": f"Price {abs(pct_above):.1f}% below SMA50 — depressed",
                "strength": min(round(abs(pct_above) * 3), 100),
            })

    return signals


def _score_ticker(ticker, signals, current_data):
    """Compute a composite score (0-100) for a ticker. Higher = more bullish."""
    if not signals:
        return 50  # neutral

    buy_score = 0
    sell_score = 0
    for sig in signals:
        if sig["type"] == "BUY":
            buy_score += sig["strength"]
        elif sig["type"] == "SELL":
            sell_score += sig["strength"]

    # Normalize: net score from -100 to +100, then map to 0-100
    total = buy_score + sell_score
    if total == 0:
        return 50
    net = (buy_score - sell_score) / total * 100
    return round(max(0, min(100, 50 + net / 2)))


def _compute_rebalance(holdings, current_prices):
    """Compute portfolio drift and rebalancing recommendations."""
    if not holdings or not current_prices:
        return {"needed": False, "actions": [], "current_allocation": {}, "target_allocation": TIER_TARGETS}

    # Compute current tier allocation
    tier_values = {}
    total_value = 0
    for h in holdings:
        ticker = h["ticker"]
        price_data = current_prices.get(ticker, {})
        current_price = price_data.get("price", h["buy_price"])
        market_value = h["shares"] * current_price
        meta = TICKER_META.get(ticker, {})
        tier = meta.get("tier", "")
        tier_values[tier] = tier_values.get(tier, 0) + market_value
        total_value += market_value

    if total_value == 0:
        return {"needed": False, "actions": [], "current_allocation": {}, "target_allocation": TIER_TARGETS}

    current_alloc = {t: round(v / total_value * 100, 1) for t, v in tier_values.items()}
    actions = []
    drift_threshold = 5  # percent

    for tier, target_pct in TIER_TARGETS.items():
        current_pct = current_alloc.get(tier, 0)
        drift = current_pct - target_pct
        if abs(drift) > drift_threshold:
            tier_name = TIERS.get(tier, {}).get("name", tier)
            if drift > 0:
                dollar_amount = round(abs(drift) / 100 * total_value, 2)
                actions.append({
                    "tier": tier,
                    "tier_name": tier_name,
                    "action": "REDUCE",
                    "drift_pct": round(drift, 1),
                    "amount": dollar_amount,
                    "message": f"Reduce {tier_name} ({tier}) by ~${dollar_amount:,.0f} — overweight by {drift:.1f}%",
                })
            else:
                dollar_amount = round(abs(drift) / 100 * total_value, 2)
                actions.append({
                    "tier": tier,
                    "tier_name": tier_name,
                    "action": "ADD",
                    "drift_pct": round(drift, 1),
                    "amount": dollar_amount,
                    "message": f"Add ~${dollar_amount:,.0f} to {tier_name} ({tier}) — underweight by {abs(drift):.1f}%",
                })

    # Sort by largest drift first
    actions.sort(key=lambda a: abs(a["drift_pct"]), reverse=True)

    return {
        "needed": len(actions) > 0,
        "actions": actions,
        "current_allocation": current_alloc,
        "target_allocation": TIER_TARGETS,
        "total_value": round(total_value, 2),
    }


def _build_recommendations(all_signals, scores, rebalance, current_prices):
    """Build prioritized action recommendations."""
    recs = []

    # Strong buy signals (score > 70)
    for ticker, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        if score >= 70:
            sigs = all_signals.get(ticker, [])
            buy_reasons = [s["reason"] for s in sigs if s["type"] == "BUY"]
            meta = TICKER_META.get(ticker, {})
            price_data = current_prices.get(ticker, {})
            recs.append({
                "priority": "HIGH",
                "action": "BUY",
                "ticker": ticker,
                "name": meta.get("name", ticker),
                "tier": meta.get("tier", ""),
                "score": score,
                "price": price_data.get("price"),
                "reasons": buy_reasons,
                "message": f"Strong buy signal for {ticker} (score {score}/100)",
            })

    # Strong sell signals (score < 30)
    for ticker, score in sorted(scores.items(), key=lambda x: x[1]):
        if score <= 30:
            sigs = all_signals.get(ticker, [])
            sell_reasons = [s["reason"] for s in sigs if s["type"] == "SELL"]
            meta = TICKER_META.get(ticker, {})
            price_data = current_prices.get(ticker, {})
            recs.append({
                "priority": "HIGH",
                "action": "SELL",
                "ticker": ticker,
                "name": meta.get("name", ticker),
                "tier": meta.get("tier", ""),
                "score": score,
                "price": price_data.get("price"),
                "reasons": sell_reasons,
                "message": f"Strong sell signal for {ticker} (score {score}/100)",
            })

    # Rebalancing actions
    for action in rebalance.get("actions", []):
        recs.append({
            "priority": "MEDIUM",
            "action": "REBALANCE",
            "ticker": None,
            "name": action["tier_name"],
            "tier": action["tier"],
            "score": None,
            "price": None,
            "reasons": [action["message"]],
            "message": action["message"],
        })

    # Moderate signals (score 60-70 buy, 30-40 sell)
    for ticker, score in scores.items():
        if 60 <= score < 70:
            meta = TICKER_META.get(ticker, {})
            recs.append({
                "priority": "LOW",
                "action": "WATCH_BUY",
                "ticker": ticker,
                "name": meta.get("name", ticker),
                "tier": meta.get("tier", ""),
                "score": score,
                "price": current_prices.get(ticker, {}).get("price"),
                "reasons": [s["reason"] for s in all_signals.get(ticker, []) if s["type"] == "BUY"],
                "message": f"Watch {ticker} for potential entry (score {score}/100)",
            })
        elif 30 < score <= 40:
            meta = TICKER_META.get(ticker, {})
            recs.append({
                "priority": "LOW",
                "action": "WATCH_SELL",
                "ticker": ticker,
                "name": meta.get("name", ticker),
                "tier": meta.get("tier", ""),
                "score": score,
                "price": current_prices.get(ticker, {}).get("price"),
                "reasons": [s["reason"] for s in all_signals.get(ticker, []) if s["type"] == "SELL"],
                "message": f"Watch {ticker} for potential exit (score {score}/100)",
            })

    return recs


def run_autonomous_scan():
    """Run full autonomous analysis on all tickers. Updates AUTO_CACHE."""
    logger.info("Running autonomous strategy scan...")
    current_prices = CACHE.get("data", {})
    if not current_prices:
        logger.warning("No price data available for autonomous scan")
        return

    all_signals = {}
    scores = {}

    for ticker in ALL_TICKERS:
        ohlcv = fetch_analysis_data(ticker, period="3mo")
        if not ohlcv:
            continue

        signals = _generate_signals_for_ticker(ticker, ohlcv)
        all_signals[ticker] = signals
        scores[ticker] = _score_ticker(ticker, signals, current_prices)

    # Flatten signals with ticker info for the API
    flat_signals = []
    for ticker, sigs in all_signals.items():
        meta = TICKER_META.get(ticker, {})
        price_data = current_prices.get(ticker, {})
        for sig in sigs:
            flat_signals.append({
                **sig,
                "ticker": ticker,
                "name": meta.get("name", ticker),
                "tier": meta.get("tier", ""),
                "price": price_data.get("price"),
            })

    # Sort: strongest signals first
    flat_signals.sort(key=lambda s: s["strength"], reverse=True)

    # Rebalance check
    holdings = query_db("SELECT * FROM holdings")
    rebalance = _compute_rebalance(holdings, current_prices)

    # Build recommendations
    recommendations = _build_recommendations(all_signals, scores, rebalance, current_prices)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    AUTO_CACHE["signals"] = flat_signals
    AUTO_CACHE["scores"] = scores
    AUTO_CACHE["rebalance"] = rebalance
    AUTO_CACHE["recommendations"] = recommendations
    AUTO_CACHE["last_run"] = now

    buy_count = sum(1 for s in flat_signals if s["type"] == "BUY")
    sell_count = sum(1 for s in flat_signals if s["type"] == "SELL")
    logger.info(
        "Autonomous scan complete: %d signals (%d buy, %d sell), %d recommendations",
        len(flat_signals), buy_count, sell_count, len(recommendations),
    )
