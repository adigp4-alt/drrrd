"""Tests for the dual SQLite/Postgres storage backend.

The whole app funnels its SQL through three helpers in :mod:`app.models`, so
these tests exercise those helpers directly and assert the two backends behave
identically — the same schema, the same placeholder style, the same return
values from :func:`execute_db`, and the same upsert semantics that the forecast
ledger depends on.

The Postgres tests are skipped unless a server is reachable. Set
``TEST_DATABASE_URL`` to run them; CI without Postgres still runs the SQLite half.

Run with:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, models  # noqa: E402


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


def postgres_available() -> bool:
    if not TEST_DATABASE_URL:
        return False
    try:
        import psycopg
        with psycopg.connect(TEST_DATABASE_URL, connect_timeout=3):
            return True
    except Exception:
        return False


class PlaceholderTranslationTests(unittest.TestCase):
    """SQLite-style ``?`` must become ``%s`` for Postgres — but not inside strings."""

    def test_sqlite_is_left_alone(self):
        sql = "SELECT * FROM t WHERE a = ? AND b = ?"
        self.assertEqual(models._translate(sql, models.SQLITE), sql)

    def test_postgres_placeholders_are_rewritten(self):
        self.assertEqual(
            models._translate("SELECT * FROM t WHERE a = ? AND b = ?", models.POSTGRES),
            "SELECT * FROM t WHERE a = %s AND b = %s",
        )

    def test_question_marks_inside_literals_survive(self):
        sql = "SELECT * FROM t WHERE label = 'why?' AND a = ?"
        self.assertEqual(
            models._translate(sql, models.POSTGRES),
            "SELECT * FROM t WHERE label = 'why?' AND a = %s",
        )

    def test_double_quoted_literals_survive(self):
        sql = 'SELECT * FROM t WHERE tag = "a?b" AND id = ?'
        self.assertEqual(
            models._translate(sql, models.POSTGRES),
            'SELECT * FROM t WHERE tag = "a?b" AND id = %s',
        )

    def test_statement_without_placeholders_is_unchanged(self):
        sql = "SELECT count(*) FROM forecasts"
        self.assertEqual(models._translate(sql, models.POSTGRES), sql)


class InsertDetectionTests(unittest.TestCase):
    """Only plain INSERTs get a RETURNING clause appended."""

    def test_plain_insert_detected(self):
        self.assertTrue(models._is_plain_insert("INSERT INTO t (a) VALUES (?)"))
        self.assertTrue(models._is_plain_insert("  insert into t (a) values (?)  "))

    def test_insert_with_returning_is_left_alone(self):
        self.assertFalse(
            models._is_plain_insert("INSERT INTO t (a) VALUES (?) RETURNING id")
        )

    def test_non_inserts_are_not_touched(self):
        self.assertFalse(models._is_plain_insert("UPDATE t SET a = ?"))
        self.assertFalse(models._is_plain_insert("DELETE FROM t WHERE id = ?"))
        self.assertFalse(models._is_plain_insert("SELECT * FROM t"))


class _BackendContractMixin:
    """The behaviour both backends must share, run once against each."""

    def test_schema_creates_every_table(self):
        for table in ("holdings", "watchlist", "alert_rules", "alert_history",
                      "forecasts"):
            rows = models.query_db(f"SELECT * FROM {table}")
            self.assertEqual(rows, [], f"{table} should exist and start empty")

    def test_init_db_is_idempotent(self):
        models.init_db()
        models.init_db()
        self.assertEqual(models.query_db("SELECT * FROM holdings"), [])

    def test_execute_db_returns_new_row_id(self):
        new_id = models.execute_db(
            "INSERT INTO holdings (ticker, shares, buy_price) VALUES (?, ?, ?)",
            ("AAPL", 10.0, 150.0),
        )
        self.assertIsInstance(new_id, int)
        self.assertGreater(new_id, 0)

    def test_round_trip_read_write(self):
        models.execute_db(
            "INSERT INTO holdings (ticker, shares, buy_price) VALUES (?, ?, ?)",
            ("MSFT", 5.0, 300.0),
        )
        row = models.query_db(
            "SELECT * FROM holdings WHERE ticker = ?", ("MSFT",), one=True
        )
        self.assertIsInstance(row, dict)
        self.assertEqual(row["ticker"], "MSFT")
        self.assertAlmostEqual(row["shares"], 5.0)

    def test_query_db_one_returns_none_when_missing(self):
        self.assertIsNone(
            models.query_db("SELECT * FROM holdings WHERE ticker = ?", ("NOPE",),
                            one=True)
        )

    def test_update_and_delete(self):
        models.execute_db(
            "INSERT INTO watchlist (ticker, notes) VALUES (?, ?)", ("TSLA", "watch")
        )
        models.execute_db(
            "UPDATE watchlist SET notes = ? WHERE ticker = ?", ("updated", "TSLA")
        )
        row = models.query_db(
            "SELECT notes FROM watchlist WHERE ticker = ?", ("TSLA",), one=True
        )
        self.assertEqual(row["notes"], "updated")

        models.execute_db("DELETE FROM watchlist WHERE ticker = ?", ("TSLA",))
        self.assertEqual(models.query_db("SELECT * FROM watchlist"), [])

    def test_created_at_default_is_populated(self):
        """The TEXT/CURRENT_TIMESTAMP default needs a cast on Postgres."""
        models.execute_db(
            "INSERT INTO holdings (ticker, shares, buy_price) VALUES (?, ?, ?)",
            ("NVDA", 1.0, 100.0),
        )
        row = models.query_db(
            "SELECT created_at FROM holdings WHERE ticker = ?", ("NVDA",), one=True
        )
        self.assertTrue(row["created_at"], "created_at default should be set")

    def test_forecast_upsert_semantics(self):
        """The ledger's ON CONFLICT ... WHERE resolved_at IS NULL must work on both."""
        from app import forecast_ledger

        row = {
            "ticker": "AAA", "asof_date": "2024-01-02", "direction": "bull",
            "p_up": 0.55, "expected_move_pct": 0.1, "sigma_pct": 1.5,
            "conviction": 70, "source": "quant", "ref_close": 100.0,
            "rationale": "first",
        }
        forecast_ledger.record_forecasts([row])
        forecast_ledger.record_forecasts([{**row, "p_up": 0.45, "rationale": "second"}])

        pending = forecast_ledger.pending_forecasts()
        self.assertEqual(len(pending), 1, "upsert must not duplicate the row")
        self.assertAlmostEqual(pending[0]["p_up"], 0.45)

        # Once resolved, the row is frozen against further rewrites.
        forecast_ledger.resolve_forecasts(
            {"AAA": [{"date": "2024-01-03", "close": 102.0}]}
        )
        forecast_ledger.record_forecasts([{**row, "p_up": 0.99}])
        resolved = forecast_ledger.recent_resolved()[0]
        self.assertAlmostEqual(resolved["p_up"], 0.45)
        self.assertEqual(resolved["outcome"], 1)

    def test_scorecard_runs_against_the_backend(self):
        from app import forecast_ledger
        from datetime import datetime, timedelta

        asof = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        target = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        forecast_ledger.record_forecasts([{
            "ticker": "BBB", "asof_date": asof, "direction": "bull", "p_up": 0.60,
            "expected_move_pct": 0.2, "sigma_pct": 1.0, "conviction": 65,
            "source": "quant", "ref_close": 50.0, "rationale": "x",
        }])
        forecast_ledger.resolve_forecasts({"BBB": [{"date": target, "close": 51.0}]})

        card = forecast_ledger.scorecard(days=30)
        self.assertEqual(card["resolved"], 1)
        self.assertAlmostEqual(card["brier"], 0.16, places=3)
        self.assertEqual(card["hit_rate"], 1.0)


