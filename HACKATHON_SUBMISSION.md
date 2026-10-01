# drrrd Agent Desk — Submission Draft

## One-line pitch

drrrd is an autonomous SPY options agent that combines Alpaca MCP market intelligence with model reasoning, then forces every idea through deterministic risk gates before it can touch a paper account.

## The problem

Trading agents are impressive when they find a trade, but dangerous when the language model also owns execution policy. A persuasive hallucination can become an order. drrrd separates those powers: the model can research and propose; ordinary Python decides whether the proposal is permitted.

## AI logic

The Python host starts Alpaca's official v2 MCP server and dynamically discovers its current tools and JSON schemas. A configurable Claude or OpenAI agent uses read-only Alpaca tools to inspect the $100,000 competition paper account, market clock, SPY snapshot, option chain, quotes, positions and orders. It returns one typed proposal—one long call, one long put, or `SKIP`—with evidence, confidence and invalidation criteria.

The narrow SPY universe is deliberate. It makes the demo reproducible, keeps options liquidity high, and lets judges understand every decision in seconds.

## Risk gates

The language model cannot place orders. Its JSON proposal must pass eleven deterministic checks:

1. A trade was explicitly proposed.
2. Alpaca paper mode is locked on.
3. The market is open, verified directly through Alpaca MCP.
4. The underlying and OCC contract are SPY.
5. The position is `buy_to_open`, never a short option.
6. Quantity is exactly one contract.
7. Execution is a limit order.
8. Premium and maximum loss are capped at $250.
9. Expiration is 7–45 calendar days away.
10. Confidence is at least 55%.
11. No order has already been submitted that UTC day.

Only then does Python call Alpaca MCP's `place_option_order`, using a unique client order ID. A timeout cannot silently generate a duplicate retry. `SKIP` is a successful outcome, not a failure.

## Alpaca infrastructure

- Official `alpaca-mcp-server` v2 over MCP stdio
- Server-side toolset filtering: account, trading, assets, stock data, options data and news
- Live Alpaca option-chain research and account state
- Autonomous `place_option_order` on the dedicated paper account
- Paper mode forced to `true` inside the MCP subprocess, independent of model output
- Append-only JSONL audit trail containing MCP tool trace, proposal, every gate and order result
- Token-protected run endpoint so a public demo URL cannot be used to trigger orders

## Visualization

The Flask **Agent Desk** turns a run into a four-stage story: Observe → Reason → Veto → Execute. Judges see the proposal, confidence, maximum loss, each gate, every MCP tool invoked and the raw audit record. The existing ForesightTape remains available as the deeper quantitative visualization and backtest layer.

## Smallest viable demo

Open `/agent`, select **Run autonomous agent**, and watch one complete run. The agent either submits one capped-loss SPY paper option limit order or visibly explains why it skipped. That single screen demonstrates agent reasoning, Alpaca MCP, options execution, safety engineering and observability.

## Disclaimer

Educational hackathon software only. Paper trading only; not investment advice. No claim of profitability or future performance is made.
