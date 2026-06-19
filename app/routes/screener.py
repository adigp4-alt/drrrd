"""Stock screener routes — filter all tickers by computed criteria."""

from flask import Blueprint, jsonify, render_template, request

from app.config import ALL_TICKERS, TICKER_META
from app.data_fetcher import CACHE
from app.indicators import rsi

bp = Blueprint("screener", __name__)


@bp.route("/screener")
def screener_page():
    return render_template("screener.html")


@bp.route("/api/screener")
def api_screener():
    """Scan all tickers and filter by RSI / change% / volume / signal.

    Query params (all optional):
      rsi_min, rsi_max         -> RSI band (0-100)
      change_min               -> minimum absolute daily change %
      signal                   -> oversold | overbought | neutral
      tier                     -> T1..T5
    """
    prices = CACHE.get("data", {})
    history = CACHE.get("history", {})
    if not prices:
        return jsonify({"error": "Prices not loaded yet"}), 503

    rsi_min = request.args.get("rsi_min", type=float)
    rsi_max = request.args.get("rsi_max", type=float)
    change_min = request.args.get("change_min", type=float)
    signal = request.args.get("signal")
    tier = request.args.get("tier")

    rows = []
    for ticker in ALL_TICKERS:
        p = prices.get(ticker)
        if not p:
            continue

        # Compute current RSI from cached history when available
        cur_rsi = None
        series = history.get(ticker)
        if series and len(series) >= 15:
            closes = [pt["close"] for pt in series]
            vals = rsi(closes, 14)
            cur_rsi = vals[-1]

        sig = "neutral"
        if cur_rsi is not None:
            if cur_rsi <= 30:
                sig = "oversold"
            elif cur_rsi >= 70:
                sig = "overbought"

        meta = TICKER_META.get(ticker, {})
        rows.append({
            "ticker": ticker,
            "name": meta.get("name", ticker),
            "tier": meta.get("tier", ""),
            "price": p.get("price"),
            "change_pct": p.get("change_pct"),
            "volume": p.get("volume"),
            "rsi": cur_rsi,
            "signal": sig,
        })

    # Apply filters
    def keep(r):
        if tier and r["tier"] != tier:
            return False
        if signal and r["signal"] != signal:
            return False
        if rsi_min is not None and (r["rsi"] is None or r["rsi"] < rsi_min):
            return False
        if rsi_max is not None and (r["rsi"] is None or r["rsi"] > rsi_max):
            return False
        if change_min is not None and abs(r.get("change_pct") or 0) < change_min:
            return False
        return True

    filtered = [r for r in rows if keep(r)]
    return jsonify({"results": filtered, "total_scanned": len(rows), "matched": len(filtered)})
