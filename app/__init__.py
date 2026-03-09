"""Flask application factory."""

import threading

from flask import Flask

from app.models import init_db
from app.data_fetcher import fetch_prices, fetch_history_data
from app.scheduler import start_scheduler
from app.alerts import check_alerts
from app.data_fetcher import CACHE


def create_app():
    app = Flask(__name__, template_folder="../templates")

    # Initialize database
    init_db()

    # Register blueprints
    from app.routes import dashboard, portfolio, analysis, alerts_api, watchlist, export, screener
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(portfolio.bp)
    app.register_blueprint(analysis.bp)
    app.register_blueprint(alerts_api.bp)
    app.register_blueprint(watchlist.bp)
    app.register_blueprint(export.bp)
    app.register_blueprint(screener.bp)

    # Startup: fetch data and start scheduler
    print("\n".join([
        "",
        "====================================================",
        "  IRAN INVESTMENT TRACKER — WEB SERVER",
        "====================================================",
        "",
    ]))

    def _startup():
        fetch_prices()
        # Check custom alerts after fetching prices
        check_alerts(CACHE.get("data", {}))
        fetch_history_data(30)
        start_scheduler()

    threading.Thread(target=_startup, daemon=True).start()

    return app
