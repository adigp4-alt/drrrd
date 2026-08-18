"""Tests for the direct Yahoo chart API provider.

This provider exists because yfinance reaches Yahoo through a cookie/crumb
handshake that Yahoo periodically changes. When that breaks, yfinance returns an
empty frame *and logs the reason rather than raising*, so the board goes blank
with no error anywhere. The chart endpoint needs no crumb, so calling it with
plain ``requests`` removes both that failure mode and yfinance version drift.

The network leg cannot be exercised from a sandbox with no outbound access to
market data, so these tests stub the HTTP call and cover everything around it:
the response format Yahoo actually serves, the malformed and error shapes it
also serves, host failover, and the timezone handling that decides which
calendar day a bar lands on.

Run with:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE))

from app import market_data  # noqa: E402

# 2024-01-02, -03 and -04 at 14:30 UTC — NYSE's 09:30 open in winter.
US_TIMESTAMPS = [1704205800, 1704292200, 1704378600]


def chart_payload(timestamps=None, gmtoffset=-18000, **overrides):
    """Build a response in the shape Yahoo's v8 chart endpoint actually serves."""
    timestamps = US_TIMESTAMPS if timestamps is None else timestamps
    quote = {
        "open": [472.16, 470.43, 468.03],
        "high": [473.67, 471.19, 469.94],
        "low": [470.49, 468.17, 466.11],
        "close": [472.65, 468.79, 467.28],
        "volume": [72000, 81000, 90000],
    }
    quote.update(overrides)
    return {
        "chart": {
            "result": [{
                "meta": {
                    "symbol": "SPY",
                    "gmtoffset": gmtoffset,
                    "exchangeTimezoneName": "America/New_York",
                },
                "timestamp": timestamps,
                "indicators": {"quote": [quote]},
            }],
            "error": None,
        }
    }


class ParsingTests(unittest.TestCase):

    def test_parses_a_normal_response(self):
        bars = market_data.parse_yahoo_chart(chart_payload(), "SPY")
        self.assertEqual(len(bars), 3)
        self.assertAlmostEqual(bars[0]["close"], 472.65)
        self.assertAlmostEqual(bars[0]["high"], 473.67)
        self.assertEqual(bars[1]["volume"], 81000)

    def test_output_shape_matches_the_engine_contract(self):
        """Bars must be interchangeable with the other providers' output."""
        bar = market_data.parse_yahoo_chart(chart_payload(), "SPY")[0]
        self.assertEqual(set(bar), {"date", "open", "high", "low", "close", "volume"})

    def test_accepts_raw_json_text(self):
        """fetch_yahoo_chart hands the parser response.text, not a dict."""
        bars = market_data.parse_yahoo_chart(json.dumps(chart_payload()), "SPY")
        self.assertEqual(len(bars), 3)

    def test_dates_use_the_exchange_calendar_not_utc(self):
        bars = market_data.parse_yahoo_chart(chart_payload(), "SPY")
        self.assertEqual([b["date"] for b in bars],
                         ["2024-01-02", "2024-01-03", "2024-01-04"])

    def test_a_market_ahead_of_utc_lands_on_the_right_day(self):
        """Sydney opens at 10:00 AEDT — 23:00 UTC the *previous* day.

        Ignoring meta.gmtoffset would date every one of these bars a day early.
        """
        bars = market_data.parse_yahoo_chart(
            chart_payload(timestamps=[1704063600], gmtoffset=39600), "^AXJO")
        self.assertEqual(bars[0]["date"], "2024-01-01")

    def test_null_prices_are_skipped_not_fatal(self):
        """Yahoo writes nulls for sessions it has no print for."""
        bars = market_data.parse_yahoo_chart(
            chart_payload(close=[472.65, None, 467.28]), "SPY")
        self.assertEqual(len(bars), 2)
        self.assertEqual([b["date"] for b in bars],
                         ["2024-01-02", "2024-01-04"])

    def test_nulls_are_not_aligned_across_fields(self):
        """A row is dropped if *any* of its OHLC values is missing."""
        bars = market_data.parse_yahoo_chart(
            chart_payload(open=[472.16, None, 468.03],
                          high=[473.67, 471.19, None]), "SPY")
        self.assertEqual([b["date"] for b in bars], ["2024-01-02"])

    def test_null_volume_becomes_zero(self):
        bars = market_data.parse_yahoo_chart(
            chart_payload(volume=[72000, None, 90000]), "SPY")
        self.assertEqual(bars[1]["volume"], 0)

    def test_rows_are_sorted_chronologically(self):
        payload = chart_payload(timestamps=list(reversed(US_TIMESTAMPS)))
        dates = [b["date"] for b in market_data.parse_yahoo_chart(payload, "SPY")]
        self.assertEqual(dates, sorted(dates))

    def test_zero_prices_are_rejected(self):
        bars = market_data.parse_yahoo_chart(
            chart_payload(open=[0, 0, 0], close=[0, 0, 0]), "SPY")
        self.assertEqual(bars, [])

    def test_shorter_price_arrays_do_not_raise(self):
        bars = market_data.parse_yahoo_chart(
            chart_payload(close=[472.65]), "SPY")
        self.assertEqual(len(bars), 1)

    def test_delisted_symbol_error_response(self):
        payload = {"chart": {"result": None, "error": {
            "code": "Not Found",
            "description": "No data found, symbol may be delisted"}}}
        self.assertEqual(market_data.parse_yahoo_chart(payload, "BOGUS"), [])

    def test_malformed_inputs_return_empty_rather_than_raise(self):
        """A bad ticker must not take down a 36-ticker board."""
        for junk in (None, "", "not json", [], {}, {"chart": None},
                     {"chart": {}}, {"chart": {"result": []}},
                     {"chart": {"result": [{}]}},
                     {"chart": {"result": [{"timestamp": [], "indicators": {}}]}},
                     {"chart": {"result": [{"timestamp": [1704205800],
                                            "indicators": {"quote": []}}]}}):
            with self.subTest(junk=junk):
                self.assertEqual(market_data.parse_yahoo_chart(junk, "SPY"), [])

    def test_an_html_error_page_is_not_mistaken_for_data(self):
        self.assertEqual(
            market_data.parse_yahoo_chart("<html>Too Many Requests</html>", "SPY"),
            [])

    def test_non_numeric_prices_are_skipped(self):
        bars = market_data.parse_yahoo_chart(
            chart_payload(close=[472.65, "n/a", 467.28]), "SPY")
        self.assertEqual(len(bars), 2)


