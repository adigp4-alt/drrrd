"""WhatsApp Cloud API — send helper and incoming message handler."""

import logging
import os

import requests

from app.data_fetcher import CACHE, fetch_prices
from app.models import execute_db, query_db

logger = logging.getLogger(__name__)

_GRAPH_URL = "https://graph.facebook.com/v19.0"


def send_whatsapp(message, to=None):
    """Send a WhatsApp text message via the Meta Cloud API."""
    token = os.environ.get("WHATSAPP_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    recipient = to or os.environ.get("WHATSAPP_RECIPIENT")
    if not token or not phone_number_id or not recipient:
        return False
    try:
        resp = requests.post(
            f"{_GRAPH_URL}/{phone_number_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "text",
                "text": {"body": message},
            },
            timeout=10,
        )
        return resp.ok
    except Exception as exc:
        logger.error("WhatsApp send error: %s", exc)
        return False


def handle_message(text, sender):
    """Parse an incoming WhatsApp message and return a reply string."""
    parts = text.strip().split()
    if not parts:
        return None
    # Support both "prices" and "/prices" style
    cmd = parts[0].lower().lstrip("/")

    if cmd in ("start", "help"):
        return (
            "*Remote Control Commands:*\n"
            "prices [TICKER] — All prices or a specific ticker\n"
            "portfolio — Portfolio P&L summary\n"
            "refresh — Force price refresh\n"
            "alerts — List active alert rules\n"
            "add TICKER SHARES PRICE — Add a holding"
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
            return f"{sym}: ${d['price']:.2f} ({d['change_pct']:+.2f}%)"
        lines = [
            f"{s}: ${d['price']:.2f} ({d['change_pct']:+.2f}%)"
            for s, d in list(data.items())[:20]
        ]
        ts = CACHE.get("last_updated", "unknown")
        return "\n".join(lines) + f"\nUpdated: {ts}"

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
            lines.append(f"{h['ticker']}: ${mv:,.0f} (PnL: {pnl:+,.0f})")
        lines.append(f"\nTotal: ${total_mv:,.0f} | PnL: {total_pnl:+,.0f}")
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
            return "Usage: add TICKER SHARES PRICE"
        try:
            ticker = parts[1].upper()
            shares = float(parts[2])
            price = float(parts[3])
        except (ValueError, IndexError):
            return "Invalid format. Usage: add TICKER SHARES PRICE"
        execute_db(
            "INSERT INTO holdings (ticker, shares, buy_price) VALUES (?, ?, ?)",
            (ticker, shares, price),
        )
        return f"Added {shares} shares of {ticker} at ${price:.2f}"

    return "Unknown command. Send 'help' to see available commands."
