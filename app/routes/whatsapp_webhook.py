"""WhatsApp Cloud API webhook — message verification and incoming handler."""

import hmac
import logging
import os

from flask import Blueprint, jsonify, request

from app.whatsapp_bot import handle_message, send_whatsapp

logger = logging.getLogger(__name__)

bp = Blueprint("whatsapp", __name__, url_prefix="/whatsapp")


@bp.route("/webhook", methods=["GET"])
def verify():
    """Respond to Meta's webhook verification challenge."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    expected = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
    if mode == "subscribe" and expected and hmac.compare_digest(token or "", expected):
        return challenge, 200
    return "Forbidden", 403


@bp.route("/webhook", methods=["POST"])
def receive():
    """Handle incoming WhatsApp messages."""
    allowed = os.environ.get("WHATSAPP_RECIPIENT", "")
    data = request.get_json(silent=True) or {}

    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    if msg.get("type") != "text":
                        continue
                    sender = msg.get("from", "")
                    text = msg.get("text", {}).get("body", "")
                    if not text:
                        continue
                    # Only respond to the configured recipient number
                    if allowed and sender != allowed:
                        logger.warning("Rejected message from %s", sender)
                        continue
                    reply = handle_message(text, sender)
                    if reply:
                        send_whatsapp(reply, to=sender)
    except Exception as exc:
        logger.error("WhatsApp webhook error: %s", exc)

    # Always return 200 so Meta doesn't retry
    return jsonify({"status": "ok"})
