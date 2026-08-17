"""Background scheduler for periodic data fetching."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.data_fetcher import fetch_prices, fetch_history_data

logger = logging.getLogger(__name__)


def _resolve_forecasts():
    """Grade any forecast whose target session has closed."""
    try:
        from app.forecast_engine import resolve_outstanding
        resolve_outstanding()
    except Exception as exc:
        logger.error("Scheduled forecast resolution failed: %s", exc)


def start_scheduler():
    """Auto-fetch every 5 minutes during market hours."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_prices, "interval", minutes=5, id="price_fetch")
    scheduler.add_job(lambda: fetch_history_data(30), "interval", hours=6, id="history_fetch")
    # Forecasts can only be graded once the target session has closed, so an
    # hourly sweep resolves each one shortly after its outcome becomes known.
    scheduler.add_job(_resolve_forecasts, "interval", hours=1, id="forecast_resolve")
    scheduler.start()

    logger.info(
        "Scheduler started: prices every 5 min, history every 6 hrs, "
        "forecast scoring hourly"
    )
