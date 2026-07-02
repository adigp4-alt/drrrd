#!/usr/bin/env python3
"""Iran Investment Tracker — Entry Point."""

import eventlet
eventlet.monkey_patch()  # must be first, before any other imports

import os

from app import create_app
from app.extensions import socketio

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
