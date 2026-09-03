"""Agent Desk UI and JSON endpoints."""

import hmac
import os

from flask import Blueprint, jsonify, render_template, request

from app import trading_agent

bp = Blueprint("agent", __name__, url_prefix="/agent")


@bp.get("")
def index():
    ready = trading_agent.is_configured() and bool(os.environ.get("AGENT_RUN_TOKEN"))
    return render_template("agent.html", configured=ready)


@bp.get("/api/runs")
def api_runs():
    return jsonify({"runs": trading_agent.recent_runs()})


@bp.post("/api/run")
def api_run():
    dry_run = bool((request.get_json(silent=True) or {}).get("dry_run", False))
    expected = os.environ.get("AGENT_RUN_TOKEN", "")
    supplied = request.headers.get("X-Agent-Token", "")
    if not expected or not hmac.compare_digest(supplied, expected):
        return jsonify({"error": "valid Agent Desk run token required"}), 401
    try:
        run = trading_agent.run_sync(execute=not dry_run)
        return jsonify(run), 200 if run["status"] != "error" else 500
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
