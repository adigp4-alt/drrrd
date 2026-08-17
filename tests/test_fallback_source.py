"""Tests for the Stooq fallback provider and automatic source failover.

Yahoo Finance throttles and blocks datacenter IP ranges, which is what makes a
cloud-deployed board go blank. Parsing care cannot fix an HTTP 429, so the
engine falls back to a second provider automatically.

The network leg cannot be exercised from a sandbox with no outbound access to
market data, so these tests stub the HTTP call and verify everything around it:
symbol mapping, CSV parsing against real Stooq response formats (including the
malformed ones), failover triggering, and — importantly — that a fallback
failure still produces an explanation rather than silence.

Run with:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE))

from app import market_data  # noqa: E402

STOOQ_CSV = """Date,Open,High,Low,Close,Volume
2024-01-02,472.16,473.67,470.49,472.65,72_000
2024-01-03,470.43,471.19,468.17,468.79,81000
2024-01-04,468.03,469.94,466.11,467.28,90000
"""


class SymbolMappingTests(unittest.TestCase):

    def test_us_equities_get_the_us_suffix(self):
        self.assertEqual(market_data.stooq_symbol("SPY"), "spy.us")
        self.assertEqual(market_data.stooq_symbol("lmt"), "lmt.us")

    def test_share_classes_keep_their_dash(self):
        self.assertEqual(market_data.stooq_symbol("BRK-B"), "brk-b.us")

    def test_index_symbols_keep_the_caret_and_take_no_suffix(self):
        self.assertEqual(market_data.stooq_symbol("^VIX"), "^vix")

    def test_existing_exchange_suffix_is_preserved(self):
        self.assertEqual(market_data.stooq_symbol("BP.L"), "bp.l")

    def test_blank_input(self):
        self.assertEqual(market_data.stooq_symbol(""), "")
        self.assertEqual(market_data.stooq_symbol(None), "")


class CsvParsingTests(unittest.TestCase):

    def test_parses_a_normal_response(self):
        bars = market_data.parse_stooq_csv(STOOQ_CSV)
        self.assertEqual(len(bars), 3)
        self.assertEqual(bars[0]["date"], "2024-01-02")
        self.assertAlmostEqual(bars[0]["close"], 472.65)
        self.assertAlmostEqual(bars[0]["high"], 473.67)
        self.assertEqual(bars[1]["volume"], 81000)

    def test_output_shape_matches_the_engine_contract(self):
        bar = market_data.parse_stooq_csv(STOOQ_CSV)[0]
        self.assertEqual(set(bar), {"date", "open", "high", "low", "close", "volume"})

    def test_rows_are_sorted_chronologically(self):
        shuffled = "\n".join([
            "Date,Open,High,Low,Close,Volume",
            "2024-01-04,468.03,469.94,466.11,467.28,90000",
            "2024-01-02,472.16,473.67,470.49,472.65,72000",
            "2024-01-03,470.43,471.19,468.17,468.79,81000",
        ])
        dates = [b["date"] for b in market_data.parse_stooq_csv(shuffled)]
        self.assertEqual(dates, sorted(dates))

    def test_na_rows_are_skipped_not_fatal(self):
        csv_text = (
            "Date,Open,High,Low,Close,Volume\n"
            "2024-01-02,472.16,473.67,470.49,472.65,72000\n"
            "2024-01-03,N/A,N/A,N/A,N/A,N/A\n"
            "2024-01-04,468.03,469.94,466.11,467.28,90000\n"
        )
        bars = market_data.parse_stooq_csv(csv_text)
        self.assertEqual(len(bars), 2)

    def test_zero_prices_are_rejected(self):
        csv_text = ("Date,Open,High,Low,Close,Volume\n"
                    "2024-01-02,0,0,0,0,0\n")
        self.assertEqual(market_data.parse_stooq_csv(csv_text), [])

    def test_unknown_symbol_response(self):
        self.assertEqual(market_data.parse_stooq_csv("No data"), [])

    def test_html_error_page_is_not_mistaken_for_data(self):
        self.assertEqual(
            market_data.parse_stooq_csv("<html><body>Error</body></html>"), []
        )

    def test_empty_and_header_only_responses(self):
        self.assertEqual(market_data.parse_stooq_csv(""), [])
        self.assertEqual(market_data.parse_stooq_csv("   "), [])
        self.assertEqual(
            market_data.parse_stooq_csv("Date,Open,High,Low,Close,Volume\n"), []
        )

    def test_missing_volume_column_still_parses(self):
        csv_text = ("Date,Open,High,Low,Close\n"
                    "2024-01-02,472.16,473.67,470.49,472.65\n")
        bars = market_data.parse_stooq_csv(csv_text)
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0]["volume"], 0)


class FetchTests(unittest.TestCase):
    """The HTTP leg, with requests stubbed."""

    def _response(self, text, status=200):
        stub = mock.Mock()
        stub.status_code = status
        stub.text = text
        return stub

    def test_successful_fetch(self):
        with mock.patch("requests.get", return_value=self._response(STOOQ_CSV)):
            bars = market_data.fetch_stooq("SPY")
        self.assertEqual(len(bars), 3)

    def test_request_targets_the_mapped_symbol(self):
        with mock.patch("requests.get",
                        return_value=self._response(STOOQ_CSV)) as get:
            market_data.fetch_stooq("BRK-B")
        self.assertEqual(get.call_args.kwargs["params"]["s"], "brk-b.us")

    def test_http_error_returns_empty_not_raise(self):
        with mock.patch("requests.get",
                        return_value=self._response("", status=429)):
            self.assertEqual(market_data.fetch_stooq("SPY"), [])

    def test_network_exception_returns_empty_not_raise(self):
        with mock.patch("requests.get", side_effect=OSError("connection refused")):
            self.assertEqual(market_data.fetch_stooq("SPY"), [])

    def test_fetch_many_collects_only_successes(self):
        def fake_get(url, params=None, **kwargs):
            if params["s"] == "spy.us":
                return self._response(STOOQ_CSV)
            return self._response("No data")

        with mock.patch("requests.get", side_effect=fake_get):
            out = market_data.fetch_stooq_many(["SPY", "BOGUS"])
        self.assertEqual(set(out), {"SPY"})
        self.assertEqual(len(out["SPY"]), 3)

    def test_fetch_many_handles_empty_input(self):
        self.assertEqual(market_data.fetch_stooq_many([]), {})


class FailoverTests(unittest.TestCase):
    """The engine must switch providers on its own when Yahoo yields nothing."""

    def _run(self, yahoo_result, stooq_map, mode="auto"):
        from app import forecast_engine

        class FakeYF:
            @staticmethod
            def download(*args, **kwargs):
                if isinstance(yahoo_result, Exception):
                    raise yahoo_result
                return yahoo_result

        with mock.patch.object(forecast_engine, "yf", FakeYF), \
             mock.patch.object(market_data, "SOURCE_MODE", mode), \
             mock.patch.object(market_data, "fetch_stooq_many",
                               side_effect=lambda t, **k: {
                                   x: stooq_map[x] for x in t if x in stooq_map
                               }):
            return forecast_engine.fetch_bars_with_reasons(["SPY", "LMT"])

    def _bars(self):
        return market_data.parse_stooq_csv(STOOQ_CSV)

    def test_empty_yahoo_response_falls_back(self):
        bars, reasons = self._run(pd.DataFrame(),
                                  {"SPY": self._bars(), "LMT": self._bars()})
        self.assertEqual(set(bars), {"SPY", "LMT"})
        self.assertTrue(any("Stooq" in r for r in reasons))

    def test_yahoo_exception_falls_back(self):
        bars, _ = self._run(OSError("blocked"),
                            {"SPY": self._bars(), "LMT": self._bars()})
        self.assertEqual(set(bars), {"SPY", "LMT"})

    def test_partial_yahoo_data_is_topped_up(self):
        """Yahoo serving only some tickers must not lose the rest."""
        raw = pd.DataFrame(
            {("SPY", f): [1.0, 2.0, 3.0] for f in
             ("Open", "High", "Low", "Close", "Volume")},
            index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
        )
        raw.columns = pd.MultiIndex.from_tuples(raw.columns)
        bars, reasons = self._run(raw, {"LMT": self._bars()})
        self.assertEqual(set(bars), {"SPY", "LMT"})
        self.assertTrue(any("recovered from Stooq" in r for r in reasons))

    def test_both_sources_failing_explains_itself(self):
        """The one thing that must never happen again: silence."""
        bars, reasons = self._run(pd.DataFrame(), {})
        self.assertEqual(bars, {})
        self.assertTrue(reasons)
        self.assertIn("diagnostics", " ".join(reasons))

    def test_yahoo_only_mode_does_not_fall_back(self):
        bars, reasons = self._run(pd.DataFrame(), {"SPY": self._bars()},
                                  mode="yahoo")
        self.assertEqual(bars, {})
        self.assertFalse(any("Stooq" in r for r in reasons))

    def test_stooq_only_mode_skips_yahoo_entirely(self):
        bars, reasons = self._run(
            AssertionError("Yahoo must not be called in stooq mode"),
            {"SPY": self._bars(), "LMT": self._bars()}, mode="stooq",
        )
        self.assertEqual(set(bars), {"SPY", "LMT"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
