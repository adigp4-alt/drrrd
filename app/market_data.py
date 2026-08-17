"""Market data access: version-tolerant parsing and a fallback provider.

Two independent problems live here, both of which produced a blank page in
production:

1. **yfinance response shapes change between releases.** Since 1.x,
   ``multi_level_index`` defaults to True, so even a single-ticker download
   returns MultiIndex columns — breaking the long-standing "flat frame when
   there's one ticker" assumption throughout this app.
2. **Yahoo Finance throttles and blocks datacenter IP ranges.** Cloud hosts
   (Render, Heroku, and friends) are refused often enough that a market-data
   app depending on Yahoo alone is fragile by construction. No amount of
   parsing care fixes an HTTP 429.

So this module provides a *fallback provider*: Stooq, which serves daily OHLCV
as plain CSV, needs no API key, and is generally reachable from cloud hosts.
When Yahoo returns nothing for a ticker, Stooq is tried automatically and the
board reports which source actually served the data.


yfinance's column layout has changed repeatedly across releases and also varies
with ``group_by``. Since 1.x, ``multi_level_index`` defaults to True, so even a
*single*-ticker download returns MultiIndex columns — which silently broke the
long-standing "flat frame when there's only one ticker" assumption throughout
this app and produced empty pages with no error anywhere.

Keeping the shape handling in one place means a future yfinance bump is a single
fix (and a failing unit test) rather than a hunt across every module that reads
market data.
"""

from __future__ import annotations

import csv
import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

logger = logging.getLogger(__name__)

OHLC = ("Open", "High", "Low", "Close")

# "auto" tries Yahoo first and falls back to Stooq per ticker. Force one
# provider with MARKET_DATA_SOURCE=yahoo or =stooq.
SOURCE_MODE = os.environ.get("MARKET_DATA_SOURCE", "auto").strip().lower()

STOOQ_URL = "https://stooq.com/q/d/l/"
STOOQ_TIMEOUT = 20
STOOQ_WORKERS = 6


def extract_symbol_frame(raw, symbol: str):
    """Pull a flat OHLCV frame for ``symbol`` out of any yfinance response shape.

    Handles:

    * flat ``Open/High/Low/Close`` columns (older single-ticker responses)
    * MultiIndex with the ticker on level 0 (``group_by="ticker"``)
    * MultiIndex with the ticker on level 1 (``group_by="column"``)
    * single-ticker MultiIndex responses carrying only field names

    Returns a frame with plain OHLCV columns, or ``None`` when the symbol is not
    present or the response carries no recognizable price data.
    """
    if raw is None or getattr(raw, "empty", True):
        return None

    columns = raw.columns

    if not isinstance(columns, pd.MultiIndex):
        return raw if all(c in columns for c in OHLC) else None

    for level in range(columns.nlevels):
        if symbol in columns.get_level_values(level):
            frame = raw.xs(symbol, axis=1, level=level)
            if all(c in frame.columns for c in OHLC):
                return frame

    # A single-ticker MultiIndex whose remaining level is just the field names.
    if all(c in columns.get_level_values(0) for c in OHLC):
        frame = raw.copy()
        frame.columns = frame.columns.get_level_values(0)
        return frame

    return None


# ---------------------------------------------------------------------------
# Stooq fallback provider
# ---------------------------------------------------------------------------


def stooq_symbol(ticker: str) -> str:
    """Map a Yahoo-style ticker onto Stooq's symbol convention.

    US equities and ETFs take a ``.us`` suffix; index symbols keep their caret
    and take none. Stooq uses dashes for share classes just as Yahoo does, so
    ``BRK-B`` needs no rewriting beyond the suffix.
    """
    symbol = (ticker or "").strip().lower()
    if not symbol:
        return ""
    if symbol.startswith("^"):
        return symbol
    if "." in symbol:
        # Already carries an exchange suffix (e.g. bp.l) — leave it alone.
        return symbol
    return f"{symbol}.us"


def parse_stooq_csv(text: str) -> list[dict]:
    """Parse Stooq's daily CSV into the app's bar dicts.

    Returns ``[]`` for the "no data" responses Stooq serves for unknown symbols
    (and for the HTML error pages it sometimes returns instead of CSV).
    """
    if not text:
        return []
    stripped = text.strip()
    if not stripped or stripped.lower().startswith("<"):
        return []

    bars = []
    for row in csv.DictReader(io.StringIO(stripped)):
        try:
            date = (row.get("Date") or "").strip()
            if not date:
                continue
            bar = {
                "date": date,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(float(row.get("Volume") or 0)),
            }
        except (KeyError, TypeError, ValueError):
            # Stooq emits 'N/A' cells on non-trading rows; skip them.
            continue
        if bar["close"] > 0 and bar["open"] > 0:
            bars.append(bar)

    bars.sort(key=lambda b: b["date"])
    return bars


def fetch_stooq(ticker: str, timeout: int = STOOQ_TIMEOUT) -> list[dict]:
    """Fetch daily OHLCV for one ticker from Stooq. Returns [] on any failure."""
    symbol = stooq_symbol(ticker)
    if not symbol:
        return []
    try:
        import requests
        response = requests.get(
            STOOQ_URL, params={"s": symbol, "i": "d"}, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; iran-tracker/1.0)"},
        )
        if response.status_code != 200:
            logger.warning("Stooq %s returned HTTP %s", symbol, response.status_code)
            return []
        return parse_stooq_csv(response.text)
    except Exception as exc:
        logger.warning("Stooq fetch failed for %s: %s: %s", symbol,
                       type(exc).__name__, exc)
        return []


def fetch_stooq_many(tickers: list[str], timeout: int = STOOQ_TIMEOUT
                     ) -> dict[str, list[dict]]:
    """Fetch several tickers from Stooq concurrently.

    Stooq has no batch endpoint, so this is one request per ticker; a small
    thread pool keeps a 36-ticker board from taking 36 sequential round trips.
    """
    if not tickers:
        return {}

    out: dict[str, list[dict]] = {}
    workers = max(1, min(STOOQ_WORKERS, len(tickers)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for ticker, bars in zip(tickers, pool.map(
            lambda t: fetch_stooq(t, timeout=timeout), tickers
        )):
            if bars:
                out[ticker] = bars
    return out
