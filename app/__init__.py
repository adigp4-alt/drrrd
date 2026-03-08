"""Flask application factory."""

import logging
import os
import threading

from flask import Flask, jsonify

from app.models import init_db
from app.data_fetcher import fetch_prices, fetch_history_data
from app.scheduler import start_scheduler
from app.alerts import check_alerts
from app.data_fetcher import CACHE

logger = logging.getLogger(__name__)

# Resolve template folder as absolute path relative to this file
_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")


def create_app():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = Flask(__name__, template_folder=_TEMPLATE_DIR)

    # Initialize database
    init_db()

    # Register blueprints
    from app.routes import dashboard, portfolio, analysis, alerts_api, watchlist, export
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(portfolio.bp)
    app.register_blueprint(analysis.bp)
    app.register_blueprint(alerts_api.bp)
    app.register_blueprint(watchlist.bp)
    app.register_blueprint(export.bp)

    @app.route("/health")
    def health_check():
        return jsonify({"status": "ok", "last_updated": CACHE.get("last_updated")})

    logger.info("====================================================")
    logger.info("  IRAN INVESTMENT TRACKER — WEB SERVER")
    logger.info("====================================================")

    def _startup():
        fetch_prices()
        check_alerts(CACHE.get("data", {}))
        fetch_history_data(30)
        start_scheduler()

    threading.Thread(target=_startup, daemon=True).start()

    return app
