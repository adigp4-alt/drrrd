"""Tests for the walk-forward backtest.

The headline test here is :meth:`NoLookaheadTests.test_future_bars_cannot_change_a_forecast`.
A backtest that peeks at the future is actively harmful — it manufactures
confidence in a model that has none — so that property is asserted directly by
rewriting history after the forecast date and checking nothing moves.

Run with:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))   # project root, for `app`
sys.path.insert(0, str(_HERE))          # this directory, for sibling test helpers

from app import forecast_backtest as bt  # noqa: E402
from test_forecast import make_bars  # noqa: E402


class NoLookaheadTests(unittest.TestCase):
    """The replay must never see a bar later than the one it forecasts from."""

    def test_future_bars_cannot_change_a_forecast(self):
        """Rewrite everything after the forecast window; forecasts must not move.

        This is the test that makes the backtest trustworthy. The first 200
        sessions are identical between the two runs; the tail is replaced with a
        violent crash in one and a melt-up in the other. Any prediction made in
        the shared prefix that differs between runs would prove the engine is
        reading the future.
        """
        base = make_bars(n=260, daily_sigma=0.015, seed=42)

        crash = [dict(b) for b in base]
        melt_up = [dict(b) for b in base]
        for i in range(200, 260):
            for key in ("open", "high", "low", "close"):
                crash[i][key] = base[i][key] * 0.4
                melt_up[i][key] = base[i][key] * 2.5

        crash_runs = bt.replay_ticker("T", crash, warmup=150)
        melt_runs = bt.replay_ticker("T", melt_up, warmup=150)

        crash_by_date = {p.asof_date: p for p in crash_runs}
        melt_by_date = {p.asof_date: p for p in melt_runs}

        # Forecasts made from the shared prefix (before session 199, so that
        # neither the history nor the predicted bar is in the rewritten tail).
        shared_dates = {b["date"] for b in base[:199]}
        compared = 0
        for date in sorted(shared_dates & crash_by_date.keys() & melt_by_date.keys()):
            a, b = crash_by_date[date], melt_by_date[date]
            self.assertAlmostEqual(
                a.p_up, b.p_up, places=10,
                msg=f"lookahead detected: {date} forecast changed with the future",
            )
            self.assertEqual(a.direction, b.direction)
            self.assertAlmostEqual(a.sigma_pct, b.sigma_pct, places=10)
            compared += 1

        self.assertGreater(compared, 20, "test compared too few forecasts to matter")

    def test_forecast_is_made_strictly_before_its_target(self):
        bars = make_bars(n=200, seed=8)
        for p in bt.replay_ticker("T", bars, warmup=150):
            self.assertLess(p.asof_date, p.target_date)

    def test_realized_return_matches_the_actual_next_session(self):
        bars = make_bars(n=200, seed=9)
        by_date = {b["date"]: b for b in bars}
        for p in bt.replay_ticker("T", bars, warmup=150):
            ref = by_date[p.asof_date]["close"]
            target = by_date[p.target_date]["close"]
            expected = (target - ref) / ref * 100.0
            self.assertAlmostEqual(p.realized_return_pct, expected, places=3)
            self.assertEqual(p.outcome, 1 if expected > 0 else 0)


class ReplayMechanicsTests(unittest.TestCase):

    def test_short_history_produces_nothing(self):
        self.assertEqual(bt.replay_ticker("T", make_bars(n=40), warmup=150), [])
        self.assertEqual(bt.replay_ticker("T", [], warmup=150), [])

    def test_respects_warmup(self):
        bars = make_bars(n=220, seed=3)
        predictions = bt.replay_ticker("T", bars, warmup=150)
        earliest = min(p.asof_date for p in predictions)
        self.assertGreaterEqual(earliest, bars[150]["date"])

    def test_max_sessions_caps_the_replay(self):
        bars = make_bars(n=400, seed=4)
        predictions = bt.replay_ticker("T", bars, warmup=150, max_sessions=30)
        self.assertLessEqual(len(predictions), 31)
        self.assertGreater(len(predictions), 0)

    def test_every_session_after_warmup_is_replayed(self):
        bars = make_bars(n=200, seed=5)
        predictions = bt.replay_ticker("T", bars, warmup=150)
        self.assertEqual(len(predictions), len(bars) - 1 - 150)


class ScoringTests(unittest.TestCase):
    """Metric arithmetic, verified against hand-computed values."""

    def _prediction(self, p_up, outcome, direction="bull", conviction=70):
        return bt.Prediction(
            ticker="T", asof_date="2024-01-01", target_date="2024-01-02",
            direction=direction, p_up=p_up, conviction=conviction,
            expected_move_pct=0.1, sigma_pct=1.0, vol_regime="normal",
            realized_return_pct=1.0 if outcome else -1.0, outcome=outcome,
        )

    def test_brier_arithmetic(self):
        self.assertAlmostEqual(self._prediction(0.6, 1).brier, 0.16, places=9)
        self.assertAlmostEqual(self._prediction(0.6, 0).brier, 0.36, places=9)

    def test_perfect_forecaster_scores_near_zero(self):
        preds = [self._prediction(0.999, 1) for _ in range(10)]
        summary = bt.summarize(preds)
        self.assertLess(summary["brier"], 0.001)
        self.assertGreater(summary["brier_skill_score"], 0.99)
        self.assertEqual(summary["hit_rate"], 1.0)

    def test_coin_flip_forecaster_has_zero_skill(self):
        preds = [self._prediction(0.5, i % 2) for i in range(20)]
        summary = bt.summarize(preds)
        self.assertAlmostEqual(summary["brier"], 0.25, places=9)
        self.assertAlmostEqual(summary["brier_skill_score"], 0.0, places=9)
        self.assertFalse(summary["baselines"]["beats_coin_flip"])

    def test_always_up_baseline_is_computed(self):
        # 7 of 10 sessions up: always-up Brier = 3/10 = 0.3
        preds = [self._prediction(0.5, 1) for _ in range(7)]
        preds += [self._prediction(0.5, 0) for _ in range(3)]
        summary = bt.summarize(preds)
        self.assertAlmostEqual(summary["baselines"]["always_up_brier"], 0.3, places=9)
        self.assertAlmostEqual(summary["baselines"]["always_up_hit_rate"], 0.7, places=9)
        self.assertAlmostEqual(summary["realized_up_rate"], 0.7, places=9)

    def test_dojis_are_excluded_from_hit_rate(self):
        preds = [self._prediction(0.5, 1, direction="doji") for _ in range(5)]
        preds += [self._prediction(0.55, 1, direction="bull") for _ in range(5)]
        summary = bt.summarize(preds)
        self.assertEqual(summary["doji_calls"], 5)
        self.assertEqual(summary["directional_calls"], 5)
        self.assertEqual(summary["hit_rate"], 1.0)

    def test_empty_input_is_reported_not_crashed(self):
        self.assertEqual(bt.summarize([])["predictions"], 0)

    def test_calibration_bins_partition_the_predictions(self):
        preds = [self._prediction(0.44, 0), self._prediction(0.52, 1),
                 self._prediction(0.58, 1)]
        summary = bt.summarize(preds)
        self.assertEqual(sum(b["count"] for b in summary["calibration"]), 3)

    def test_per_ticker_breakdown(self):
        preds = [self._prediction(0.6, 1), self._prediction(0.6, 1)]
        preds[1].ticker = "OTHER"
        rows = bt.summarize(preds)["by_ticker"]
        self.assertEqual({r["ticker"] for r in rows}, {"T", "OTHER"})


class EndToEndTests(unittest.TestCase):

    def test_run_backtest_over_synthetic_tickers(self):
        bars = {
            "AAA": make_bars(n=220, daily_sigma=0.012, seed=1),
            "BBB": make_bars(n=220, daily_sigma=0.020, seed=2),
        }
        summary = bt.run_backtest(["AAA", "BBB", "MISSING"], warmup=150,
                                  bars_by_ticker=bars)
        self.assertEqual(summary["tickers_tested"], 2)
        self.assertEqual(summary["predictions"], 2 * (220 - 1 - 150))
        self.assertEqual(summary["skipped"], [{"ticker": "MISSING",
                                               "reason": "no market data"}])
        self.assertFalse(summary["catalyst_overlay"])
        self.assertIn("brier", summary)

    def test_driftless_series_produces_near_zero_skill(self):
        """On a pure random walk the engine must not appear to have an edge.

        This is the sanity check on the whole exercise: if a driftless series
        produced a big positive skill score, the backtest would be measuring a
        bug rather than a signal.
        """
        bars = {f"T{i}": make_bars(n=320, daily_sigma=0.015, daily_drift=0.0,
                                   seed=100 + i) for i in range(6)}
        summary = bt.run_backtest(list(bars), warmup=150, bars_by_ticker=bars)
        self.assertGreater(summary["predictions"], 500)
        self.assertLess(abs(summary["brier_skill_score"]), 0.05)


if __name__ == "__main__":
    unittest.main(verbosity=2)
