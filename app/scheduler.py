"""Background scheduler for periodic data fetching and autonomous strategy."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.data_fetcher import fetch_prices, fetch_history_data
from app.strategy import run_autonomous_scan

logger = logging.getLogger(__name__)


def start_scheduler():
    """Auto-fetch every 5 minutes, history every 6 hours, autonomous scan every 30 minutes."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_prices, "interval", minutes=5, id="price_fetch")
    scheduler.add_job(lambda: fetch_history_data(30), "interval", hours=6, id="history_fetch")
    scheduler.add_job(run_autonomous_scan, "interval", minutes=30, id="autonomous_scan")
    scheduler.start()
    logger.info("Scheduler started: prices/5min, history/6hrs, autonomous/30min")
