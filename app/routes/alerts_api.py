"""Alert configuration routes."""

from flask import Blueprint, jsonify, render_template, request

from app.alerts import send_telegram
from app.models import query_db, execute_db, get_db

bp = Blueprint("alerts_api", __name__)


@bp.route("/alerts")
def alerts_page():
    return render_template("alerts.html")


@bp.route("/api/alerts")
def api_alerts():
    rules = query_db("SELECT * FROM alert_rules ORDER BY id DESC")
    history = query_db(
        "SELECT * FROM alert_history ORDER BY triggered_at DESC LIMIT 50"
    )
    return jsonify({"rules": rules, "history": history})


@bp.route("/api/alerts", methods=["POST"])
def create_alert():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    required = ("ticker", "condition", "threshold")
    if not all(data.get(k) for k in required):
        return jsonify({"error": "ticker, condition, and threshold are required"}), 400

    valid_conditions = ("above", "below", "change_pct_above", "volume_spike")
    if data["condition"] not in valid_conditions:
        return jsonify({"error": f"condition must be one of {valid_conditions}"}), 400

    try:
        threshold = float(data["threshold"])
    except (ValueError, TypeError):
        return jsonify({"error": "threshold must be a number"}), 400

    row_id = execute_db(
        "INSERT INTO alert_rules (ticker, condition, threshold) VALUES (?, ?, ?)",
        (data["ticker"].upper(), data["condition"], threshold)
    )
    return jsonify({"id": row_id, "status": "created"}), 201


@bp.route("/api/alerts/<int:rule_id>", methods=["DELETE"])
def delete_alert(rule_id):
    with get_db() as db:
        db.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
    return jsonify({"status": "deleted"})


@bp.route("/api/alerts/<int:rule_id>/toggle", methods=["POST"])
def toggle_alert(rule_id):
    with get_db() as db:
        db.execute(
            "UPDATE alert_rules SET enabled = CASE WHEN enabled = 1 THEN 0 ELSE 1 END WHERE id = ?",
            (rule_id,)
        )
    return jsonify({"status": "toggled"})


@bp.route("/api/alerts/test-telegram", methods=["POST"])
def test_telegram():
    ok = send_telegram("Test alert from Iran Investment Tracker")
    if ok:
        return jsonify({"status": "sent"})
    return jsonify({"error": "Failed. Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars"}), 400
