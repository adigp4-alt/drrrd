"""Alert engine and Telegram integration."""

import logging
import os
from datetime import datetime

import requests

from app.models import query_db, execute_db, get_db

logger = logging.getLogger(__name__)


def check_alerts(current_data):
    """Evaluate all enabled alert rules against live data."""
    rules = query_db("SELECT * FROM alert_rules WHERE enabled = 1")
    triggered = []

    for rule in rules:
        ticker = rule["ticker"]
        if ticker not in current_data:
            continue

        stock = current_data[ticker]
        price = stock["price"]
        change = stock["change_pct"]
        volume = stock.get("volume", 0)
        condition = rule["condition"]
        threshold = rule["threshold"]
        fired = False
        message = ""

        if condition == "above" and price >= threshold:
            message = f"{ticker} hit ${price:.2f} (above ${threshold:.2f})"
            fired = True
        elif condition == "below" and price <= threshold:
            message = f"{ticker} dropped to ${price:.2f} (below ${threshold:.2f})"
            fired = True
        elif condition == "change_pct_above" and abs(change) >= threshold:
            direction = "up" if change > 0 else "down"
            message = f"{ticker} moved {change:+.2f}% ({direction}, threshold {threshold}%)"
            fired = True
        elif condition == "volume_spike" and volume >= threshold:
            message = f"{ticker} volume spike: {volume:,} (threshold {threshold:,.0f})"
            fired = True

        if fired:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            execute_db(
                "INSERT INTO alert_history (rule_id, ticker, message) VALUES (?, ?, ?)",
                (rule["id"], ticker, message)
            )
            with get_db() as db:
                db.execute(
                    "UPDATE alert_rules SET last_triggered = ? WHERE id = ?",
                    (now, rule["id"])
                )
            triggered.append({"ticker": ticker, "message": message, "time": now})
            send_telegram(message)

    return triggered


def send_telegram(message):
    """Send alert via Telegram bot if configured."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
        return resp.ok
    except Exception:
        logger.exception("Failed to send Telegram message")
        return False
