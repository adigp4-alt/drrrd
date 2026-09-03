# 90-second demo script

**0:00–0:12 — Hook**  
“Most AI trading demos celebrate when the model says buy. drrrd is built around the more important question: should the model be allowed to trade at all?”

**0:12–0:28 — Architecture**  
Show the four-stage strip on `/agent`. “The Python host connects to Alpaca's official MCP server. Claude or OpenAI can research the paper account, SPY and its option chain—but the model never receives the order-placement tool.”

**0:28–0:48 — Live run**  
Press **Run autonomous agent**. “The agent can return one long SPY call or put, or skip. The universe is intentionally narrow and liquid so the behavior is reproducible.”

**0:48–1:08 — Safety reveal**  
Scroll to Risk Gate. “Now untrusted model output hits ten deterministic checks: paper mode, one contract, buy-to-open only, limit order, 7–45 DTE, $250 maximum loss, confidence floor, and a one-order-per-day throttle.”

**1:08–1:22 — Alpaca proof**  
Point to MCP trace and order status. “Only an approved proposal reaches Alpaca MCP's option-order tool, with an idempotent client ID. A rejection or skip is fully visible.”

**1:22–1:30 — Close**  
“drrrd does not ask you to trust the AI. It shows the evidence, constrains the blast radius, and keeps the final authority in code.”

## Recording fallback

If markets are closed, use **Run research-only demo** and show the clean `SKIP` path. Record one successful paper submission during market hours as a short backup clip.
