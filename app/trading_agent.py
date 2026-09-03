"""Autonomous, paper-only SPY options agent with deterministic risk gates."""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.alpaca_mcp import AlpacaMCP, EXECUTE_TOOL, configured as alpaca_configured
from app.config import DATA_DIR


SYSTEM_PROMPT = """You are drrrd Agent Desk, an autonomous PAPER-trading research agent.
Use Alpaca MCP tools to inspect the paper account, market clock, SPY snapshot,
SPY option chain/quotes, positions and open orders. Select at most one long SPY
call or put, 7-45 calendar days to expiration, with a liquid quote and premium
at or below $2.50 per share ($250 maximum loss). Never request stock, crypto,
short options, multi-leg orders, exercise, cancellation, or liquidation.

Return ONLY JSON when research is complete:
{"action":"TRADE|SKIP","underlying":"SPY","option_symbol":"OCC symbol or empty",
"side":"buy","position_intent":"buy_to_open","qty":1,"order_type":"limit",
"limit_price":0.0,"confidence":0.0,"thesis":"short evidence-based explanation",
"evidence":["fact"],"invalidation":"what would make the thesis wrong"}
Choose SKIP whenever data is missing, the market is closed, spreads are poor,
an equivalent position/order exists, or confidence is below 0.55. Do not call
any order-placement tool; deterministic code owns execution after validation."""


@dataclass
class GateResult:
    passed: bool
    checks: list[dict]
    max_loss_dollars: float


_run_lock = threading.Lock()


def is_configured() -> bool:
    provider = os.environ.get("AGENT_MODEL_PROVIDER", "anthropic").lower()
    model_key = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    return alpaca_configured() and bool(os.environ.get(model_key))


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("model did not return a JSON proposal")
    return json.loads(text[start:end + 1])


def _occ_expiration(symbol: str) -> date | None:
    match = re.fullmatch(r"SPY(\d{6})[CP]\d{8}", symbol.upper())
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%y%m%d").date()
    except ValueError:
        return None


def apply_risk_gates(
    proposal: dict, *, already_traded: bool = False, market_open: bool = True
) -> GateResult:
    """Validate model output without trusting model reasoning or arithmetic."""
    checks = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    action = str(proposal.get("action", "SKIP")).upper()
    symbol = str(proposal.get("option_symbol", "")).upper()
    expiration = _occ_expiration(symbol)
    try:
        qty = int(proposal.get("qty", 0))
        price = round(float(proposal.get("limit_price", 0)), 2)
        confidence = float(proposal.get("confidence", 0))
    except (TypeError, ValueError):
        qty, price, confidence = 0, 0.0, 0.0
    dte = (expiration - date.today()).days if expiration else -1
    max_loss = max(0.0, qty * price * 100)

    check("trade proposed", action == "TRADE", f"action={action}")
    check("paper mode locked", os.environ.get("ALPACA_PAPER_TRADE", "true").lower() == "true",
          "ALPACA_PAPER_TRADE must be true")
    check("market open", market_open, "verified directly through Alpaca MCP")
    check("SPY long option", proposal.get("underlying") == "SPY" and symbol.startswith("SPY"), symbol)
    check("defined risk", proposal.get("side") == "buy" and proposal.get("position_intent") == "buy_to_open",
          "only buy_to_open is accepted")
    check("one contract", qty == 1, f"qty={qty}")
    check("limit order", proposal.get("order_type") == "limit", str(proposal.get("order_type")))
    check("premium cap", 0.05 <= price <= 2.50 and max_loss <= 250, f"max loss=${max_loss:.2f}")
    check("expiration window", 7 <= dte <= 45, f"DTE={dte}")
    check("confidence floor", 0.55 <= confidence <= 1.0, f"confidence={confidence:.2f}")
    check("daily throttle", not already_traded, "maximum one submitted order per UTC day")
    return GateResult(all(item["passed"] for item in checks), checks, max_loss)


def _audit_path() -> Path:
    return Path(DATA_DIR) / "agent_runs.jsonl"


def recent_runs(limit: int = 20) -> list[dict]:
    path = _audit_path()
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(rows[-max(1, min(limit, 100)):]))


def _already_traded_today() -> bool:
    today = datetime.now(timezone.utc).date().isoformat()
    return any(r.get("timestamp", "").startswith(today) and r.get("status") == "submitted"
               for r in recent_runs(100))


def _find_bool(value: Any, key: str) -> bool | None:
    if isinstance(value, dict):
        for current_key, current_value in value.items():
            if current_key.lower() == key.lower() and isinstance(current_value, bool):
                return current_value
            found = _find_bool(current_value, key)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_bool(item, key)
            if found is not None:
                return found
    return None


def _find_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        for current_key, current_value in value.items():
            if current_key.lower() == key.lower():
                return current_value
            found = _find_value(current_value, key)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_value(item, key)
            if found is not None:
                return found
    return None


