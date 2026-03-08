"""Background scheduler for periodic data fetching and autonomous strategy."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import PRICE_FETCH_INTERVAL, AUTO_SCAN_INTERVAL, HISTORY_FETCH_HOURS
from app.data_fetcher import fetch_prices, fetch_history_data
from app.strategy import run_autonomous_scan

logger = logging.getLogger(__name__)


def start_scheduler():
    """Start background jobs with configurable intervals."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_prices, "interval", minutes=PRICE_FETCH_INTERVAL, id="price_fetch")
    scheduler.add_job(lambda: fetch_history_data(30), "interval", hours=HISTORY_FETCH_HOURS, id="history_fetch")
    scheduler.add_job(run_autonomous_scan, "interval", minutes=AUTO_SCAN_INTERVAL, id="autonomous_scan")
    scheduler.start()
    logger.info(
        "Scheduler started: prices/%dmin, history/%dhrs, autonomous/%dmin",
        PRICE_FETCH_INTERVAL, HISTORY_FETCH_HOURS, AUTO_SCAN_INTERVAL,
    )
