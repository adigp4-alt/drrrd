"""Background scheduler for periodic data fetching, strategy, and digest."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import (
    PRICE_FETCH_INTERVAL, AUTO_SCAN_INTERVAL, HISTORY_FETCH_HOURS, DIGEST_HOUR,
)
from app.data_fetcher import fetch_prices, fetch_history_data, CACHE
from app.strategy import run_autonomous_scan
from app.reports import build_digest_text
from app.alerts import send_email_alert

logger = logging.getLogger(__name__)


def send_daily_digest():
    """Build and email the daily digest (no-op if email is not configured)."""
    text = build_digest_text(CACHE.get("data", {}))
    if send_email_alert(text):
        logger.info("Daily digest email sent")
    else:
        logger.info("Daily digest skipped (email not configured)")


def start_scheduler():
    """Start background jobs with configurable intervals."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_prices, "interval", minutes=PRICE_FETCH_INTERVAL, id="price_fetch")
    scheduler.add_job(lambda: fetch_history_data(30), "interval", hours=HISTORY_FETCH_HOURS, id="history_fetch")
    scheduler.add_job(run_autonomous_scan, "interval", minutes=AUTO_SCAN_INTERVAL, id="autonomous_scan")
    scheduler.add_job(send_daily_digest, "cron", hour=DIGEST_HOUR, minute=0, id="daily_digest")
    scheduler.start()
    logger.info(
        "Scheduler started: prices/%dmin, history/%dhrs, autonomous/%dmin, digest@%02d:00",
        PRICE_FETCH_INTERVAL, HISTORY_FETCH_HOURS, AUTO_SCAN_INTERVAL, DIGEST_HOUR,
    )
