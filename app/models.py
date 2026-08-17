"""Database initialization and helpers, over SQLite or Postgres.

The backend is chosen by whether ``DATABASE_URL`` is set:

* **unset** — SQLite at ``DATA_DIR/tracker.db``. Zero setup, but the file lives
  on the container filesystem, so on a host with ephemeral disk (Render's free
  tier, for one) everything resets on redeploy. Mount a volume and point
  ``DATA_DIR`` at it to keep it.
* **set** — Postgres. Durable regardless of the container's disk, which is what
  you want once the forecast ledger's accuracy history is worth keeping.

Every query in the app funnels through :func:`query_db`, :func:`execute_db` and
:func:`get_db`, so the two backends are reconciled in this one module and no
caller has to care which is active. Callers write SQLite-style ``?``
placeholders throughout; they are rewritten to ``%s`` for Postgres here.
"""

import re
import sqlite3
from contextlib import contextmanager

from app import config

POSTGRES = "postgres"
SQLITE = "sqlite"


def backend() -> str:
    """Which database backend is active for this process."""
    return POSTGRES if config.DATABASE_URL else SQLITE


# Schema as individual statements rather than one script: Postgres drivers have
# no `executescript`, and per-statement execution reports errors precisely.
# `{PK}` and `{NOW}` are substituted per backend.
SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS holdings (
        id {PK},
        ticker TEXT NOT NULL,
        shares REAL NOT NULL,
        buy_price REAL NOT NULL,
        buy_date TEXT,
        notes TEXT,
        created_at TEXT DEFAULT {NOW}
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist (
        id {PK},
        ticker TEXT NOT NULL UNIQUE,
        price_target_high REAL,
        price_target_low REAL,
        notes TEXT,
        tags TEXT,
        created_at TEXT DEFAULT {NOW}
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alert_rules (
        id {PK},
        ticker TEXT NOT NULL,
        condition TEXT NOT NULL,
        threshold REAL NOT NULL,
        enabled INTEGER DEFAULT 1,
        last_triggered TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alert_history (
        id {PK},
        rule_id INTEGER,
        ticker TEXT,
        message TEXT,
        triggered_at TEXT DEFAULT {NOW}
    )
    """,
    # Every published forecast, plus its realized outcome once the target
    # session closes. The UNIQUE constraint means re-scanning within a session
    # updates the existing row instead of inflating the sample the scorecard is
    # computed from.
    """
    CREATE TABLE IF NOT EXISTS forecasts (
        id {PK},
        ticker TEXT NOT NULL,
        asof_date TEXT NOT NULL,
        horizon TEXT NOT NULL DEFAULT 'next_session',
        direction TEXT NOT NULL,
        p_up REAL NOT NULL,
        expected_move_pct REAL,
        sigma_pct REAL,
        conviction INTEGER,
        source TEXT,
        catalyst_shift REAL,
        vol_multiplier REAL,
        rationale TEXT,
        ref_close REAL,
        created_at TEXT DEFAULT {NOW},
        target_date TEXT,
        resolved_at TEXT,
        realized_return_pct REAL,
        outcome INTEGER,
        brier REAL,
        log_loss REAL,
        UNIQUE(ticker, asof_date, horizon)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_forecasts_pending ON forecasts(resolved_at, asof_date)",
    "CREATE INDEX IF NOT EXISTS idx_forecasts_scorecard ON forecasts(asof_date, ticker)",
]

_DIALECT = {
    SQLITE: {"PK": "INTEGER PRIMARY KEY", "NOW": "CURRENT_TIMESTAMP"},
    # CURRENT_TIMESTAMP is a timestamptz in Postgres and these columns are TEXT,
    # so the default needs an explicit cast.
    POSTGRES: {"PK": "SERIAL PRIMARY KEY", "NOW": "CURRENT_TIMESTAMP::text"},
}

# Matches a ? that is not inside a single- or double-quoted string literal.
_PLACEHOLDER_RE = re.compile(r"'[^']*'|\"[^\"]*\"|(\?)")


def _translate(sql: str, db_backend: str) -> str:
    """Rewrite SQLite ``?`` placeholders to Postgres ``%s``, sparing literals."""
    if db_backend != POSTGRES:
        return sql

    def swap(match):
        return "%s" if match.group(1) else match.group(0)

    return _PLACEHOLDER_RE.sub(swap, sql)


class _Connection:
    """A uniform execute/commit surface over sqlite3 and psycopg connections."""

    def __init__(self, raw, db_backend: str):
        self._raw = raw
        self.backend = db_backend

    def execute(self, sql, args=()):
        """Execute a statement and return a cursor (`.rowcount`, `.fetchall()`)."""
        statement = _translate(sql, self.backend)
        if self.backend == SQLITE:
            return self._raw.execute(statement, args)
        cursor = self._raw.cursor()
        cursor.execute(statement, args)
        return cursor

    def commit(self):
        self._raw.commit()

    def close(self):
        self._raw.close()


def _connect() -> _Connection:
    db_backend = backend()
    if db_backend == POSTGRES:
        import psycopg
        from psycopg.rows import dict_row

        return _Connection(
            psycopg.connect(config.DATABASE_URL, row_factory=dict_row), POSTGRES
        )
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    return _Connection(conn, SQLITE)


def init_db():
    """Create tables and indexes if they don't already exist."""
    dialect = _DIALECT[backend()]
    with get_db() as db:
        for statement in SCHEMA_STATEMENTS:
            db.execute(statement.format(**dialect))


@contextmanager
def get_db():
    """Context manager yielding a connection, committing on clean exit."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _as_dict(row):
    """Normalize a driver row into a plain dict."""
    return dict(row) if not isinstance(row, dict) else row


def query_db(sql, args=(), one=False):
    """Execute a SELECT and return dicts (or a single dict when ``one``)."""
    with get_db() as db:
        cur = db.execute(sql, args)
        rows = [_as_dict(row) for row in cur.fetchall()]
        return rows[0] if one and rows else rows if not one else None


def execute_db(sql, args=()):
    """Execute an INSERT/UPDATE/DELETE and return the new row id when there is one."""
    with get_db() as db:
        if db.backend == POSTGRES and _is_plain_insert(sql):
            # Postgres has no lastrowid; ask for the id back explicitly.
            cur = db.execute(sql.rstrip().rstrip(";") + " RETURNING id", args)
            row = cur.fetchone()
            return _as_dict(row)["id"] if row else None
        cur = db.execute(sql, args)
        return getattr(cur, "lastrowid", None)


def _is_plain_insert(sql: str) -> bool:
    upper = sql.strip().upper()
    return upper.startswith("INSERT") and "RETURNING" not in upper
