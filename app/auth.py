"""API key authentication decorator for remote endpoints."""

import hmac
import os
from functools import wraps

from flask import jsonify, request


def require_api_key(f):
    """Protect an endpoint with the REMOTE_API_KEY environment variable."""
    @wraps(f)
    def decorated(*args, **kwargs):
        provided = (
            request.headers.get("X-API-Key")
            or request.args.get("api_key")
        )
        expected = os.environ.get("REMOTE_API_KEY", "")
        if not expected:
            return jsonify({"error": "Remote API not configured"}), 503
        if not provided or not hmac.compare_digest(provided, expected):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated
