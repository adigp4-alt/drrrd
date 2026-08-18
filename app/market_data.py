"""Market data access: three independent providers behind one interface.

Every blank board this app has produced traced back to depending on a single
path to prices. There are three distinct failure modes, and no amount of care
in any one provider covers the other two:

1. **yfinance's Yahoo session breaks.** Yahoo periodically changes its
   cookie/crumb handshake. Until yfinance is updated to match, it returns an
   empty frame *and logs the reason instead of raising*, so the app sees "no
   data" with no exception and no cause.
2. **yfinance response shapes change between releases.** Since 1.x,
   ``multi_level_index`` defaults to True, so even a single-ticker download
   returns MultiIndex columns — breaking the long-standing "flat frame when
   there's one ticker" assumption throughout this app.
3. **Yahoo throttles and blocks datacenter IP ranges.** Cloud hosts are refused
   often enough that depending on Yahoo alone is fragile by construction. No
   parsing care fixes an HTTP 429.

So there are three providers, tried in order of how little can go wrong:

* **Yahoo's chart API, called directly** (``fetch_yahoo_chart``). This is the
  same JSON endpoint yfinance ultimately reads, but reached with plain
  ``requests`` and no cookie/crumb handshake — chart data does not require the
  crumb, only the quote/fundamentals endpoints do. That makes this path immune
  to both (1) and (2): there is no library version to drift and no session to
  break. The diagnostics module has always probed this endpoint to prove Yahoo
  was reachable while the board sat empty; this makes the app able to *use* it.
* **yfinance** (in ``forecast_engine``). Kept as the second path because it
  carries its own retry and session handling, which occasionally succeeds where
  a bare request is refused.
* **Stooq** (``fetch_stooq``), a different origin entirely: daily OHLCV as plain
  CSV, no API key. Covers (3), when Yahoo refuses this host outright.

The board reports which source actually served the data, so a degraded path is
visible rather than silent.

Keeping all shape handling here means a future yfinance bump is a single fix
(and a failing unit test) rather than a hunt across every module that reads
market data.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd

logger = logging.getLogger(__name__)

OHLC = ("Open", "High", "Low", "Close")

# How the providers are ordered:
#   auto (default) — Yahoo chart API, then yfinance, then Stooq
#   yahoo          — the two Yahoo paths only, no Stooq
#   stooq          — Stooq only
#   chart          — the direct chart API only   (diagnostic isolation)
#   yfinance       — the yfinance path only      (diagnostic isolation)
SOURCE_MODE = os.environ.get("MARKET_DATA_SOURCE", "auto").strip().lower()

STOOQ_URL = "https://stooq.com/q/d/l/"
STOOQ_TIMEOUT = 20
STOOQ_WORKERS = 6

# query1 and query2 are separate pools; one can be throttled while the other
# answers, so a refusal is worth retrying against the sibling before giving up.
YAHOO_CHART_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
YAHOO_CHART_TIMEOUT = 20
YAHOO_CHART_WORKERS = 6

# Yahoo serves an error page to obviously-scripted clients; a browser UA gets
# the JSON. This is the same header the diagnostics probe has always sent.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


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
# Yahoo chart API, called directly (no yfinance, no cookie/crumb handshake)
# ---------------------------------------------------------------------------


def _chart_result(payload, symbol: str = ""):
    """Unwrap the ``chart.result[0]`` object, or ``None`` if there isn't one.

    Yahoo signals a bad symbol through ``chart.error`` with a 200 status, so the
    error case has to be read out of the body rather than the status code.
    """
    if isinstance(payload, (str, bytes)):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            return None
    if not isinstance(payload, dict):
        return None

    chart = payload.get("chart")
    if not isinstance(chart, dict):
        return None

    error = chart.get("error")
    if error:
        description = error.get("description") if isinstance(error, dict) else error
        logger.warning("Yahoo chart error for %s: %s", symbol or "?", description)
        return None

    results = chart.get("result")
    if not results or not isinstance(results[0], dict):
        return None
    return results[0]


def parse_yahoo_chart(payload, symbol: str = "") -> list[dict]:
    """Parse Yahoo's ``v8/finance/chart`` JSON into the app's bar dicts.

    The response carries parallel arrays — one timestamp list and one list per
    OHLCV field — which have to be zipped back into rows. Yahoo writes ``null``
    into those arrays for sessions it has no print for, and the nulls are *not*
    aligned across fields, so any row missing a price is dropped rather than
    guessed at.

    Timestamps are epoch seconds, but the date that matters is the one on the
    exchange's calendar, not UTC. Yahoo supplies ``meta.gmtoffset`` for exactly
    this; ignoring it puts every Sydney and Auckland bar on the wrong day.

    Returns ``[]`` for error responses and unknown symbols rather than raising —
    a bad ticker in a 36-ticker board must not take the board down with it.
    """
    result = _chart_result(payload, symbol)
    if result is None:
        return []

    timestamps = result.get("timestamp") or []
    quotes = (result.get("indicators") or {}).get("quote") or []
    if not timestamps or not quotes or not isinstance(quotes[0], dict):
        return []

    quote = quotes[0]
    series = [quote.get(field) or []
              for field in ("open", "high", "low", "close")]
    volumes = quote.get("volume") or []

    try:
        gmtoffset = int((result.get("meta") or {}).get("gmtoffset") or 0)
    except (TypeError, ValueError):
        gmtoffset = 0

    bars = []
    for i, ts in enumerate(timestamps):
        if ts is None or any(i >= len(s) for s in series):
            continue
        prices = [s[i] for s in series]
        if any(p is None for p in prices):
            continue
        try:
            local = datetime.fromtimestamp(int(ts) + gmtoffset, tz=timezone.utc)
            open_, high, low, close = (float(p) for p in prices)
            volume = int(volumes[i]) if i < len(volumes) and volumes[i] else 0
        except (TypeError, ValueError, OSError, OverflowError):
            continue
        if open_ > 0 and close > 0:
            bars.append({
                "date": local.strftime("%Y-%m-%d"),
                "open": open_, "high": high, "low": low, "close": close,
                "volume": volume,
            })

    bars.sort(key=lambda b: b["date"])
    return bars


def fetch_yahoo_chart(ticker: str, period: str = "1y",
                      timeout: int = YAHOO_CHART_TIMEOUT) -> list[dict]:
    """Fetch daily OHLCV for one ticker straight from Yahoo's chart endpoint.

    Tries both query hosts before giving up. Returns ``[]`` on any failure —
    callers fall through to the next provider.
    """
    symbol = (ticker or "").strip()
    if not symbol:
        return []

    try:
        import requests
    except Exception as exc:  # pragma: no cover - requests is a hard dependency
        logger.warning("requests unavailable: %s", exc)
        return []

    last_detail = ""
    for host in YAHOO_CHART_HOSTS:
        url = f"https://{host}/v8/finance/chart/{symbol}"
        try:
            response = requests.get(
                url, params={"range": period, "interval": "1d"}, timeout=timeout,
                headers={"User-Agent": BROWSER_UA, "Accept": "application/json"},
            )
        except Exception as exc:
            last_detail = f"{type(exc).__name__}: {exc}"
            logger.warning("Yahoo chart %s via %s failed: %s", symbol, host,
                           last_detail)
            continue

        if response.status_code != 200:
            last_detail = f"HTTP {response.status_code}"
            logger.warning("Yahoo chart %s via %s returned %s", symbol, host,
                           last_detail)
            # 404 is the symbol's own answer, identical on both hosts.
            if response.status_code == 404:
                return []
            continue

        bars = parse_yahoo_chart(response.text, symbol)
        if bars:
            return bars
        last_detail = "no bars in response"

    if last_detail:
        logger.info("Yahoo chart gave up on %s (%s)", symbol, last_detail)
    return []


def fetch_yahoo_chart_many(tickers: list[str], period: str = "1y",
                           timeout: int = YAHOO_CHART_TIMEOUT
                           ) -> dict[str, list[dict]]:
    """Fetch several tickers from the chart endpoint concurrently.

    The endpoint is one symbol per request, so a small thread pool keeps a
    36-ticker board from costing 36 sequential round trips.
    """
    if not tickers:
        return {}

    out: dict[str, list[dict]] = {}
    workers = max(1, min(YAHOO_CHART_WORKERS, len(tickers)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for ticker, bars in zip(tickers, pool.map(
            lambda t: fetch_yahoo_chart(t, period=period, timeout=timeout), tickers
        )):
            if bars:
                out[ticker] = bars
    return out


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
