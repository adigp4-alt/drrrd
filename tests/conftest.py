"""Shared pytest fixtures — app is created without background fetch threads."""

import os
import sys

# Must be set before the app package is imported
os.environ["SKIP_STARTUP_FETCH"] = "1"
os.environ.setdefault("REMOTE_API_KEY", "test-key")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app import create_app


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture()
def client(app):
    return app.test_client()
