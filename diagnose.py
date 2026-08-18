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

It walks up from the network to the app: DNS, then raw HTTPS to each origin,
then each of the app's three price providers individually, then yfinance's two
internal code paths. Because the app only needs *one* provider to work, a
failure partway up the stack is often not a problem at all — the verdict says
so rather than sending you after it.
"""

from __future__ import annotations

import io
import logging
import platform
import socket
import sys
import time

CANARY = "SPY"
LINE = "-" * 68


def head(title):
    print(f"\n{LINE}\n{title}\n{LINE}")


def yfinance_is_outdated():
    """Report whether a newer yfinance exists.

    Yahoo periodically changes the cookie/crumb handshake, which breaks the
    installed yfinance until it is updated — and the symptom is an empty frame
    with no error, so it is invisible from the app. Checking PyPI turns that
    into a one-line answer.
    """
    try:
        import json as _json
        import urllib.request
        import yfinance as yf
        with urllib.request.urlopen(
            "https://pypi.org/pypi/yfinance/json", timeout=10
        ) as response:
            latest = _json.load(response)["info"]["version"]
        installed = yf.__version__
        if latest != installed:
            print(f"  yfinance      {installed}  ->  {latest} AVAILABLE  "
                  f"(pip install -U yfinance)")
            return True
        print(f"  yfinance      {installed}  (latest)")
        return False
    except Exception:
        return None


def versions():
    head("VERSIONS")
    print(f"  python        {platform.python_version()}  ({platform.system()} "
          f"{platform.machine()})")
    outdated = yfinance_is_outdated()
    for name in ("pandas", "numpy", "requests", "curl_cffi"):
        try:
            mod = __import__(name)
            print(f"  {name:<13} {getattr(mod, '__version__', 'unknown')}")
        except Exception as exc:
            print(f"  {name:<13} NOT INSTALLED ({type(exc).__name__})")
    return outdated


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


def app_providers():
    """Run the app's own providers, in the order the app tries them.

    The raw probes above only show that bytes come back. These run the real
    parsers, which is what decides whether the board populates.
    """
    head("APP PROVIDERS (what the board actually uses)")
    results = {}
    try:
        from app import market_data
    except Exception as exc:
        print(f"  could not import the app: {type(exc).__name__}: {exc}")
        print("  (run this from the repository root)")
        return results

    # The providers log their own failures, which would interleave with this
    # report; the lines below say the same thing in one place.
    logging.getLogger("app").setLevel(logging.CRITICAL)

    for label, call in (
        ("1. Yahoo chart API", lambda: market_data.fetch_yahoo_chart(
            CANARY, period="1mo")),
        ("3. Stooq", lambda: market_data.fetch_stooq(CANARY)),
    ):
        try:
            started = time.time()
            bars = call()
            ms = round((time.time() - started) * 1000)
            latest = bars[-1]["date"] if bars else "-"
            print(f"  {label:<22} {len(bars)} bars  {ms}ms  latest {latest}")
            results[label] = bool(bars)
        except Exception as exc:
            print(f"  {label:<22} FAILED {type(exc).__name__}: {exc}")
            results[label] = False
    print("  (2. yfinance is probed separately below)")
    return results


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


def verdict(dns_ok, yahoo_ok, stooq_ok, yf_ok, outdated, providers):
    head("VERDICT")
    chart_ok = providers.get("1. Yahoo chart API")
    app_stooq_ok = providers.get("3. Stooq")
    any_provider = chart_ok or app_stooq_ok

    if not dns_ok:
        print("  No DNS. This machine has no working internet connection.")
        return

    if any_provider:
        # yfinance is the *second* of three providers now, so it failing is not
        # a fault — say so plainly rather than sending anyone chasing it.
        working = [n for n, ok in (("the Yahoo chart API", chart_ok),
                                   ("Stooq", app_stooq_ok)) if ok]
        print(f"  Market data IS reachable via {' and '.join(working)}.\n"
              "  The board should populate. If it is still empty, the problem is\n"
              "  in the app rather than the data — paste this report plus whatever\n"
              "  the board's red banner says.\n")
        if not yf_ok:
            print("  (yfinance returned nothing, but that no longer matters: it is\n"
                  "   the second of three providers and the app does not need it.")
            if outdated:
                print("   `pip install -U yfinance` would still fix it if you want\n"
                      "   that path back.)")
            else:
                print("   Nothing to do.)")
        return

    # No provider works. Now the raw probes tell us which layer is at fault.
    if outdated and not yf_ok:
        print("  A NEWER yfinance IS AVAILABLE and the installed one returned\n"
              "  nothing. Do this first:\n"
              "      pip install -U yfinance\n"
              "  then re-run this script.\n")

    if yahoo_ok:
        print("  Yahoo answers over plain HTTPS, but the app could not parse bars\n"
              "  out of the response — Yahoo has likely changed its chart format.\n"
              "  Paste this report; market_data.parse_yahoo_chart needs updating.")
    elif stooq_ok:
        print("  Yahoo is refusing this machine, but Stooq answers over raw HTTPS\n"
              "  while the app's Stooq provider got nothing. Paste this report.")
    else:
        print("  Nothing is reachable, though DNS resolves. Something between this\n"
              "  machine and the internet is blocking HTTPS — corporate network,\n"
              "  VPN, firewall or proxy.")


def main():
    print("ForesightTape market-data diagnostic")
    outdated = versions()
    dns_ok = dns()
    yahoo_ok, stooq_ok = raw_http()
    providers = app_providers()
    yf_ok = yfinance_probe()
    verdict(dns_ok, yahoo_ok, stooq_ok, yf_ok, outdated, providers)
    print(f"\n{LINE}\nPaste everything above when reporting the problem.\n{LINE}")
    return 0 if any(providers.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