class SqliteBackendTests(_BackendContractMixin, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self._original_url = config.DATABASE_URL
        self._original_path = config.DB_PATH
        config.DATABASE_URL = ""
        config.DB_PATH = Path(self.tmp.name)
        models.init_db()

    def tearDown(self):
        config.DATABASE_URL = self._original_url
        config.DB_PATH = self._original_path
        os.unlink(self.tmp.name)

    def test_backend_is_sqlite(self):
        self.assertEqual(models.backend(), models.SQLITE)


@unittest.skipUnless(
    postgres_available(),
    "Postgres not reachable; set TEST_DATABASE_URL to run these",
)
class PostgresBackendTests(_BackendContractMixin, unittest.TestCase):
    def setUp(self):
        self._original_url = config.DATABASE_URL
        config.DATABASE_URL = TEST_DATABASE_URL
        # Start from a clean schema so each test sees an empty database.
        with models.get_db() as db:
            for table in ("forecasts", "alert_history", "alert_rules", "watchlist",
                          "holdings"):
                db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        models.init_db()

    def tearDown(self):
        with models.get_db() as db:
            for table in ("forecasts", "alert_history", "alert_rules", "watchlist",
                          "holdings"):
                db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        config.DATABASE_URL = self._original_url

    def test_backend_is_postgres(self):
        self.assertEqual(models.backend(), models.POSTGRES)

    def test_serial_primary_key_autoincrements(self):
        first = models.execute_db(
            "INSERT INTO holdings (ticker, shares, buy_price) VALUES (?, ?, ?)",
            ("A", 1.0, 1.0),
        )
        second = models.execute_db(
            "INSERT INTO holdings (ticker, shares, buy_price) VALUES (?, ?, ?)",
            ("B", 1.0, 1.0),
        )
        self.assertEqual(second, first + 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
