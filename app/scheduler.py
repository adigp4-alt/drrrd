"""Background scheduler for periodic data fetching."""

from apscheduler.schedulers.background import BackgroundScheduler

from app.data_fetcher import fetch_prices, fetch_history_data


def start_scheduler():
    """Auto-fetch every 5 minutes during market hours."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_prices, "interval", minutes=5, id="price_fetch")
    from app.tasks.data_collector import run_daily_ai_collection
    
    scheduler.add_job(run_daily_ai_collection, "cron", hour=17, minute=0, id="daily_ai_collection") # Run at 5:00 PM
    scheduler.start()
    
    # For testing/demonstration purposes, run the collector once on startup in a separate thread
    # so the database immediately has exportable AI signals.
    import threading
    threading.Thread(target=run_daily_ai_collection, daemon=True).start()
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Scheduler started: prices every 5 min, history every 6 hrs")
