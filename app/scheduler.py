"""Background scheduler for periodic data fetching."""

from apscheduler.schedulers.background import BackgroundScheduler

from app.data_fetcher import fetch_prices, fetch_history_data


def start_scheduler():
    """Auto-fetch every 5 minutes during market hours."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_prices, "interval", minutes=5, id="price_fetch")
    scheduler.add_job(lambda: fetch_history_data(30), "interval", hours=6, id="history_fetch")
    scheduler.start()
    print("Scheduler started: prices every 5 min, history every 6 hrs")
