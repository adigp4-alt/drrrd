"""Flask application factory."""

import os
import threading

from flask import Flask, jsonify

from app.extensions import socketio
from app.models import init_db
from app.data_fetcher import fetch_prices, fetch_history_data
from app.scheduler import start_scheduler
from app.alerts import check_alerts
from app.data_fetcher import CACHE


def create_app():
    app = Flask(__name__, template_folder="../templates")

    # Threading mode: WebSocket via simple-websocket, and the asyncio Discord
    # bot can safely run in its own thread (asyncio is incompatible with
    # eventlet monkey-patching, so eventlet must not be used here).
    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")

    # Initialize database
    init_db()

    # Start Discord bot in its own thread (asyncio event loop)
    if os.environ.get("DISCORD_BOT_TOKEN"):
        from app.discord_bot import start_bot
        start_bot()

    # Register blueprints
    from app.routes import (
        dashboard, portfolio, analysis, alerts_api,
        watchlist, export, screener, backtest, stat_arb,
        remote_api, news, history, risk, tools, autonomous,
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
    app.register_blueprint(news.bp)
    app.register_blueprint(history.bp)
    app.register_blueprint(risk.bp)
    app.register_blueprint(tools.bp)
    app.register_blueprint(autonomous.bp)

    @app.route("/health")
    def health_check():
        return jsonify({"status": "ok", "last_updated": CACHE.get("last_updated")})

    @app.after_request
    def set_security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    # Startup: fetch data and start scheduler.
    # SKIP_STARTUP_FETCH lets tests and tooling import the app without
    # spawning network-fetching background threads.
    if not os.environ.get("SKIP_STARTUP_FETCH"):
        def _startup():
            fetch_prices()
            check_alerts(CACHE.get("data", {}))
            fetch_history_data(30)
            start_scheduler()

        threading.Thread(target=_startup, daemon=True).start()

    return app
