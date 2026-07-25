"""Tests for the forecast engine.

These use synthetic price series with known statistical properties rather than
live market data, so each test asserts that the engine recovers a parameter we
actually control: a series built with 2% daily volatility should be measured at
2% daily volatility, a driftless random walk should forecast a coin flip, and a
strong trend should tilt the probability without ever escaping the designed
bounds.

Run with:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import math
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import forecast_quant as fq  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic data
# ---------------------------------------------------------------------------


def make_bars(n=300, daily_sigma=0.02, daily_drift=0.0, start=100.0, seed=7,
              intraday_steps=24):
    """Generate OHLCV bars from a geometric random walk.

    Total daily variance is split between an overnight gap and an intraday path,
    so the high/low carry genuine range information for the Yang-Zhang estimator
    instead of being painted on afterwards.
    """
    from datetime import date, timedelta

    rng = random.Random(seed)
    overnight_var = 0.3 * daily_sigma ** 2
    intraday_var = 0.7 * daily_sigma ** 2
    step_sigma = math.sqrt(intraday_var / intraday_steps)
    overnight_sigma = math.sqrt(overnight_var)

    first_day = date(2020, 1, 1)
    bars = []
    close = start
    for i in range(n):
        prev_close = close
        open_price = prev_close * math.exp(rng.gauss(0, overnight_sigma))
        price = open_price
        high = low = open_price
        for _ in range(intraday_steps):
            price *= math.exp(rng.gauss(daily_drift / intraday_steps, step_sigma))
            high = max(high, price)
            low = min(low, price)
        close = price
        bars.append({
            "date": (first_day + timedelta(days=i)).isoformat(),
            "open": open_price, "high": high, "low": low, "close": close,
            "volume": 1_000_000 + rng.randint(-50_000, 50_000),
        })
    return bars


class StudentTTests(unittest.TestCase):
    """The distribution underpinning every probability the engine publishes."""

    def test_cdf_matches_published_critical_values(self):
        # Standard t-table values for 4 degrees of freedom.
        for p, expected in [(0.95, 2.131847), (0.975, 2.776445), (0.99, 3.746947)]:
            self.assertAlmostEqual(fq.student_t_ppf(p, 4.0), expected, places=5)

    def test_cdf_is_symmetric(self):
        for t in (0.25, 1.0, 2.5, 6.0):
            self.assertAlmostEqual(
                fq.student_t_cdf(t) + fq.student_t_cdf(-t), 1.0, places=9
            )

    def test_median_is_zero(self):
        self.assertAlmostEqual(fq.student_t_cdf(0.0), 0.5, places=12)

    def test_converges_to_normal_at_high_dof(self):
        self.assertAlmostEqual(fq.student_t_ppf(0.975, 1e6), 1.959964, places=4)

    def test_scale_produces_requested_standard_deviation(self):
        sigma = 0.023
        scale = fq.t_scale_for_sigma(sigma, 4.0)
        # Var(scale * t(4)) = scale^2 * dof/(dof-2)
        self.assertAlmostEqual(scale * math.sqrt(4.0 / 2.0), sigma, places=12)

    def test_fat_tails_exceed_gaussian(self):
        # A 3-sigma move should be materially more likely under t(4).
        t_tail = 1.0 - fq.student_t_cdf(3.0)
        gaussian_tail = 1.0 - fq.student_t_cdf(3.0, 1e6)
        self.assertGreater(t_tail, gaussian_tail * 5)


class VolatilityEstimatorTests(unittest.TestCase):
    """Both estimators must recover a volatility we injected on purpose."""

    def test_yang_zhang_recovers_known_volatility(self):
        for true_sigma in (0.01, 0.02, 0.04):
            bars = make_bars(n=300, daily_sigma=true_sigma, seed=11)
            estimate = fq.yang_zhang_volatility(bars, window=250)
            self.assertIsNotNone(estimate)
            self.assertAlmostEqual(estimate / true_sigma, 1.0, delta=0.20)

    def test_ewma_recovers_known_volatility(self):
        true_sigma = 0.018
        bars = make_bars(n=400, daily_sigma=true_sigma, seed=13)
        closes = [b["close"] for b in bars]
        returns = [math.log(b / a) for a, b in zip(closes, closes[1:])]
        estimate = fq.ewma_volatility(returns)
        self.assertIsNotNone(estimate)
        self.assertAlmostEqual(estimate / true_sigma, 1.0, delta=0.30)

    def test_yang_zhang_returns_none_on_thin_history(self):
        self.assertIsNone(fq.yang_zhang_volatility(make_bars(n=5), window=30))


class QuantForecastTests(unittest.TestCase):
    """End-to-end behaviour of the prior."""

    def test_driftless_random_walk_forecasts_a_coin_flip(self):
        bars = make_bars(n=300, daily_sigma=0.015, daily_drift=0.0, seed=3)
        f = fq.forecast_next_session("TEST", bars)
        self.assertIsNotNone(f)
        self.assertAlmostEqual(f.p_up, 0.5, delta=0.05)

    def test_annualized_volatility_is_reported_correctly(self):
        bars = make_bars(n=300, daily_sigma=0.02, seed=5)
        f = fq.forecast_next_session("TEST", bars)
        expected = 0.02 * math.sqrt(252) * 100
        self.assertAlmostEqual(f.annualized_vol_pct, expected, delta=expected * 0.25)

    def test_probability_never_escapes_designed_bounds(self):
        """The honesty guarantee: no next-session call can claim a huge edge.

        Regardless of how extreme the input series is, the shrunk drift term
        caps how far the probability can travel from a coin flip.
        """
        worst = 0.5
        for seed in range(40):
            for drift in (-0.05, -0.01, 0.0, 0.01, 0.05):
                bars = make_bars(n=200, daily_sigma=0.02, daily_drift=drift, seed=seed)
                f = fq.forecast_next_session("TEST", bars)
                if f is None:
                    continue
                worst = max(worst, abs(f.p_up - 0.5) + 0.5)
                self.assertGreater(f.p_up, 0.40)
                self.assertLess(f.p_up, 0.60)
        # And it should actually use some of that range, or the engine is inert.
        self.assertGreater(worst, 0.51)

    def test_sustained_uptrend_tilts_bullish(self):
        bars = make_bars(n=250, daily_sigma=0.01, daily_drift=0.004, seed=21)
        f = fq.forecast_next_session("TEST", bars)
        self.assertGreater(f.p_up, 0.5)
        self.assertIn(f.direction, ("bull", "doji"))

    def test_sustained_downtrend_tilts_bearish(self):
        bars = make_bars(n=250, daily_sigma=0.01, daily_drift=-0.004, seed=22)
        f = fq.forecast_next_session("TEST", bars)
        self.assertLess(f.p_up, 0.5)
        self.assertIn(f.direction, ("bear", "doji"))

    def test_direction_agrees_with_probability(self):
        for seed in range(25):
            bars = make_bars(n=200, daily_sigma=0.02, seed=seed)
            f = fq.forecast_next_session("TEST", bars)
            if f is None or f.direction == "doji":
                continue
            if f.direction == "bull":
                self.assertGreater(f.p_up, 0.5)
            else:
                self.assertLess(f.p_up, 0.5)

    def test_doji_conviction_is_capped(self):
        for seed in range(25):
            bars = make_bars(n=200, daily_sigma=0.02, seed=seed)
            f = fq.forecast_next_session("TEST", bars)
            if f and f.direction == "doji":
                self.assertLessEqual(f.conviction, 35)

    def test_bands_are_ordered_and_positive(self):
        f = fq.forecast_next_session("TEST", make_bars(n=250, seed=9))
        self.assertGreater(f.band_68_pct, 0)
        self.assertGreater(f.band_95_pct, f.band_68_pct)

    def test_returns_none_without_enough_history(self):
        self.assertIsNone(fq.forecast_next_session("TEST", make_bars(n=20)))
        self.assertIsNone(fq.forecast_next_session("TEST", []))

    def test_survives_degenerate_bars(self):
        """Flat and zero-priced bars must not crash the estimator."""
        bars = make_bars(n=200, seed=4)
        for bar in bars[50:60]:
            bar["high"] = bar["low"] = bar["open"] = bar["close"]
        bars[70]["close"] = 0.0
        f = fq.forecast_next_session("TEST", bars)
        self.assertIsNotNone(f)
        self.assertTrue(0.0 < f.p_up < 1.0)

    def test_higher_volatility_widens_the_expected_range(self):
        calm = fq.forecast_next_session("A", make_bars(n=250, daily_sigma=0.008, seed=31))
        wild = fq.forecast_next_session("B", make_bars(n=250, daily_sigma=0.045, seed=31))
        self.assertGreater(wild.sigma_pct, calm.sigma_pct * 3)


class BlendTests(unittest.TestCase):
    """The catalyst overlay may tilt the prior, never overwrite it."""

    def setUp(self):
        from app import forecast_engine
        from app.forecast_catalyst import CatalystTilt
        self.engine = forecast_engine
        self.Tilt = CatalystTilt
        self.prior = fq.forecast_next_session("TEST", make_bars(n=250, seed=17))

    def test_no_tilt_leaves_the_prior_untouched(self):
        blended = self.engine._blend(self.prior, None)
        self.assertAlmostEqual(blended["p_up"], self.prior.p_up, places=4)
        self.assertAlmostEqual(blended["sigma_pct"], self.prior.sigma_pct, places=3)

    def test_positive_shift_raises_probability(self):
        tilt = self.Tilt("TEST", logit_shift=0.4, vol_multiplier=1.0, rationale="")
        self.assertGreater(self.engine._blend(self.prior, tilt)["p_up"], self.prior.p_up)

    def test_negative_shift_lowers_probability(self):
        tilt = self.Tilt("TEST", logit_shift=-0.4, vol_multiplier=1.0, rationale="")
        self.assertLess(self.engine._blend(self.prior, tilt)["p_up"], self.prior.p_up)

    def test_maximum_tilt_stays_bounded(self):
        tilt = self.Tilt("TEST", logit_shift=0.6, vol_multiplier=1.0, rationale="")
        self.assertLess(self.engine._blend(self.prior, tilt)["p_up"], 0.70)

    def test_volatility_multiplier_widens_range(self):
        tilt = self.Tilt("TEST", logit_shift=0.0, vol_multiplier=1.8, rationale="")
        blended = self.engine._blend(self.prior, tilt)
        self.assertAlmostEqual(blended["sigma_pct"], self.prior.sigma_pct * 1.8, places=2)

    def test_expected_move_stays_consistent_with_probability(self):
        """A row must never say 'bullish' while its expected move is negative."""
        for shift in (-0.6, -0.3, 0.0, 0.3, 0.6):
            tilt = self.Tilt("TEST", logit_shift=shift, vol_multiplier=1.0, rationale="")
            blended = self.engine._blend(self.prior, tilt)
            if blended["p_up"] > 0.5:
                self.assertGreater(blended["expected_move_pct"], 0)
            elif blended["p_up"] < 0.5:
                self.assertLess(blended["expected_move_pct"], 0)
            if blended["direction"] == "bull":
                self.assertGreater(blended["expected_move_pct"], 0)
            elif blended["direction"] == "bear":
                self.assertLess(blended["expected_move_pct"], 0)

    def test_event_volatility_does_not_inflate_conviction(self):
        calm = self.Tilt("TEST", logit_shift=0.3, vol_multiplier=1.0, rationale="")
        event = self.Tilt("TEST", logit_shift=0.3, vol_multiplier=1.8, rationale="")
        self.assertLess(
            self.engine._blend(self.prior, event)["conviction"],
            self.engine._blend(self.prior, calm)["conviction"],
        )


class ClampTests(unittest.TestCase):
    """Model-supplied numbers are never trusted raw."""

    def setUp(self):
        from app.forecast_catalyst import _clamp
        self.clamp = _clamp

    def test_out_of_range_values_are_clamped(self):
        self.assertEqual(self.clamp(99.0, -0.6, 0.6, 0.0), 0.6)
        self.assertEqual(self.clamp(-99.0, -0.6, 0.6, 0.0), -0.6)

    def test_garbage_falls_back_to_default(self):
        for bad in (None, "abc", [], {}, float("nan")):
            self.assertEqual(self.clamp(bad, -0.6, 0.6, 0.0), 0.0)

    def test_valid_values_pass_through(self):
        self.assertAlmostEqual(self.clamp(0.25, -0.6, 0.6, 0.0), 0.25)
        self.assertAlmostEqual(self.clamp("0.25", -0.6, 0.6, 0.0), 0.25)


class TickerParsingTests(unittest.TestCase):
    """User input reaches yfinance, so it gets sanitized first."""

    def setUp(self):
        from app.forecast_engine import parse_tickers
        self.parse = parse_tickers

    def test_splits_on_commas_and_whitespace(self):
        self.assertEqual(self.parse("lmt, xom  crwd"), ["LMT", "XOM", "CRWD"])

    def test_deduplicates_preserving_order(self):
        self.assertEqual(self.parse("SPY spy SPY qqq"), ["SPY", "QQQ"])

    def test_rejects_injection_and_junk(self):
        # Anything carrying path separators, semicolons or markup is dropped;
        # plain alphabetic words are syntactically valid symbols and pass
        # through (yfinance simply finds nothing for them).
        self.assertEqual(self.parse("../../etc/passwd;"), [])
        self.assertEqual(self.parse("<script>alert(1)</script>"), [])
        self.assertEqual(self.parse("SPY'; DROP--"), [])

    def test_allows_real_symbol_punctuation(self):
        self.assertEqual(self.parse("BRK-B ^VIX BP.L"), ["BRK-B", "^VIX", "BP.L"])

    def test_caps_the_list(self):
        self.assertEqual(len(self.parse(" ".join(f"T{i}" for i in range(50)))), 12)

    def test_handles_empty_input(self):
        self.assertEqual(self.parse(""), [])
        self.assertEqual(self.parse(None), [])


class LedgerTests(unittest.TestCase):
    """Record, resolve, score."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        from app import models
        self.models = models
        self._original_path = models.DB_PATH
        models.DB_PATH = Path(self.tmp.name)
        models.init_db()
        from app import forecast_ledger
        self.ledger = forecast_ledger

    def tearDown(self):
        self.models.DB_PATH = self._original_path
        os.unlink(self.tmp.name)

    def _forecast(self, ticker, asof, direction, p_up, close=100.0):
        return {
            "ticker": ticker, "asof_date": asof, "direction": direction,
            "p_up": p_up, "expected_move_pct": 0.1, "sigma_pct": 1.5,
            "conviction": 70, "source": "quant", "ref_close": close,
            "rationale": "test",
        }

    def test_records_and_reads_back(self):
        self.ledger.record_forecasts([self._forecast("AAA", "2024-01-02", "bull", 0.55)])
        pending = self.ledger.pending_forecasts()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["ticker"], "AAA")

    def test_rescan_updates_rather_than_duplicates(self):
        self.ledger.record_forecasts([self._forecast("AAA", "2024-01-02", "bull", 0.55)])
        self.ledger.record_forecasts([self._forecast("AAA", "2024-01-02", "bear", 0.45)])
        pending = self.ledger.pending_forecasts()
        self.assertEqual(len(pending), 1)
        self.assertAlmostEqual(pending[0]["p_up"], 0.45)

    def test_resolution_scores_a_correct_call(self):
        self.ledger.record_forecasts(
            [self._forecast("AAA", "2024-01-02", "bull", 0.60, close=100.0)]
        )
        bars = {"AAA": [{"date": "2024-01-03", "close": 102.0}]}
        self.assertEqual(self.ledger.resolve_forecasts(bars), 1)

        resolved = self.ledger.recent_resolved()[0]
        self.assertEqual(resolved["outcome"], 1)
        self.assertAlmostEqual(resolved["realized_return_pct"], 2.0, places=4)
        # Brier = (0.60 - 1)^2 = 0.16
        self.assertAlmostEqual(resolved["brier"], 0.16, places=5)

    def test_resolution_scores_an_incorrect_call(self):
        self.ledger.record_forecasts(
            [self._forecast("BBB", "2024-01-02", "bull", 0.60, close=100.0)]
        )
        self.ledger.resolve_forecasts({"BBB": [{"date": "2024-01-03", "close": 98.0}]})
        resolved = self.ledger.recent_resolved()[0]
        self.assertEqual(resolved["outcome"], 0)
        # Brier = (0.60 - 0)^2 = 0.36
        self.assertAlmostEqual(resolved["brier"], 0.36, places=5)

    def test_resolved_rows_are_immutable(self):
        """Rewriting a forecast after the outcome is known would be cheating."""
        self.ledger.record_forecasts(
            [self._forecast("CCC", "2024-01-02", "bull", 0.60, close=100.0)]
        )
        self.ledger.resolve_forecasts({"CCC": [{"date": "2024-01-03", "close": 105.0}]})
        self.ledger.record_forecasts(
            [self._forecast("CCC", "2024-01-02", "bull", 0.99, close=100.0)]
        )
        self.assertAlmostEqual(self.ledger.recent_resolved()[0]["p_up"], 0.60)

    def test_forecast_stays_pending_without_a_later_session(self):
        self.ledger.record_forecasts([self._forecast("DDD", "2024-01-02", "bull", 0.55)])
        # Only same-day and earlier bars available: nothing to resolve against.
        self.ledger.resolve_forecasts({"DDD": [{"date": "2024-01-02", "close": 101.0}]})
        self.assertEqual(len(self.ledger.pending_forecasts()), 1)

    def test_scorecard_reports_no_data_before_resolution(self):
        self.assertEqual(self.ledger.scorecard()["resolved"], 0)

    def test_scorecard_aggregates_known_outcomes(self):
        from datetime import datetime, timedelta
        today = datetime.now()
        rows, bars = [], {}
        # Six forecasts at p=0.6; four resolve up, two resolve down.
        for i, up in enumerate([True, True, True, True, False, False]):
            ticker = f"T{i}"
            asof = (today - timedelta(days=10)).strftime("%Y-%m-%d")
            target = (today - timedelta(days=9)).strftime("%Y-%m-%d")
            rows.append(self._forecast(ticker, asof, "bull", 0.60, close=100.0))
            bars[ticker] = [{"date": target, "close": 103.0 if up else 97.0}]
        self.ledger.record_forecasts(rows)
        self.ledger.resolve_forecasts(bars)

        card = self.ledger.scorecard(days=30)
        self.assertEqual(card["resolved"], 6)
        self.assertAlmostEqual(card["hit_rate"], 4 / 6, places=4)
        self.assertAlmostEqual(card["realized_up_rate"], 4 / 6, places=4)
        # Brier = (4*(0.4)^2 + 2*(0.6)^2) / 6; the scorecard rounds to 4 places.
        self.assertAlmostEqual(card["brier"], (4 * 0.16 + 2 * 0.36) / 6, places=3)
        # Skill vs the 0.5 baseline (0.25); both fields are rounded for display,
        # so compare with a tolerance that absorbs the rounding.
        self.assertAlmostEqual(
            card["brier_skill_score"], 1 - card["brier"] / 0.25, delta=0.005
        )
        self.assertGreater(card["brier_skill_score"], 0)

    def test_perfect_and_useless_forecasters_score_as_expected(self):
        from datetime import datetime, timedelta
        asof = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        target = (datetime.now() - timedelta(days=4)).strftime("%Y-%m-%d")

        rows, bars = [], {}
        for i in range(4):
            ticker = f"P{i}"
            rows.append(self._forecast(ticker, asof, "bull", 0.999, close=100.0))
            bars[ticker] = [{"date": target, "close": 101.0}]
        self.ledger.record_forecasts(rows)
        self.ledger.resolve_forecasts(bars)

        card = self.ledger.scorecard(days=30)
        self.assertAlmostEqual(card["hit_rate"], 1.0)
        self.assertLess(card["brier"], 0.001)
        self.assertGreater(card["brier_skill_score"], 0.99)


if __name__ == "__main__":
    unittest.main(verbosity=2)
