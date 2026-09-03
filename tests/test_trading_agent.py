from __future__ import annotations

import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.trading_agent import apply_risk_gates  # noqa: E402
from app import create_app  # noqa: E402


def option_symbol(days=14, strike=500, kind="C"):
    expiry = (date.today() + timedelta(days=days)).strftime("%y%m%d")
    return f"SPY{expiry}{kind}{strike * 1000:08d}"


def valid_proposal():
    return {"action": "TRADE", "underlying": "SPY", "option_symbol": option_symbol(),
            "side": "buy", "position_intent": "buy_to_open", "qty": 1,
            "order_type": "limit", "limit_price": 2.25, "confidence": .70}


class RiskGateTests(unittest.TestCase):
    def test_accepts_one_defined_risk_spy_contract(self):
        with mock.patch.dict(os.environ, {"ALPACA_PAPER_TRADE": "true"}):
            result = apply_risk_gates(valid_proposal())
        self.assertTrue(result.passed)
        self.assertEqual(result.max_loss_dollars, 225)

    def test_rejects_short_option(self):
        proposal = valid_proposal()
        proposal.update(side="sell", position_intent="sell_to_open")
        self.assertFalse(apply_risk_gates(proposal).passed)

    def test_rejects_live_mode_even_when_everything_else_is_valid(self):
        with mock.patch.dict(os.environ, {"ALPACA_PAPER_TRADE": "false"}):
            result = apply_risk_gates(valid_proposal())
        self.assertFalse(result.passed)
        self.assertFalse(next(c for c in result.checks if c["name"] == "paper mode locked")["passed"])

    def test_rejects_premium_above_max_loss(self):
        proposal = valid_proposal()
        proposal["limit_price"] = 2.51
        self.assertFalse(apply_risk_gates(proposal).passed)

    def test_rejects_second_order_same_day(self):
        self.assertFalse(apply_risk_gates(valid_proposal(), already_traded=True).passed)

    def test_skip_never_passes_execution_gate(self):
        proposal = valid_proposal()
        proposal["action"] = "SKIP"
        self.assertFalse(apply_risk_gates(proposal).passed)

    def test_closed_market_is_a_hard_veto(self):
        self.assertFalse(apply_risk_gates(valid_proposal(), market_open=False).passed)


class AgentRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app(start_background=False).test_client()

    def test_public_visitor_cannot_trigger_agent(self):
        with mock.patch.dict(os.environ, {"AGENT_RUN_TOKEN": "secret"}):
            response = self.client.post("/agent/api/run", json={"dry_run": True})
        self.assertEqual(response.status_code, 401)

    def test_valid_token_can_trigger_dry_run(self):
        fake = {"status": "approved_dry_run", "run_id": "demo"}
        with mock.patch.dict(os.environ, {"AGENT_RUN_TOKEN": "secret"}), \
             mock.patch("app.routes.agent.trading_agent.run_sync", return_value=fake) as run:
            response = self.client.post(
                "/agent/api/run", json={"dry_run": True},
                headers={"X-Agent-Token": "secret"},
            )
        self.assertEqual(response.status_code, 200)
        run.assert_called_once_with(execute=False)


if __name__ == "__main__":
    unittest.main()
