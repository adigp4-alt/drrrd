import os
from datetime import datetime, timedelta
import requests
from app.models import query_db, get_db

def check_alerts(current_data, ml_predictions=None, ml_features=None):
    rules = query_db("SELECT * FROM alert_rules WHERE enabled = 1")
    triggered = []
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    inserts = []
    updates = []

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
        
        last_triggered = rule.get("last_triggered")
        if last_triggered:
            try:
                lt_dt = datetime.strptime(last_triggered, "%Y-%m-%d %H:%M:%S")
                if now - lt_dt < timedelta(hours=24):
                    continue
            except ValueError:
                pass
                
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
            
        if not fired and ml_predictions and ml_features:
            regime = ml_predictions.get(ticker, {}).get("regime")
            if condition == "regime_change" and regime and regime == threshold:
                message = f"{ticker} entered new regime: {regime}"
                fired = True
                
            bb_width = ml_features.get(ticker, {}).get("bb_width")
            if condition == "bollinger_squeeze" and bb_width is not None and bb_width <= threshold:
                message = f"{ticker} Bollinger Band squeeze detected (width {bb_width:.3f} <= {threshold})"
                fired = True

        if fired:
            inserts.append((rule["id"], ticker, message, now_str))
            updates.append((now_str, rule["id"]))
            triggered.append({"ticker": ticker, "message": message, "time": now_str})
            send_telegram(message)

    if inserts or updates:
        with get_db() as db:
            if inserts:
                db.executemany("INSERT INTO alert_history (rule_id, ticker, message, triggered_at) VALUES (?, ?, ?, ?)", inserts)
            if updates:
                db.executemany("UPDATE alert_rules SET last_triggered = ? WHERE id = ?", updates)
            db.commit()

    return triggered

def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
        return resp.ok
    except Exception:
        return False