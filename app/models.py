"""SQLite database initialization and helper functions."""

import sqlite3
from contextlib import contextmanager

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    shares REAL NOT NULL,
    buy_price REAL NOT NULL,
    buy_date TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL UNIQUE,
    price_target_high REAL,
    price_target_low REAL,
    notes TEXT,
    tags TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    condition TEXT NOT NULL,
    threshold REAL NOT NULL,
    enabled INTEGER DEFAULT 1,
    last_triggered TEXT
);

CREATE TABLE IF NOT EXISTS alert_history (
    id INTEGER PRIMARY KEY,
    rule_id INTEGER,
    ticker TEXT,
    message TEXT,
    triggered_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_signal_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    price REAL,
    change_pct REAL,
    bullish_score INTEGER,
    technical_signal TEXT,
    ai_probability REAL,
    ai_regime TEXT,
    prophet_accuracy TEXT,
    nlp_sentiment_score REAL,
    consensus TEXT,
    conviction TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db():
    """Create tables if they don't exist."""
    with get_db() as db:
        db.executescript(SCHEMA)


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def query_db(sql, args=(), one=False):
    """Execute a query and return results as dicts."""
    with get_db() as db:
        cur = db.execute(sql, args)
        rows = [dict(row) for row in cur.fetchall()]
        return rows[0] if one and rows else rows if not one else None


def execute_db(sql, args=()):
    """Execute an INSERT/UPDATE/DELETE and return lastrowid."""
    with get_db() as db:
        cur = db.execute(sql, args)
        return cur.lastrowid
