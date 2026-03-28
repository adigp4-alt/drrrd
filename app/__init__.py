"""Flask application factory."""

import os
import threading

from flask import Flask

from app.extensions import socketio
from app.models import init_db
from app.data_fetcher import fetch_prices, fetch_history_data
from app.scheduler import start_scheduler
from app.alerts import check_alerts
from app.data_fetcher import CACHE


def create_app():
    app = Flask(__name__, template_folder="../templates")

    # Initialize SocketIO (must happen before blueprints use it)
    socketio.init_app(app, cors_allowed_origins="*", async_mode="eventlet")

    # Initialize database
    init_db()

    # Register blueprints
    from app.routes import (
        dashboard, portfolio, analysis, alerts_api,
        watchlist, export, screener, backtest, stat_arb,
        remote_api,
    )
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(portfolio.bp)
    app.register_blueprint(analysis.bp)
    app.register_blueprint(alerts_api.bp)
    app.register_blueprint(watchlist.bp)
    app.register_blueprint(export.bp)
    app.register_blueprint(screener.bp)
    app.register_blueprint(backtest.bp)
    app.register_blueprint(stat_arb.bp)
    app.register_blueprint(remote_api.bp)

    # Startup: fetch data and start scheduler
    def _startup():
        fetch_prices()
        check_alerts(CACHE.get("data", {}))
        fetch_history_data(30)
        start_scheduler()

    threading.Thread(target=_startup, daemon=True).start()

    # Start Telegram bot if token is configured
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        from app.telegram_bot import start_bot
        start_bot()

    return app