def _order_summary(result: dict) -> dict:
    """Keep demo-safe order proof; do not publish full broker responses."""
    summary = {"ok": bool(result.get("ok"))}
    data = result.get("data")
    for key in ("id", "client_order_id", "status", "symbol", "qty", "side", "type",
                "limit_price", "submitted_at"):
        value = _find_value(data, key)
        if value is not None:
            summary[key] = value
    if not summary["ok"]:
        summary["message"] = str(_find_value(data, "message") or "Alpaca rejected the order")[:300]
    return summary


def _save(run: dict) -> None:
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(run, separators=(",", ":"), default=str) + "\n")


async def _anthropic_loop(mcp: AlpacaMCP, prompt: str) -> tuple[dict, list[dict]]:
    import anthropic

    client = anthropic.AsyncAnthropic()
    tools = [{"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
             for t in mcp.model_tools()]
    messages: list[dict] = [{"role": "user", "content": prompt}]
    trace = []
    for _ in range(10):
        response = await client.messages.create(
            model=os.environ.get("ANTHROPIC_AGENT_MODEL", "claude-sonnet-4-5"),
            max_tokens=3000, system=SYSTEM_PROMPT, tools=tools, messages=messages,
        )
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            text = "\n".join(b.text for b in response.content if b.type == "text")
            return _extract_json(text), trace
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for call in tool_uses:
            output = await mcp.call(call.name, call.input)
            trace.append({"tool": call.name, "ok": output["ok"]})
            results.append({"type": "tool_result", "tool_use_id": call.id,
                            "content": json.dumps(output)[:30000]})
        messages.append({"role": "user", "content": results})
    raise RuntimeError("agent exceeded its ten-turn tool budget")


async def _openai_loop(mcp: AlpacaMCP, prompt: str) -> tuple[dict, list[dict]]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    tools = [{"type": "function", "name": t["name"], "description": t["description"],
              "parameters": t["input_schema"]} for t in mcp.model_tools()]
    inputs: list[Any] = [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": prompt}]
    trace = []
    for _ in range(10):
        response = await client.responses.create(
            model=os.environ.get("OPENAI_AGENT_MODEL", "gpt-5.2"), input=inputs, tools=tools,
        )
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            return _extract_json(response.output_text), trace
        inputs += [item.model_dump() for item in response.output]
        for call in calls:
            args = json.loads(call.arguments or "{}")
            output = await mcp.call(call.name, args)
            trace.append({"tool": call.name, "ok": output["ok"]})
            inputs.append({"type": "function_call_output", "call_id": call.call_id,
                           "output": json.dumps(output)[:30000]})
    raise RuntimeError("agent exceeded its ten-turn tool budget")


async def run_once(*, execute: bool = True) -> dict:
    """Research, gate, and optionally submit one autonomous paper order."""
    run_id = f"drrrd-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8]}"
    provider = os.environ.get("AGENT_MODEL_PROVIDER", "anthropic").lower()
    run: dict = {"run_id": run_id, "timestamp": datetime.now(timezone.utc).isoformat(),
                 "provider": provider, "status": "started", "trace": []}
    try:
        if provider not in {"anthropic", "openai"}:
            raise ValueError("AGENT_MODEL_PROVIDER must be anthropic or openai")
        if not is_configured():
            raise RuntimeError("Alpaca and selected model credentials are not configured")
        async with AlpacaMCP() as mcp:
            clock = await mcp.call("get_clock")
            market_open = bool(clock["ok"] and _find_bool(clock["data"], "is_open") is True)
            run["preflight"] = {"clock_ok": clock["ok"], "market_open": market_open}
            prompt = ("Run the smallest viable hackathon demo now. Research only SPY and its "
                      "options. This is a dedicated $100,000 competition paper account. "
                      "Make one proposal or skip; obey every constraint.")
            if provider == "openai":
                proposal, trace = await _openai_loop(mcp, prompt)
            else:
                proposal, trace = await _anthropic_loop(mcp, prompt)
            run["proposal"], run["trace"] = proposal, trace
            gates = apply_risk_gates(
                proposal, already_traded=_already_traded_today(), market_open=market_open
            )
            run["risk"] = asdict(gates)
            if not gates.passed:
                run["status"] = "skipped"
            elif not execute or os.environ.get("ALPACA_AUTOTRADE_ENABLED", "false").lower() != "true":
                run["status"] = "approved_dry_run"
            else:
                result = await mcp.call(EXECUTE_TOOL, {
                    "qty": "1", "type": "limit", "time_in_force": "day",
                    "symbol": str(proposal["option_symbol"]).upper(), "side": "buy",
                    "position_intent": "buy_to_open",
                    "limit_price": f"{float(proposal['limit_price']):.2f}",
                    "client_order_id": run_id,
                })
                run["order"] = _order_summary(result)
                run["status"] = "submitted" if result["ok"] else "order_rejected"
    except Exception as exc:
        run["status"] = "error"
        run["error"] = f"{type(exc).__name__}: {exc}"
    _save(run)
    return run


def run_sync(*, execute: bool = True) -> dict:
    if not _run_lock.acquire(blocking=False):
        raise RuntimeError("an agent run is already in progress")
    try:
        return asyncio.run(run_once(execute=execute))
    finally:
        _run_lock.release()
