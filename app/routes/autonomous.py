"""Autonomous strategy routes — signals, scores, and recommendations."""

import logging
import threading

from flask import Blueprint, jsonify, render_template, request

from app.strategy import AUTO_CACHE, run_autonomous_scan

logger = logging.getLogger(__name__)

bp = Blueprint("autonomous", __name__)


@bp.route("/autonomous")
def autonomous_page():
    return render_template("autonomous.html")


@bp.route("/api/autonomous")
def api_autonomous():
    return jsonify({
        "signals": AUTO_CACHE["signals"],
        "scores": AUTO_CACHE["scores"],
        "rebalance": AUTO_CACHE["rebalance"],
        "recommendations": AUTO_CACHE["recommendations"],
        "last_run": AUTO_CACHE["last_run"],
    })


@bp.route("/api/autonomous/scan", methods=["POST"])
def trigger_scan():
    """Trigger a manual autonomous scan in the background."""
    def _run():
        try:
            run_autonomous_scan()
        except Exception:
            logger.exception("Autonomous scan failed")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "scan_started", "message": "Autonomous scan running in background"})


@bp.route("/api/autonomous/signals")
def api_signals():
    signal_type = None
    type_param = request.args.get("type")
    if type_param and type_param.upper() in ("BUY", "SELL", "WATCH"):
        signal_type = type_param.upper()

    signals = AUTO_CACHE["signals"]
    if signal_type:
        signals = [s for s in signals if s["type"] == signal_type]
    return jsonify({"signals": signals, "last_run": AUTO_CACHE["last_run"]})


@bp.route("/api/autonomous/rebalance")
def api_rebalance():
    return jsonify(AUTO_CACHE["rebalance"])


@bp.route("/api/autonomous/scores")
def api_scores():
    return jsonify({"scores": AUTO_CACHE["scores"], "last_run": AUTO_CACHE["last_run"]})
