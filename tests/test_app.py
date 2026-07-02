"""Endpoint smoke tests and regression tests for review fixes."""

import threading

from app.data_fetcher import CACHE

PAGES = [
    "/", "/portfolio", "/screener", "/backtest", "/stat-arb", "/analysis",
    "/alerts", "/watchlist", "/correlation", "/reports", "/history",
    "/news", "/risk", "/compare", "/heatmap", "/autonomous",
]


def test_all_pages_render(client):
    for page in PAGES:
        resp = client.get(page)
        assert resp.status_code == 200, f"{page} returned {resp.status_code}"


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_security_headers(client):
    resp = client.get("/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


def test_pwa_assets(client):
    manifest = client.get("/static/manifest.json")
    assert manifest.status_code == 200
    assert manifest.get_json()["display"] == "standalone"
    sw = client.get("/static/sw.js")
    assert sw.status_code == 200
    assert client.get("/static/icon.svg").status_code == 200


def test_api_prices_shape(client):
    data = client.get("/api/prices").get_json()
    for key in ("tickers", "last_updated", "alerts", "copilot_briefing", "tiers", "ticker_order"):
        assert key in data


# ── Remote API auth and validation ──

def test_remote_rejects_missing_key(client):
    assert client.post("/remote/refresh").status_code == 401


def test_remote_rejects_wrong_key(client):
    resp = client.get("/remote/prices", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_remote_unconfigured_returns_503(client, monkeypatch):
    monkeypatch.delenv("REMOTE_API_KEY")
    resp = client.get("/remote/prices", headers={"X-API-Key": "test-key"})
    assert resp.status_code == 503


def test_remote_alert_accepts_zero_threshold(client):
    resp = client.post(
        "/remote/alert",
        json={"ticker": "LMT", "condition": "change_pct_above", "threshold": 0},
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 201


def test_remote_alert_rejects_missing_field(client):
    resp = client.post(
        "/remote/alert",
        json={"ticker": "LMT", "condition": "above"},
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 400


def test_remote_holding_accepts_zero_buy_price(client):
    resp = client.post(
        "/remote/holding",
        json={"ticker": "LMT", "shares": 5, "buy_price": 0},
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 201


def test_remote_holding_rejects_empty_ticker(client):
    resp = client.post(
        "/remote/holding",
        json={"ticker": "", "shares": 5, "buy_price": 10},
        headers={"X-API-Key": "test-key"},
    )
    assert resp.status_code == 400


# ── Compare endpoint date alignment ──

def test_compare_without_history_returns_503(client, monkeypatch):
    monkeypatch.setitem(CACHE, "history", {})
    resp = client.get("/api/compare?tickers=LMT,RTX")
    assert resp.status_code == 503


def test_compare_aligns_series_by_date(client, monkeypatch):
    monkeypatch.setitem(CACHE, "history", {
        "LMT": [
            {"date": "2026-01-01", "close": 100.0},
            {"date": "2026-01-02", "close": 110.0},
            {"date": "2026-01-03", "close": 120.0},
        ],
        # RTX is missing 2026-01-02 — must gap with None, not shift by index
        "RTX": [
            {"date": "2026-01-01", "close": 50.0},
            {"date": "2026-01-03", "close": 55.0},
        ],
    })
    data = client.get("/api/compare?tickers=LMT,RTX").get_json()
    assert data["dates"] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    by_ticker = {s["ticker"]: s for s in data["series"]}
    assert by_ticker["LMT"]["normalized"] == [100.0, 110.0, 120.0]
    assert by_ticker["RTX"]["normalized"] == [100.0, None, 110.0]
    assert by_ticker["RTX"]["change_pct"] == 10.0


def test_compare_requires_tickers_param(client, monkeypatch):
    monkeypatch.setitem(CACHE, "history", {"LMT": [{"date": "2026-01-01", "close": 1.0}]})
    assert client.get("/api/compare").status_code == 400


# ── Autonomous scan lock ──

def test_scan_conflict_while_running(client, monkeypatch):
    from app.routes import autonomous as auto_routes

    release = threading.Event()
    started = threading.Event()

    def slow_scan():
        started.set()
        release.wait(timeout=10)

    monkeypatch.setattr(auto_routes, "run_autonomous_scan", slow_scan)
    try:
        first = client.post("/api/autonomous/scan")
        assert first.status_code == 200
        assert started.wait(timeout=5)
        second = client.post("/api/autonomous/scan")
        assert second.status_code == 409
    finally:
        release.set()