class FetchTests(unittest.TestCase):
    """The HTTP leg, with requests stubbed."""

    def _response(self, body, status=200):
        stub = mock.Mock()
        stub.status_code = status
        stub.text = body if isinstance(body, str) else json.dumps(body)
        return stub

    def test_successful_fetch(self):
        with mock.patch("requests.get",
                        return_value=self._response(chart_payload())):
            bars = market_data.fetch_yahoo_chart("SPY")
        self.assertEqual(len(bars), 3)

    def test_request_shape(self):
        with mock.patch("requests.get",
                        return_value=self._response(chart_payload())) as get:
            market_data.fetch_yahoo_chart("SPY", period="6mo")
        self.assertIn("/v8/finance/chart/SPY", get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs["params"],
                         {"range": "6mo", "interval": "1d"})

    def test_a_browser_user_agent_is_sent(self):
        """Yahoo serves an error page to obviously-scripted clients."""
        with mock.patch("requests.get",
                        return_value=self._response(chart_payload())) as get:
            market_data.fetch_yahoo_chart("SPY")
        self.assertIn("Mozilla", get.call_args.kwargs["headers"]["User-Agent"])

    def test_second_host_is_tried_when_the_first_is_throttled(self):
        """query1 and query2 are separate pools; one can answer when the other won't."""
        calls = []

        def fake_get(url, **kwargs):
            calls.append(url)
            if market_data.YAHOO_CHART_HOSTS[0] in url:
                return self._response("", status=429)
            return self._response(chart_payload())

        with mock.patch("requests.get", side_effect=fake_get):
            bars = market_data.fetch_yahoo_chart("SPY")

        self.assertEqual(len(bars), 3)
        self.assertEqual(len(calls), 2)

    def test_404_is_not_retried_on_the_second_host(self):
        """A missing symbol gets the same answer from both hosts."""
        calls = []

        def fake_get(url, **kwargs):
            calls.append(url)
            return self._response("", status=404)

        with mock.patch("requests.get", side_effect=fake_get):
            bars = market_data.fetch_yahoo_chart("BOGUS")

        self.assertEqual(bars, [])
        self.assertEqual(len(calls), 1)

    def test_network_exception_returns_empty_not_raise(self):
        with mock.patch("requests.get", side_effect=OSError("connection reset")):
            self.assertEqual(market_data.fetch_yahoo_chart("SPY"), [])

    def test_blank_ticker_makes_no_request(self):
        with mock.patch("requests.get") as get:
            self.assertEqual(market_data.fetch_yahoo_chart(""), [])
        get.assert_not_called()

    def test_fetch_many_collects_only_successes(self):
        def fake_get(url, **kwargs):
            if "/SPY" in url:
                return self._response(chart_payload())
            return self._response({"chart": {"result": None, "error": {
                "description": "delisted"}}})

        with mock.patch("requests.get", side_effect=fake_get):
            out = market_data.fetch_yahoo_chart_many(["SPY", "BOGUS"])

        self.assertEqual(set(out), {"SPY"})
        self.assertEqual(len(out["SPY"]), 3)

    def test_fetch_many_handles_empty_input(self):
        self.assertEqual(market_data.fetch_yahoo_chart_many([]), {})

    def test_rate_limiting_abandons_the_rest_of_the_batch(self):
        """A throttled host refuses the remainder too — stop asking.

        Without this, a 36-ticker board fires 72 requests into a host that is
        already answering 429, which deepens the throttle and cannot succeed.
        """
        calls = []

        def fake_get(url, **kwargs):
            calls.append(url)
            return self._response("", status=429)

        tickers = [f"T{i}" for i in range(24)]
        with mock.patch("requests.get", side_effect=fake_get):
            out = market_data.fetch_yahoo_chart_many(tickers)

        self.assertEqual(out, {})
        # Far fewer than one request per ticker, let alone two hosts each.
        self.assertLess(len(calls), len(tickers),
                        f"kept hammering a throttled host: {len(calls)} calls")

    def test_a_single_fetch_still_tries_both_hosts_on_429(self):
        """The batch-wide stop must not change one-off behaviour."""
        calls = []

        def fake_get(url, **kwargs):
            calls.append(url)
            return self._response("", status=429)

        with mock.patch("requests.get", side_effect=fake_get):
            self.assertEqual(market_data.fetch_yahoo_chart("SPY"), [])
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
