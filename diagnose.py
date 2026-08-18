#!/usr/bin/env python3
"""Standalone market-data diagnostic.

Run this on whatever machine the app is failing on:

    python diagnose.py

It needs no server running and prints a single self-contained report. Paste the
whole thing when reporting a blank board.

Why this exists: yfinance reports most failures by *logging* them and returning
an empty frame, so the calling code sees "no data" with no exception and no
reason. That makes a blocked IP, a rate limit, an API change and a bad symbol
all look identical from the app. This captures yfinance's own log output and
probes each layer separately so they can be told apart.
"""

from __future__ import annotations

import io
import json
import logging
import platform
import socket
import sys
import time

CANARY = "SPY"
LINE = "-" * 68


def head(title):
    print(f"\n{LINE}\n{title}\n{LINE}")


def versions():
    head("VERSIONS")
    print(f"  python        {platform.python_version()}  ({platform.system()} "
          f"{platform.machine()})")
    for name in ("yfinance", "pandas", "numpy", "requests", "curl_cffi"):
        try:
            mod = __import__(name)
            print(f"  {name:<13} {getattr(mod, '__version__', 'unknown')}")
        except Exception as exc:
            print(f"  {name:<13} NOT INSTALLED ({type(exc).__name__})")


def dns():
    head("DNS")
    ok = False
    for host in ("query1.finance.yahoo.com", "stooq.com"):
        try:
            print(f"  {host:<32} -> {socket.gethostbyname(host)}")
            ok = True
        except Exception as exc:
            print(f"  {host:<32} -> FAILED {type(exc).__name__}: {exc}")
    return ok


def https_probe(name, url, expect):
    try:
        import requests
        started = time.time()
        r = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
        })
        ms = round((time.time() - started) * 1000)
        body = r.text or ""
        good = r.status_code == 200 and expect in body
        print(f"  {name:<22} HTTP {r.status_code}  {ms}ms  {len(body)}B  "
              f"{'looks like data' if good else 'NO DATA IN BODY'}")
        if not good:
            print(f"    body starts: {body[:180]!r}")
        return good
    except Exception as exc:
        print(f"  {name:<22} FAILED {type(exc).__name__}: {exc}")
        return False


def raw_http():
    head("RAW HTTPS (bypasses yfinance entirely)")
    yahoo = https_probe(
        "Yahoo chart API",
        f"https://query1.finance.yahoo.com/v8/finance/chart/{CANARY}"
        "?range=5d&interval=1d",
        '"timestamp"')
    stooq = https_probe("Stooq CSV",
                        f"https://stooq.com/q/d/l/?s={CANARY.lower()}.us&i=d",
                        "Date,Open")
    return yahoo, stooq


def yfinance_probe():
    """Call yfinance while capturing the log records it emits instead of raising."""
    head("YFINANCE")
    try:
        import yfinance as yf
    except Exception as exc:
        print(f"  import failed: {type(exc).__name__}: {exc}")
        return False

    captured = io.StringIO()
    handler = logging.StreamHandler(captured)
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger("yfinance")
    previous_level, previous_propagate = root.level, root.propagate
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)

    any_ok = False
    try:
        for label, call in (
            ("download()", lambda: yf.download(CANARY, period="5d", progress=False,
                                               auto_adjust=False, threads=False)),
            ("Ticker.history()", lambda: yf.Ticker(CANARY).history(period="5d")),
        ):
            try:
                frame = call()
                rows = 0 if frame is None else len(frame)
                print(f"  {label:<20} {rows} rows"
                      + (f", columns={list(frame.columns)[:6]}" if rows else ""))
                any_ok = any_ok or rows > 0
            except Exception as exc:
                print(f"  {label:<20} RAISED {type(exc).__name__}: {exc}")
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)
        root.propagate = previous_propagate

    log = captured.getvalue().strip()
    if log:
        print("\n  --- yfinance's own log (this usually names the real cause) ---")
        for line in log.splitlines()[:25]:
            print(f"  | {line[:160]}")
    return any_ok


def verdict(dns_ok, yahoo_ok, stooq_ok, yf_ok):
    head("VERDICT")
    if not dns_ok:
        print("  No DNS. This machine has no working internet connection.")
    elif yf_ok:
        print("  yfinance IS returning data. If the board is still empty, the\n"
              "  problem is in the app rather than the data source — report this\n"
              "  report plus what the board's red banner says.")
    elif yahoo_ok and not yf_ok:
        print("  Yahoo answers fine over plain HTTPS, but yfinance returns nothing.\n"
              "  That is a yfinance/API mismatch, not a network or IP problem.\n"
              "  Try:  pip install -U yfinance\n"
              "  If that fixes it, say so and the version will be pinned.")
    elif not yahoo_ok and stooq_ok:
        print("  Yahoo is refusing or failing for this machine, but Stooq works.\n"
              "  The app's fallback should cover this — make sure you are running\n"
              "  the latest code, and set MARKET_DATA_SOURCE=stooq to force it.")
    elif not yahoo_ok and not stooq_ok:
        print("  Neither Yahoo nor Stooq is reachable, though DNS resolves.\n"
              "  Something between this machine and the internet is blocking\n"
              "  HTTPS — corporate network, VPN, firewall or proxy.")
    else:
        print("  Inconclusive — paste the whole report.")


def main():
    print("ForesightTape market-data diagnostic")
    versions()
    dns_ok = dns()
    yahoo_ok, stooq_ok = raw_http()
    yf_ok = yfinance_probe()
    verdict(dns_ok, yahoo_ok, stooq_ok, yf_ok)
    print(f"\n{LINE}\nPaste everything above when reporting the problem.\n{LINE}")
    return 0 if yf_ok or stooq_ok else 1


if __name__ == "__main__":
    sys.exit(main())
