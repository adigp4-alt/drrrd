"""Yahoo Finance data fetching logic."""

import csv
import logging
from datetime import datetime

import yfinance as yf
import pandas as pd

from app.config import ALL_TICKERS, TICKER_META, SNAPSHOT_CSV

logger = logging.getLogger(__name__)

# In-memory cache for live data
CACHE = {"data": {}, "last_updated": None, "alerts": [], "history": {}}


def fetch_prices():
    """Fetch current prices for all tickers."""
    logger.info(f"[{datetime.now():%H:%M:%S}] Fetching {len(ALL_TICKERS)} tickers...")
    tickers_str = " ".join(ALL_TICKERS)

    try:
        raw = yf.download(tickers_str, period="5d", group_by="ticker", progress=False)
    except Exception as e:
        logger.error(f"  yfinance error: {e}")
        return

    results = {}
    alerts = []
    now = datetime.now()

    for sym in ALL_TICKERS:
        try:
            df = raw[sym] if len(ALL_TICKERS) > 1 else raw
            if df.empty or df.dropna(how="all").empty:
                continue

            closes = df.dropna(subset=["Close"])
            latest = closes.iloc[-1]
            prev = closes.iloc[-2] if len(closes) > 1 else latest

            price = round(float(latest["Close"]), 2)
            prev_close = round(float(prev["Close"]), 2)
            change = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0

            meta = TICKER_META[sym]
            results[sym] = {
                "ticker": sym,
                "name": meta["name"],
                "tier": meta["tier"],
                "color": meta["color"],
                "price": price,
                "prev_close": prev_close,
                "change_pct": change,
                "open": round(float(latest["Open"]), 2) if pd.notna(latest["Open"]) else price,
                "high": round(float(latest["High"]), 2) if pd.notna(latest["High"]) else price,
                "low": round(float(latest["Low"]), 2) if pd.notna(latest["Low"]) else price,
                "volume": int(latest["Volume"]) if pd.notna(latest["Volume"]) else 0,
            }

            if abs(change) >= 5:
                direction = "surge" if change > 0 else "plunge"
                alerts.append({
                    "ticker": sym, "change": change, "price": price,
                    "direction": direction,
                    "time": now.strftime("%Y-%m-%d %H:%M"),
                    "message": f"{sym} {'surged' if change > 0 else 'plunged'} {change:+.2f}% to ${price}"
                })
        except Exception:
            pass

    CACHE["data"] = results
    CACHE["last_updated"] = now.strftime("%Y-%m-%d %H:%M:%S")
    CACHE["alerts"] = alerts

    _save_snapshot(results)
    logger.info(f"  Got {len(results)}/{len(ALL_TICKERS)} tickers, {len(alerts)} alerts")


def fetch_history_data(days=30):
    """Fetch multi-day history for sparkline charts."""
    logger.info(f"  Fetching {days}-day history...")
    tickers_str = " ".join(ALL_TICKERS)
    try:
        raw = yf.download(tickers_str, period=f"{days}d", group_by="ticker", progress=False)
        history = {}
        for sym in ALL_TICKERS:
            try:
                df = raw[sym] if len(ALL_TICKERS) > 1 else raw
                closes = df["Close"].dropna()
                history[sym] = [
                    {"date": d.strftime("%Y-%m-%d"), "close": round(float(p), 2)}
                    for d, p in closes.items()
                ]
            except Exception:
                pass
        CACHE["history"] = history
        logger.info(f"  History loaded for {len(history)} tickers")
    except Exception as e:
        logger.error(f"  History fetch error: {e}")


def fetch_analysis_data(ticker, period="6mo"):
    """Fetch OHLCV data for technical analysis."""
    try:
        df = yf.download(ticker, period=period, progress=False)
        if df.empty:
            return None
        records = []
        for date, row in df.iterrows():
            records.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]) if pd.notna(row["Volume"]) else 0,
            })
        return records
    except Exception as e:
        logger.error(f"  Analysis data error for {ticker}: {e}")
        return None


def _save_snapshot(results):
    """Append snapshot to CSV."""
    exists = SNAPSHOT_CSV.exists()
    fields = ["timestamp", "ticker", "tier", "price", "change_pct", "volume", "high", "low"]
    with open(SNAPSHOT_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists:
            w.writeheader()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for sym, d in results.items():
            w.writerow({
                "timestamp": ts, "ticker": sym, "tier": d["tier"],
                "price": d["price"], "change_pct": d["change_pct"],
                "volume": d["volume"], "high": d["high"], "low": d["low"],
            })
