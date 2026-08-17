"""Market-data diagnostics: why is the board empty?

An empty forecast board has several very different causes that look identical
from the UI, and the fixes have nothing in common:

* **The host's IP is blocked or rate-limited by Yahoo.** Common on cloud
  providers — Yahoo aggressively throttles datacenter address ranges. No code
  change fixes it; you need a different egress path or a different data source.
* **yfinance version drift.** yfinance changes its response shape often. If the
  frame comes back populated but the columns are not where the parser expects,
  every ticker is skipped.
* **Genuine network failure.** DNS, egress firewall, proxy.
* **A bad ticker list.** Delisted or mistyped symbols return nothing, correctly.

This module probes each layer independently and reports what it finds, so the
cause is identified rather than guessed at.
"""

from __future__ import annotations

import logging
import platform
import socket
import time

logger = logging.getLogger(__name__)

# A liquid, long-listed symbol. If this returns nothing, the problem is the
# connection or the library — not the ticker.
CANARY = "SPY"

YAHOO_HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]


def _versions() -> dict:
    out = {"python": platform.python_version()}
    for name in ("yfinance", "pandas", "numpy", "requests", "curl_cffi"):
        try:
            module = __import__(name)
            out[name] = getattr(module, "__version__", "unknown")
        except Exception:
            out[name] = "not installed"
    return out


def _dns_probe() -> dict:
    """Can we even resolve Yahoo's hosts?"""
    results = {}
    for host in YAHOO_HOSTS:
        try:
            started = time.time()
            addr = socket.gethostbyname(host)
            results[host] = {
                "resolved": True, "address": addr,
                "ms": round((time.time() - started) * 1000, 1),
            }
        except Exception as exc:
            results[host] = {"resolved": False, "error": f"{type(exc).__name__}: {exc}"}
    return results


