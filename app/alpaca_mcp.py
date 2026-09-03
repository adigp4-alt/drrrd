"""Small, audited client for Alpaca's official v2 MCP server.

The application is the MCP host: it starts Alpaca's stdio server, discovers
the current schemas, and forwards only explicitly allow-listed tools to the
model. Credentials stay in the subprocess environment and are never included
in prompts, logs, or browser responses.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


READ_TOOLS = {
    "get_account_info",
    "get_account_config",
    "get_all_positions",
    "get_orders",
    "get_clock",
    "get_option_contracts",
    "get_option_chain",
    "get_option_snapshot",
    "get_option_latest_quote",
    "get_stock_snapshot",
    "get_news",
}
EXECUTE_TOOL = "place_option_order"


def configured() -> bool:
    return bool(os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_SECRET_KEY"))


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


class AlpacaMCP:
    """Async context manager around the official Alpaca MCP stdio server."""

    def __init__(self) -> None:
        command = os.environ.get("ALPACA_MCP_COMMAND")
        if command:
            args = shlex.split(os.environ.get("ALPACA_MCP_ARGS", ""))
        else:
            # Invoking the installed module through this interpreter is more
            # portable than assuming pip's scripts directory is on PATH.
            command = sys.executable
            args = ["-c", "from alpaca_mcp_server.cli import main; main()"]
        env = dict(os.environ)
        env["ALPACA_PAPER_TRADE"] = "true"  # this project can never launch live mode
        env.setdefault(
            "ALPACA_TOOLSETS",
            "account,trading,assets,stock-data,options-data,news",
        )
        self.params = StdioServerParameters(command=command, args=args, env=env)
        self._transport = None
        self._session_cm = None
        self.session: ClientSession | None = None
        self.tools: dict[str, Any] = {}

    async def __aenter__(self) -> "AlpacaMCP":
        if not configured():
            raise RuntimeError("ALPACA_API_KEY and ALPACA_SECRET_KEY are required")
        self._transport = stdio_client(self.params)
        read, write = await self._transport.__aenter__()
        self._session_cm = ClientSession(read, write)
        self.session = await self._session_cm.__aenter__()
        await self.session.initialize()
        listed = await self.session.list_tools()
        allowed = READ_TOOLS | {EXECUTE_TOOL}
        self.tools = {tool.name: tool for tool in listed.tools if tool.name in allowed}
        missing = {"get_account_info", "get_clock", "get_option_chain", EXECUTE_TOOL} - self.tools.keys()
        if missing:
            raise RuntimeError(f"Alpaca MCP v2 is missing required tools: {sorted(missing)}")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session_cm:
            await self._session_cm.__aexit__(exc_type, exc, tb)
        if self._transport:
            await self._transport.__aexit__(exc_type, exc, tb)

    def model_tools(self) -> list[dict]:
        result = []
        for name in sorted(READ_TOOLS & self.tools.keys()):
            tool = self.tools[name]
            result.append({
                "name": name,
                "description": tool.description or "Alpaca market/account tool",
                "input_schema": _jsonable(tool.inputSchema),
            })
        return result

    async def call(self, name: str, arguments: dict | None = None) -> dict:
        if not self.session or name not in self.tools:
            raise RuntimeError(f"MCP tool is unavailable: {name}")
        result = await self.session.call_tool(name, arguments or {})
        payload = _jsonable(result)
        if isinstance(payload, dict) and payload.get("structuredContent") is not None:
            return {"ok": not payload.get("isError", False), "data": payload["structuredContent"]}
        texts = []
        for block in payload.get("content", []) if isinstance(payload, dict) else []:
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
        raw = "\n".join(texts)
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            data = raw
        return {"ok": not (isinstance(payload, dict) and payload.get("isError", False)), "data": data}
