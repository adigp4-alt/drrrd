"""Tests for parsing yfinance responses across library versions.

yfinance's column layout has changed repeatedly and also depends on `group_by`.
Since 1.x, `multi_level_index` defaults to True, so even a single-ticker
download returns MultiIndex columns — which silently broke the old
"flat frame when there's one ticker" assumption and produced an empty board
with no error at all.

These tests build each response shape yfinance is known to return and assert the
parser copes with all of them, so a future version bump surfaces as a failing
test rather than a blank screen in production.

Run with:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE))

from app.market_data import extract_symbol_frame  # noqa: E402

FIELDS = ["Open", "High", "Low", "Close", "Volume"]
DATES = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])


def _values(seed=1.0):
    return {
        "Open": [100.0 + seed, 101.0 + seed, 102.0 + seed],
        "High": [103.0 + seed, 104.0 + seed, 105.0 + seed],
        "Low": [99.0 + seed, 98.0 + seed, 100.0 + seed],
        "Close": [102.0 + seed, 103.0 + seed, 101.0 + seed],
        "Volume": [1000, 1100, 1200],
    }


def flat_frame():
    """Old single-ticker response: plain columns."""
    return pd.DataFrame(_values(), index=DATES)


def grouped_by_ticker(symbols):
    """group_by='ticker': MultiIndex with the symbol on level 0."""
    data = {}
    for i, sym in enumerate(symbols):
        for field, values in _values(i).items():
            data[(sym, field)] = values
    frame = pd.DataFrame(data, index=DATES)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)
    return frame


def grouped_by_column(symbols):
    """group_by='column': MultiIndex with the symbol on level 1."""
    data = {}
    for i, sym in enumerate(symbols):
        for field, values in _values(i).items():
            data[(field, sym)] = values
    frame = pd.DataFrame(data, index=DATES)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)
    return frame


class ResponseShapeTests(unittest.TestCase):

    def test_flat_single_ticker_frame(self):
        frame = extract_symbol_frame(flat_frame(), "SPY")
        self.assertIsNotNone(frame)
        for field in FIELDS:
            self.assertIn(field, frame.columns)
        self.assertAlmostEqual(float(frame["Close"].iloc[0]), 103.0)

    def test_multi_ticker_grouped_by_ticker(self):
        raw = grouped_by_ticker(["SPY", "LMT"])
        for symbol in ("SPY", "LMT"):
            frame = extract_symbol_frame(raw, symbol)
            self.assertIsNotNone(frame, f"{symbol} should be extractable")
            for field in FIELDS:
                self.assertIn(field, frame.columns)

    def test_multi_ticker_grouped_by_column(self):
        raw = grouped_by_column(["SPY", "LMT"])
        for symbol in ("SPY", "LMT"):
            frame = extract_symbol_frame(raw, symbol)
            self.assertIsNotNone(frame, f"{symbol} should be extractable")
            for field in FIELDS:
                self.assertIn(field, frame.columns)

    def test_single_ticker_multiindex(self):
        """yfinance >= 1.x: one ticker, but still a MultiIndex.

        This is the shape that silently produced an empty board.
        """
        raw = grouped_by_ticker(["SPY"])
        frame = extract_symbol_frame(raw, "SPY")
        self.assertIsNotNone(frame, "single-ticker MultiIndex must parse")
        for field in FIELDS:
            self.assertIn(field, frame.columns)
        self.assertAlmostEqual(float(frame["Close"].iloc[0]), 102.0)

    def test_single_ticker_multiindex_grouped_by_column(self):
        raw = grouped_by_column(["SPY"])
        frame = extract_symbol_frame(raw, "SPY")
        self.assertIsNotNone(frame)
        for field in FIELDS:
            self.assertIn(field, frame.columns)

    def test_values_are_not_crossed_between_tickers(self):
        """Extracting SPY must not return LMT's prices."""
        for builder in (grouped_by_ticker, grouped_by_column):
            raw = builder(["SPY", "LMT"])
            spy = extract_symbol_frame(raw, "SPY")
            lmt = extract_symbol_frame(raw, "LMT")
            # Built with different seeds, so the closes must differ.
            self.assertNotAlmostEqual(
                float(spy["Close"].iloc[0]), float(lmt["Close"].iloc[0]),
                msg=f"{builder.__name__}: ticker frames got crossed",
            )
            self.assertAlmostEqual(float(spy["Close"].iloc[0]), 102.0)
            self.assertAlmostEqual(float(lmt["Close"].iloc[0]), 103.0)

    def test_absent_symbol_returns_none(self):
        self.assertIsNone(extract_symbol_frame(grouped_by_ticker(["SPY"]), "NOPE"))

    def test_empty_and_none_inputs(self):
        self.assertIsNone(extract_symbol_frame(None, "SPY"))
        self.assertIsNone(extract_symbol_frame(pd.DataFrame(), "SPY"))

    def test_frame_without_ohlc_columns_returns_none(self):
        junk = pd.DataFrame({"Foo": [1, 2, 3], "Bar": [4, 5, 6]}, index=DATES)
        self.assertIsNone(extract_symbol_frame(junk, "SPY"))