def _https_probe() -> dict:
    """Reach Yahoo's chart endpoint directly, bypassing yfinance entirely.

    This is the probe that separates "the network/IP is blocked" from "yfinance
    cannot parse what it got back" — the two causes that look the same from the
    board but need completely different fixes.
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{CANARY}?range=5d&interval=1d"
    try:
        import requests
        started = time.time()
        response = requests.get(
            url, timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; iran-tracker/1.0)"},
        )
        body = response.text or ""
        return {
            "ok": response.status_code == 200,
            "status_code": response.status_code,
            "ms": round((time.time() - started) * 1000, 1),
            "bytes": len(body),
            "looks_like_data": '"timestamp"' in body or '"close"' in body,
            "body_preview": body[:300],
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _yfinance_probe() -> dict:
    """Try both yfinance code paths on the canary symbol."""
    results = {}

    try:
        import yfinance as yf
    except Exception as exc:
        return {"import_error": f"{type(exc).__name__}: {exc}"}

    # Path 1: the batch download the engine actually uses.
    try:
        started = time.time()
        frame = yf.download(CANARY, period="5d", progress=False,
                            auto_adjust=False, threads=False)
        results["download"] = {
            "ok": frame is not None and not frame.empty,
            "ms": round((time.time() - started) * 1000, 1),
            "rows": 0 if frame is None else len(frame),
            "columns": [] if frame is None else [str(c) for c in frame.columns][:12],
        }
    except Exception as exc:
        results["download"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # Path 2: the per-ticker history API, a different code path inside yfinance.
    try:
        started = time.time()
        frame = yf.Ticker(CANARY).history(period="5d")
        results["ticker_history"] = {
            "ok": frame is not None and not frame.empty,
            "ms": round((time.time() - started) * 1000, 1),
            "rows": 0 if frame is None else len(frame),
            "columns": [] if frame is None else [str(c) for c in frame.columns][:12],
        }
    except Exception as exc:
        results["ticker_history"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    return results


def _stooq_probe() -> dict:
    """Try the fallback provider. If this works, the board can work."""
    from app.market_data import fetch_stooq, stooq_symbol

    try:
        started = time.time()
        bars = fetch_stooq(CANARY)
        return {
            "ok": bool(bars),
            "symbol": stooq_symbol(CANARY),
            "ms": round((time.time() - started) * 1000, 1),
            "bars": len(bars),
            "latest": bars[-1]["date"] if bars else None,
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _engine_probe() -> dict:
    """Run the engine's own fetch path and report what it produced."""
    from app.forecast_engine import fetch_bars_with_reasons

    try:
        started = time.time()
        bars, reasons = fetch_bars_with_reasons([CANARY], period="1y")
        got = bars.get(CANARY) or []
        return {
            "ok": bool(got),
            "ms": round((time.time() - started) * 1000, 1),
            "bars": len(got),
            "reasons": reasons,
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _verdict(dns: dict, https: dict, yfin: dict, engine: dict,
             stooq: dict) -> dict:
    """Turn the probe results into a cause and a recommended action."""
    resolved = any(v.get("resolved") for v in dns.values())
    if not resolved:
        return {
            "cause": "dns_failure",
            "summary": "Yahoo Finance hostnames do not resolve from this host.",
            "action": "The host has no working DNS or outbound network. Check the "
                      "platform's egress settings.",
        }

    # A working fallback changes the recommended action entirely: the board can
    # serve data even while Yahoo refuses this host.
    fallback_note = (
        " The Stooq fallback IS working, so the board should still populate — "
        "if it does not, redeploy to pick up the fallback."
        if stooq.get("ok") else
        " The Stooq fallback is also failing, so this host likely has no "
        "outbound access to market data at all."
    )

    if https.get("status_code") == 429:
        return {
            "cause": "rate_limited",
            "summary": "Yahoo Finance is rate-limiting this host (HTTP 429).",
            "action": "Cloud provider IP ranges get throttled aggressively. Wait "
                      "and retry, reduce scan frequency, or route market data "
                      "through a different egress or data provider." + fallback_note,
        }

    if https.get("status_code") in (401, 403):
        return {
            "cause": "ip_blocked",
            "summary": f"Yahoo Finance refused this host "
                       f"(HTTP {https.get('status_code')}).",
            "action": "This IP range is blocked by Yahoo." + fallback_note,
        }

    if not https.get("ok"):
        return {
            "cause": "network_blocked",
            "summary": "Could not reach Yahoo Finance over HTTPS.",
            "action": "Outbound HTTPS to Yahoo is failing. Check egress rules, "
                      "firewall, or proxy on the host." + fallback_note,
        }

    download_ok = (yfin.get("download") or {}).get("ok")
    history_ok = (yfin.get("ticker_history") or {}).get("ok")

    if https.get("ok") and not (download_ok or history_ok):
        return {
            "cause": "yfinance_failure",
            "summary": "Yahoo is reachable and returns data, but yfinance produced "
                       "nothing — most likely a library/API version mismatch.",
            "action": "Pin or upgrade yfinance (`pip install -U yfinance`) and "
                      "redeploy. The raw HTTPS probe above shows Yahoo itself is fine.",
        }

    if (download_ok or history_ok) and not engine.get("ok"):
        return {
            "cause": "parser_mismatch",
            "summary": "yfinance returns data but the engine's parser rejected it — "
                       "the response shape has changed.",
            "action": "Report the 'columns' fields above; the batch-download frame "
                      "layout no longer matches what fetch_bars expects.",
        }

    if engine.get("ok"):
        return {
            "cause": "healthy",
            "summary": "Market data is reachable and parsing correctly.",
            "action": "If the board is still empty, the configured tickers may be "
                      "delisted or invalid — check the 'skipped' list on a scan.",
        }

    return {
        "cause": "unknown",
        "summary": "Probes were inconclusive.",
        "action": "Review the raw probe output below.",
    }


def run_diagnostics() -> dict:
    """Probe every layer between this process and market data."""
    dns = _dns_probe()
    https = _https_probe()
    yfin = _yfinance_probe()
    stooq = _stooq_probe()
    engine = _engine_probe()
    verdict = _verdict(dns, https, yfin, engine, stooq)

    logger.info("Market data diagnostics: %s — %s", verdict["cause"],
                verdict["summary"])

    return {
        "verdict": verdict,
        "versions": _versions(),
        "probes": {
            "dns": dns,
            "https_direct": https,
            "yfinance": yfin,
            "stooq_fallback": stooq,
            "engine_fetch": engine,
        },
    }
