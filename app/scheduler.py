"""Background scheduler for periodic data fetching."""

from apscheduler.schedulers.background import BackgroundScheduler

from app.data_fetcher import fetch_prices, fetch_history_data


def _fetch_and_emit():
    """Fetch prices then push update to all connected WebSocket clients."""
    fetch_prices()
    try:
        from app.extensions import socketio
        from app.data_fetcher import CACHE
        socketio.emit("price_update", {
            "tickers": CACHE["data"],
            "last_updated": CACHE["last_updated"],
            "alerts": CACHE["alerts"],
        })
    except Exception:
        pass  # emit is best-effort; don't crash the scheduler job


def start_scheduler():
    """Auto-fetch every 5 minutes; history every 6 hours."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(_fetch_and_emit, "interval", minutes=5, id="price_fetch")
    scheduler.add_job(lambda: fetch_history_data(30), "interval", hours=6, id="history_fetch")
    from app.tasks.data_collector import run_daily_ai_collection

    scheduler.add_job(run_daily_ai_collection, "cron", hour=17, minute=0, id="daily_ai_collection")  # Run at 5:00 PM
    scheduler.start()

    # Run the collector once on startup in a separate thread
    # so the database immediately has exportable AI signals.
    import threading
    threading.Thread(target=run_daily_ai_collection, daemon=True).start()
    import logging
    logging.getLogger(__name__).info("Scheduler started: prices every 5 min, history every 6 hrs")
