#!/usr/bin/env python3
"""
Iran Investment Tracker — Web Application Backend
Flask server that fetches live stock data and serves the dashboard.
"""

import csv
import json
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template, send_file
from apscheduler.schedulers.background import BackgroundScheduler
import yfinance as yf
import pandas as pd

app = Flask(__name__)

# ─── Configuration ───
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
SNAPSHOT_CSV = DATA_DIR / "snapshots.csv"
ALERTS_LOG = DATA_DIR / "alerts.json"

# Cache: stores latest fetch results in memory
CACHE = {"data": {}, "last_updated": None, "alerts": [], "history": {}}

# ─── Ticker Configuration ───
TIERS = {
    "T1": {
        "name": "Post-Conflict Reconstruction",
        "difficulty": "Hardest", "horizon": "2-5 Years", "min_capital": "$5,000+",
        "color": "#C0392B",
        "tickers": {
            "SLB": "SLB (Schlumberger)", "HAL": "Halliburton", "BKR": "Baker Hughes",
            "TTE": "TotalEnergies", "KBR": "KBR Inc", "FLR": "Fluor Corp",
            "ACM": "AECOM", "CAT": "Caterpillar",
        },
    },
    "T2": {
        "name": "Defense & Energy Stock Picking",
        "difficulty": "Hard", "horizon": "3-12 Months", "min_capital": "$2,000+",
        "color": "#E67E22",
        "tickers": {
            "LMT": "Lockheed Martin", "RTX": "RTX Corporation", "NOC": "Northrop Grumman",
            "AVAV": "AeroVironment", "ESLT": "Elbit Systems",
            "XOM": "ExxonMobil", "CVX": "Chevron", "COP": "ConocoPhillips",
            "LNG": "Cheniere Energy", "VG": "Venture Global",
        },
    },
    "T3": {
        "name": "Israeli Equities & Cybersecurity",
        "difficulty": "Medium", "horizon": "3-12 Months", "min_capital": "$1,000+",
        "color": "#2E86C1",
        "tickers": {
            "EIS": "iShares MSCI Israel ETF", "CHKP": "Check Point Software",
            "WIX": "Wix.com", "TEVA": "Teva Pharmaceutical",
            "CRWD": "CrowdStrike", "PANW": "Palo Alto Networks",
            "ZS": "Zscaler", "LDOS": "Leidos", "CIBR": "First Trust Cyber ETF",
        },
    },
    "T4": {
        "name": "Tanker & Shipping (TACTICAL)",
        "difficulty": "Moderate", "horizon": "Days-Weeks", "min_capital": "$500+",
        "color": "#8E44AD",
        "tickers": {
            "BWET": "Breakwave Tanker ETF", "FRO": "Frontline",
            "INSW": "Intl Seaways", "STNG": "Scorpio Tankers", "DHT": "DHT Holdings",
        },
    },
    "T5": {
        "name": "Broad Sector ETFs",
        "difficulty": "Easiest", "horizon": "Ongoing", "min_capital": "Any",
        "color": "#27AE60",
        "tickers": {
            "ITA": "iShares Aerospace & Defense", "XLE": "Energy Select SPDR",
            "XOP": "SPDR Oil & Gas E&P", "SHLD": "Global X Defense ETF",
        },
    },
}

ALL_TICKERS = []
TICKER_META = {}
for tid, tdata in TIERS.items():
    for sym, name in tdata["tickers"].items():
        ALL_TICKERS.append(sym)
        TICKER_META[sym] = {"tier": tid, "name": name, "color": tdata["color"]}

VOLATILE = {"AVAV", "ESLT", "VG", "BWET", "FRO", "INSW", "STNG", "DHT"}

# Approximate baseline prices used when live data is unavailable
DEMO_PRICES = {
    "SLB": 44.0, "HAL": 36.0, "BKR": 38.0, "TTE": 62.0, "KBR": 74.0,
    "FLR": 47.0, "ACM": 103.0, "CAT": 360.0,
    "LMT": 468.0, "RTX": 124.0, "NOC": 480.0, "AVAV": 190.0, "ESLT": 205.0,
    "XOM": 108.0, "CVX": 155.0, "COP": 115.0, "LNG": 210.0, "VG": 12.0,
    "EIS": 54.0, "CHKP": 165.0, "WIX": 175.0, "TEVA": 19.0,
    "CRWD": 380.0, "PANW": 185.0, "ZS": 195.0, "LDOS": 155.0, "CIBR": 30.0,
    "BWET": 14.0, "FRO": 17.0, "INSW": 32.0, "STNG": 55.0, "DHT": 11.0,
    "ITA": 138.0, "XLE": 89.0, "XOP": 140.0, "SHLD": 31.0,
}

# ─── Data Fetching ───