class EndToEndParsingTests(unittest.TestCase):
    """The full fetch path, with yfinance stubbed to each response shape."""

    def _run_with(self, raw, tickers):
        """Run the fetch path with only the yfinance provider enabled.

        The engine tries Yahoo's chart API first in normal operation; pinning
        the source here keeps these tests about yfinance response *shapes*,
        which is what they exist to cover, and keeps them off the network.
        """
        from unittest import mock
        from app import forecast_engine, market_data

        class FakeYF:
            @staticmethod
            def download(*args, **kwargs):
                return raw

        with mock.patch.object(forecast_engine, "yf", FakeYF), \
             mock.patch.object(market_data, "SOURCE_MODE", "yfinance"):
            return forecast_engine.fetch_bars_with_reasons(tickers, period="5d")

    def test_multi_ticker_ticker_grouped(self):
        bars, reasons = self._run_with(grouped_by_ticker(["SPY", "LMT"]),
                                       ["SPY", "LMT"])
        self.assertEqual(set(bars), {"SPY", "LMT"})
        self.assertEqual(len(bars["SPY"]), 3)
        self.assertEqual(reasons, [])

    def test_single_ticker_multiindex_produces_bars(self):
        """Regression: this shape used to yield an empty board silently."""
        bars, reasons = self._run_with(grouped_by_ticker(["SPY"]), ["SPY"])
        self.assertIn("SPY", bars)
        self.assertEqual(len(bars["SPY"]), 3)
        self.assertEqual(reasons, [])

    def test_bar_fields_are_populated(self):
        bars, _ = self._run_with(grouped_by_ticker(["SPY"]), ["SPY"])
        bar = bars["SPY"][0]
        self.assertEqual(
            set(bar), {"date", "open", "high", "low", "close", "volume"}
        )
        self.assertAlmostEqual(bar["close"], 102.0)
        self.assertEqual(bar["volume"], 1000)
        self.assertEqual(bar["date"], "2024-01-02")

    def test_empty_response_reports_a_reason(self):
        """An empty board must explain itself rather than fail silently."""
        bars, reasons = self._run_with(pd.DataFrame(), ["SPY"])
        self.assertEqual(bars, {})
        self.assertTrue(reasons, "an empty response must produce a reason")
        self.assertIn("diagnostics", reasons[0])

    def test_unparseable_response_reports_a_reason(self):
        """A populated-but-unparseable frame must still name the likely cause.

        This is the signal that distinguishes "upgrade yfinance" from "Yahoo is
        blocking this host" — losing it would put us back to guessing.
        """
        junk = pd.DataFrame({"Foo": [1, 2, 3]}, index=DATES)
        bars, reasons = self._run_with(junk, ["SPY"])
        self.assertEqual(bars, {})
        self.assertTrue(reasons)
        self.assertIn("yfinance version", " ".join(reasons))

    def test_partial_success_reports_only_the_failures(self):
        bars, reasons = self._run_with(grouped_by_ticker(["SPY"]), ["SPY", "MISSING"])
        self.assertIn("SPY", bars)
        self.assertNotIn("MISSING", bars)
        self.assertTrue(any("MISSING" in r for r in reasons))


if __name__ == "__main__":
    unittest.main(verbosity=2)
