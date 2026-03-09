"""Yahoo Finance data fetching logic."""

import csv
import logging
from datetime import datetime

import yfinance as yf
import pandas as pd

from app.config import ALL_TICKERS, TICKER_META, SNAPSHOT_CSV
import requests

logger = logging.getLogger(__name__)

# Stealth Session for Yahoo Finance to bypass Cloud/Shared IP blocks constraints
# by impersonating a generic Windows 11 Chrome browser instead of the python requests library
yf_session = requests.Session()
yf_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Connection": "keep-alive"
})

# In-memory cache for live data
CACHE = {"data": {}, "last_updated": None, "alerts": [], "history": {}}


def fetch_prices():
    """Fetch current prices for all tickers."""
    logger.info(f"[{datetime.now():%H:%M:%S}] Fetching {len(ALL_TICKERS)} tickers...")
    tickers_str = " ".join(ALL_TICKERS)

    try:
        raw = yf.download(tickers_str, period="5d", group_by="ticker", progress=False, session=yf_session)
    except Exception as e:
        logger.error(f"  yfinance error: {e}")
        return {}

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
    return results


def fetch_history_data(days=30):
    """Fetch multi-day history for sparkline charts."""
    logger.info(f"  Fetching {days}-day history...")
    tickers_str = " ".join(ALL_TICKERS)
    try:
        raw = yf.download(tickers_str, period=f"{days}d", group_by="ticker", progress=False, session=yf_session)
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
        return history
    except Exception as e:
        logger.error(f"  History fetch error: {e}")
        return {}


def fetch_analysis_data(ticker, period="6mo"):
    """Fetch OHLCV data for technical analysis."""
    try:
        df = yf.download(ticker, period=period, progress=False, session=yf_session)
        if df.empty:
            return None
            
        records = []
        for date, row in df.iterrows():
            try:
                # When accessing a MultiIndex DataFrame by row, it returns a Series where the index is 
                # a tuple like ('Close', 'LMT'). We can extract the scalar using .iloc or directly by the top level string if it was automatically converted to 1D.
                open_val = row["Open"].iloc[0] if hasattr(row["Open"], 'iloc') and hasattr(row["Open"], '__len__') else row["Open"]
                high_val = row["High"].iloc[0] if hasattr(row["High"], 'iloc') and hasattr(row["High"], '__len__') else row["High"]
                low_val = row["Low"].iloc[0] if hasattr(row["Low"], 'iloc') and hasattr(row["Low"], '__len__') else row["Low"]
                close_val = row["Close"].iloc[0] if hasattr(row["Close"], 'iloc') and hasattr(row["Close"], '__len__') else row["Close"]
                vol_val = row["Volume"].iloc[0] if hasattr(row["Volume"], 'iloc') and hasattr(row["Volume"], '__len__') else row["Volume"]
                
                records.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "open": round(float(open_val), 2),
                    "high": round(float(high_val), 2),
                    "low": round(float(low_val), 2),
                    "close": round(float(close_val), 2),
                    "volume": int(vol_val) if pd.notna(vol_val) else 0,
                })
            except Exception as inner_e:
                logger.warning(f"Skipping row on {date}: {inner_e}")
                continue
                
        return records if records else None
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
