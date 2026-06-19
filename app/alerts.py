"""Alert engine with Telegram and email integration."""

import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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
            send_email_alert(message)

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


def send_email_alert(message):
    """Send alert via email (SMTP) if configured.

    Required env vars: SMTP_HOST, SMTP_USER, SMTP_PASS, ALERT_EMAIL_TO
    Optional: SMTP_PORT (default 587), SMTP_FROM (defaults to SMTP_USER)
    """
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    to_addr = os.environ.get("ALERT_EMAIL_TO")
    from_addr = os.environ.get("SMTP_FROM", user)

    if not all([host, user, password, to_addr]):
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Iran Tracker Alert: {message[:60]}"
        msg["From"] = from_addr
        msg["To"] = to_addr

        text_body = f"Stock Alert\n\n{message}\n\nSent by Iran Investment Tracker"
        html_body = (
            '<html><body>'
            '<h2 style="color:#1a1a2e">Stock Alert</h2>'
            f'<p style="font-size:16px;padding:12px;background:#f8f9fa;'
            f'border-left:4px solid #2E86C1;margin:16px 0">{message}</p>'
            '<p style="color:#6c757d;font-size:12px">Sent by Iran Investment Tracker</p>'
            '</body></html>'
        )
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(from_addr, [a.strip() for a in to_addr.split(",")], msg.as_string())
        return True
    except Exception:
        logger.exception("Failed to send email alert")
        return False


def test_email():
    """Send a test email to verify SMTP configuration."""
    return send_email_alert("Test alert from Iran Investment Tracker — email is working!")
