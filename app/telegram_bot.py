"""Telegram bot — long-polling command handler for remote control."""

import logging
import os
import threading
import time

import requests

from app.data_fetcher import CACHE, fetch_prices
from app.models import execute_db, query_db

logger = logging.getLogger(__name__)

_offset = 0


def _send_reply(chat_id, text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as exc:
        logger.error("Telegram reply error: %s", exc)


def _handle(text):
    parts = text.strip().split()
    # Strip bot @username suffix (e.g. /start@MyBot → start)
    cmd = parts[0].lower().lstrip("/").split("@")[0]

    if cmd in ("start", "help"):
        return (
            "*Remote Control Commands:*\n"
            "/prices `[TICKER]` — All prices or a specific ticker\n"
            "/portfolio — Portfolio P&L summary\n"
            "/refresh — Force price refresh\n"
            "/alerts — List active alert rules\n"
            "/add `TICKER SHARES PRICE` — Add a holding"
        )

    if cmd == "prices":
        data = CACHE.get("data", {})
        if not data:
            return "No price data available yet."
        if len(parts) > 1:
            sym = parts[1].upper()
            d = data.get(sym)
            if not d:
                return f"{sym} not found."
            return f"*{sym}*: ${d['price']:.2f} ({d['change_pct']:+.2f}%)"
        lines = [
            f"*{s}*: ${d['price']:.2f} ({d['change_pct']:+.2f}%)"
            for s, d in list(data.items())[:20]
        ]
        ts = CACHE.get("last_updated", "unknown")
        return "\n".join(lines) + f"\n_Updated: {ts}_"

    if cmd == "portfolio":
        holdings = query_db("SELECT * FROM holdings")
        if not holdings:
            return "No holdings in portfolio."
        current = CACHE.get("data", {})
        total_mv = total_pnl = 0.0
        lines = []
        for h in holdings:
            price = current.get(h["ticker"], {}).get("price", h["buy_price"])
            mv = h["shares"] * price
            pnl = mv - h["shares"] * h["buy_price"]
            total_mv += mv
            total_pnl += pnl
            lines.append(f"*{h['ticker']}*: ${mv:,.0f} (PnL: {pnl:+,.0f})")
        lines.append(f"\n*Total*: ${total_mv:,.0f} | *PnL*: {total_pnl:+,.0f}")
        return "\n".join(lines)

    if cmd == "refresh":
        fetch_prices()
        return f"Refreshed. Last updated: {CACHE.get('last_updated', 'unknown')}"

    if cmd == "alerts":
        rules = query_db("SELECT * FROM alert_rules WHERE enabled = 1")
        if not rules:
            return "No active alert rules."
        return "\n".join(
            f"{r['ticker']} {r['condition']} {r['threshold']}" for r in rules
        )

    if cmd == "add":
        if len(parts) < 4:
            return "Usage: /add TICKER SHARES PRICE"
        try:
            ticker = parts[1].upper()
            shares = float(parts[2])
            price = float(parts[3])
        except (ValueError, IndexError):
            return "Invalid format. Usage: /add TICKER SHARES PRICE"
        execute_db(
            "INSERT INTO holdings (ticker, shares, buy_price) VALUES (?, ?, ?)",
            (ticker, shares, price),
        )
        return f"Added {shares} shares of {ticker} at ${price:.2f}"

    return "Unknown command. Send /help"


def _poll_loop():
    global _offset
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    allowed_chat = os.environ.get("TELEGRAM_CHAT_ID")

    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"timeout": 30, "offset": _offset},
                timeout=35,
            )
            if not resp.ok:
                time.sleep(5)
                continue
            for upd in resp.json().get("result", []):
                _offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                text = msg.get("text", "")
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if not text.startswith("/"):
                    continue
                if allowed_chat and chat_id != allowed_chat:
                    logger.warning("Rejected command from unknown chat %s", chat_id)
                    continue
                _send_reply(chat_id, _handle(text))
        except requests.exceptions.Timeout:
            pass
        except Exception as exc:
            logger.error("Bot poll error: %s", exc)
            time.sleep(10)


def start_bot():
    threading.Thread(target=_poll_loop, name="telegram-bot", daemon=True).start()
    logger.info("Telegram bot polling started")
