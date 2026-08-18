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
import os
import platform
import socket
import subprocess
import time

from app import market_data

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


def _deployment() -> dict:
    """Identify which build is actually running.

    "I redeployed and it still doesn't work" has two very different meanings —
    the fix didn't work, or the fix isn't there — and from outside they look the
    same. This makes the running build say what it is.

    ``providers`` is the useful part: it lists the price sources *this build*
    knows about. A build predating the multi-provider chain reports only the
    ones it has, which identifies a stale deploy immediately.
    """
    from app import forecast_engine

    info = {
        # Render injects these; other hosts generally don't.
        "commit": os.environ.get("RENDER_GIT_COMMIT", ""),
        "branch": os.environ.get("RENDER_GIT_BRANCH", ""),
        "service": os.environ.get("RENDER_SERVICE_NAME", ""),
        "source_mode": market_data.SOURCE_MODE,
        "providers": list(getattr(forecast_engine, "_PROVIDERS", {})),
    }
    if not info["commit"]:
        # Local runs: read it from git rather than leaving the field blank.
        try:
            info["commit"] = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ).stdout.strip()
        except Exception:
            pass
    return {k: v for k, v in info.items() if v}


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


def _chart_probe() -> dict:
    """Try the primary provider: Yahoo's chart endpoint, parsed by this app.

    Distinct from ``_https_probe`` above, which only checks that bytes come
    back. This runs the real parser, so it separates "Yahoo answered" from
    "we got usable bars out of what Yahoo answered".
    """
    from app.market_data import fetch_yahoo_chart

    try:
        started = time.time()
        bars = fetch_yahoo_chart(CANARY, period="1mo")
        return {
            "ok": bool(bars),
            "ms": round((time.time() - started) * 1000, 1),
            "bars": len(bars),
            "latest": bars[-1]["date"] if bars else None,
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _stooq_probe() -> dict:
    """Try the last-resort provider. If this works, the board can work."""
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
             stooq: dict, chart: dict) -> dict:
    """Turn the probe results into a cause and a recommended action.

    Order matters: the engine's own fetch is the question the user is actually
    asking ("why is my board empty?"), so a working engine is reported as
    healthy even when a *secondary* provider is down. yfinance failing on its
    own is no longer a fault — it is the second of three providers, and the
    board is expected to run without it.
    """
    resolved = any(v.get("resolved") for v in dns.values())
    if not resolved:
        return {
            "cause": "dns_failure",
            "summary": "Yahoo Finance hostnames do not resolve from this host.",
            "action": "The host has no working DNS or outbound network. Check the "
                      "platform's egress settings.",
        }

    if engine.get("ok"):
        degraded = [name for name, probe in
                    (("Yahoo chart API", chart), ("Stooq", stooq))
                    if not probe.get("ok")]
        note = (f" Note: {' and '.join(degraded)} did not answer, so the board is "
                "running on a reduced set of providers." if degraded else "")
        return {
            "cause": "healthy",
            "summary": "Market data is reachable and parsing correctly.",
            "action": "If the board is still empty, the configured tickers may be "
                      "delisted or invalid — check the 'skipped' list on a scan."
                      + note,
        }

    # Past this point the engine produced nothing, so name the layer that broke.
    if chart.get("ok"):
        return {
            "cause": "engine_failure",
            "summary": "Yahoo's chart API returns usable bars, but the engine's "
                       "fetch produced nothing — so the fault is in this app, not "
                       "in the network or the data source.",
            "action": "Check MARKET_DATA_SOURCE (it may be pinned to a provider "
                      "that is down) and report the 'engine_fetch' reasons below.",
        }

    fallback_note = (
        " Stooq IS working, so the board should still populate — if it does not, "
        "redeploy to pick up the fallback."
        if stooq.get("ok") else
        " Stooq is also failing, so this host likely has no outbound access to "
        "market data at all."
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

    # Yahoo answers raw HTTPS but the chart provider got no bars out of it —
    # that is a response-format change on Yahoo's side, and it is this app's
    # parser that needs updating, not yfinance.
    return {
        "cause": "chart_parse_failure",
        "summary": "Yahoo answers over HTTPS, but no usable bars could be parsed "
                   "from its chart response — the response format has likely "
                   "changed.",
        "action": "Report the 'body_preview' field below; "
                  "market_data.parse_yahoo_chart needs updating to match."
                  + fallback_note,
    }


def run_diagnostics() -> dict:
    """Probe every layer between this process and market data."""
    dns = _dns_probe()
    https = _https_probe()
    chart = _chart_probe()
    yfin = _yfinance_probe()
    stooq = _stooq_probe()
    engine = _engine_probe()
    verdict = _verdict(dns, https, yfin, engine, stooq, chart)

    logger.info("Market data diagnostics: %s — %s", verdict["cause"],
                verdict["summary"])

    return {
        "verdict": verdict,
        "deployment": _deployment(),
        "versions": _versions(),
        "probes": {
            "dns": dns,
            "https_direct": https,
            "yahoo_chart_provider": chart,
            "yfinance": yfin,
            "stooq_fallback": stooq,
            "engine_fetch": engine,
        },
    }