def fetch_prices():
    """Fetch current prices for all tickers."""
    print(f"[{datetime.now():%H:%M:%S}] Fetching {len(ALL_TICKERS)} tickers...")
    tickers_str = " ".join(ALL_TICKERS)

    try:
        raw = yf.download(tickers_str, period="5d", group_by="ticker", progress=False)
    except Exception as e:
        print(f"  ❌ yfinance error: {e}")
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

            # Check alerts
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

    if not results:
        print("  ⚠️  No live data — using demo prices")
        results = _demo_prices()
        CACHE["data"] = results
        CACHE["last_updated"] = now.strftime("%Y-%m-%d %H:%M:%S") + " (demo)"
        CACHE["alerts"] = []
        _save_snapshot(results)
        return

    # Update cache
    CACHE["data"] = results
    CACHE["last_updated"] = now.strftime("%Y-%m-%d %H:%M:%S")
    CACHE["alerts"] = alerts

    # Append to CSV
    _save_snapshot(results)

    print(f"  ✅ Got {len(results)}/{len(ALL_TICKERS)} tickers, {len(alerts)} alerts")


def fetch_history_data(days=30):
    """Fetch multi-day history for sparkline charts."""
    print(f"  Fetching {days}-day history...")
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
        if not history:
            print("  ⚠️  No live history — using demo history")
            history = _demo_history()
        CACHE["history"] = history
        print(f"  ✅ History loaded for {len(history)} tickers")
    except Exception as e:
        print(f"  ❌ History fetch error: {e}")
        print("  ⚠️  Falling back to demo history")
        CACHE["history"] = _demo_history()


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


def _demo_prices():
    """Generate realistic mock prices when live data is unavailable."""
    import random
    now = datetime.now()
    random.seed(int(now.strftime("%Y%m%d%H")) // 4)  # stable within a 4-hr window
    results = {}
    for sym in ALL_TICKERS:
        base = DEMO_PRICES.get(sym, 50.0)
        price = round(base * (1 + random.uniform(-0.04, 0.04)), 2)
        prev_close = round(base * (1 + random.uniform(-0.03, 0.03)), 2)
        change = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
        spread = price * 0.005
        meta = TICKER_META[sym]
        results[sym] = {
            "ticker": sym, "name": meta["name"],
            "tier": meta["tier"], "color": meta["color"],
            "price": price, "prev_close": prev_close, "change_pct": change,
            "open": round(prev_close * 1.001, 2),
            "high": round(price + spread, 2),
            "low": round(price - spread, 2),
            "volume": random.randint(500_000, 15_000_000),
        }
    return results


def _demo_history():
    """Generate synthetic 30-day price history when live data is unavailable."""
    import random
    base_date = datetime.now()
    history = {}
    for sym in ALL_TICKERS:
        base = DEMO_PRICES.get(sym, 50.0)
        p = base * 0.92
        pts = []
        for i in range(30):
            p = round(p * (1 + random.gauss(0, 0.012)), 2)
            d = (base_date - timedelta(days=29 - i)).strftime("%Y-%m-%d")
            pts.append({"date": d, "close": p})
        history[sym] = pts
    return history


# ─── API Routes ───

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/prices")
def api_prices():
    return jsonify({
        "tickers": CACHE["data"],
        "last_updated": CACHE["last_updated"],
        "alerts": CACHE["alerts"],
        "tiers": {k: {i: v[i] for i in ("name", "difficulty", "horizon", "min_capital", "color")}
                  for k, v in TIERS.items()},
        "ticker_order": ALL_TICKERS,
    })


@app.route("/api/history")
def api_history():
    return jsonify(CACHE.get("history", {}))


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    fetch_prices()
    return jsonify({"status": "ok", "last_updated": CACHE["last_updated"]})


@app.route("/api/download/csv")
def download_csv():
    if SNAPSHOT_CSV.exists():
        return send_file(SNAPSHOT_CSV, as_attachment=True, download_name="stock_snapshots.csv")
    return jsonify({"error": "No data yet"}), 404


# ─── Scheduler ───

def start_scheduler():
    """Auto-fetch every 5 minutes during market hours."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_prices, "interval", minutes=5, id="price_fetch")
    scheduler.add_job(lambda: fetch_history_data(30), "interval", hours=6, id="history_fetch")
    scheduler.start()
    print("⏰ Scheduler started: prices every 5 min, history every 6 hrs")


# ─── Main ───

if __name__ == "__main__":
    print("╔═══════════════════════════════════════════════════╗")
    print("║  IRAN INVESTMENT TRACKER — WEB SERVER             ║")
    print("╚═══════════════════════════════════════════════════╝\n")

    # Initial fetch
    fetch_prices()
    fetch_history_data(30)

    # Start background scheduler
    start_scheduler()

    # Run Flask
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
