# drrrd Agent Desk — Alpaca AI Trading Agent

An autonomous, **paper-only SPY options agent** built for the Alpaca AI Trading
Agents Hackathon. The application hosts Alpaca's official v2 MCP server inside
its Python agent loop, supports Claude or OpenAI, visualizes every decision, and
uses deterministic risk gates before any order can be submitted.

## Hackathon demo (`/agent`)

The smallest viable demo is one end-to-end decision:

1. **Observe** — the selected model uses read-only Alpaca MCP tools for the
   competition account, clock, SPY snapshot, option chain, quotes and orders.
2. **Reason** — it returns one typed proposal: a long SPY call, a long SPY put,
   or `SKIP`.
3. **Veto** — Python independently enforces paper mode, one contract, limit
   execution, buy-to-open only, market-open verification, 7–45 DTE, a $250 maximum loss, a confidence
   floor and a one-order-per-day throttle.
4. **Execute** — only an approved proposal reaches MCP's `place_option_order`,
   with an idempotent client order ID. Every step is appended to an audit log.

```bash
cp .env.example .env              # fill paper and one model provider key
set -a; source .env; set +a
pip install -r requirements.txt
python main.py
# open http://localhost:5000/agent
```

`ALPACA_AUTOTRADE_ENABLED=false` is the safe default and produces an approved
dry run. Set it to `true` only on the dedicated competition paper account to
allow autonomous paper option orders. Live trading is structurally disabled:
the MCP subprocess is always launched with `ALPACA_PAPER_TRADE=true`.
The execution endpoint also requires `AGENT_RUN_TOKEN`, preventing visitors to
the public demo from triggering a run.

Submission assets: [one-page write-up](HACKATHON_SUBMISSION.md),
[90-second demo script](DEMO_SCRIPT.md), and
[final checklist](SUBMISSION_CHECKLIST.md).

---

## Original project — Iran Investment Tracker

A full-stack web application that automatically tracks all 36 tickers from the Iran Regime Change Investment Plan. Live prices, auto-refresh, alerts, CSV export, and a production-ready dashboard.

## 🔮 ForesightTape — Next-Session Forecast Engine (`/foresight`)

A probability board for the next trading session, built from two layers:

1. **Quant prior** (`app/forecast_quant.py`) — a Student-t distribution over the next
   session's return, with volatility from a Yang-Zhang + EWMA blend and a heavily
   shrunk drift from momentum/trend/reversal signals. Runs from price history alone —
   no API key required.
2. **Catalyst overlay** (`app/forecast_catalyst.py`, optional) — Claude researches live
   catalysts (earnings dates, Fed events, breaking news) via web search and returns a
   *bounded* tilt on each prior: at most a few probability points of direction and a
   capped volatility multiplier. Enable it by setting `ANTHROPIC_API_KEY` in the server
   environment. Without the key the board runs quant-only. The key never reaches the
   browser.

Every published forecast is stored (`forecasts` table) and graded once its target
session closes — Brier score, skill vs. coin flip, hit rate and a calibration table
live on the **Accuracy** tab. The board's honesty is enforced by construction: the
engine cannot claim more than a modest edge on a daily candle, and "doji" (no edge) is
a first-class call.

### Does it actually work? Run the backtest

The **Accuracy** tab has a *Run backtest* button that replays the quant engine
forward through history — each session forecast using only the bars that existed
at the time — so you get a real skill estimate immediately instead of waiting
weeks for the live ledger to fill. It reports Brier score and skill against two
baselines:

- **Coin flip** (always 50/50) — the skill score is measured against this.
- **Always up** — equities drift upward, so a model that blindly says "up" every
  session already posts a hit rate above 50%. An engine that can't beat this
  has a directional hit rate that is noise, not insight.

The catalyst overlay is excluded from backtests: past web research can't be
reconstructed without leaking the outcome. Backtest results are deliberately
**not** written to the ledger, so simulated history never inflates the live
track record.

Endpoints: `/foresight/api/market`, `/foresight/api/watchlist?tickers=…`,
`/foresight/api/scorecard`, `/foresight/api/backtest`,
`POST /foresight/api/resolve`.
Tests: `python -m unittest discover -s tests`.

### Where the prices come from

Three independent providers, tried in order, each asked only for the tickers the
previous one could not supply:

1. **Yahoo's chart API, called directly** — plain HTTPS against
   `v8/finance/chart`, no library in the way. Chart data needs no cookie/crumb
   handshake, so this path is immune both to Yahoo changing that handshake and
   to yfinance changing its response shape.
2. **yfinance** — kept as a second path for its own retry and session handling.
3. **Stooq** — a different origin entirely, for when Yahoo refuses the host
   outright (it throttles datacenter IP ranges hard, which is what makes a
   cloud-deployed board go blank).

The board reports which provider served the data whenever it isn't the first, so
a degraded path is visible rather than silent. Historically the app depended on
yfinance alone, and every blank board traced back to that.

**Board empty?** Run `python diagnose.py` — a standalone report that runs each
provider separately and separates a blocked IP, a rate limit, a yfinance/API
mismatch and a network problem. It also captures yfinance's own log, since it
reports most failures by logging them and returning an empty frame, leaving the
app with "no data" and no exception.

### ⚠️ Keeping the accuracy history

The forecast ledger is only meaningful if it survives redeploys. By default the
app writes SQLite to `data/tracker.db` — fine locally, but on a host with an
ephemeral filesystem (including Render's free plan) **every redeploy wipes the
scorecard and it restarts from zero.** Two ways to keep it:

| Option | Set | Notes |
|---|---|---|
| **Postgres** | `DATABASE_URL` | Works on free tiers with no volume. Any Postgres URL — Render, Neon, Supabase. Schema is created automatically on boot. |
| **Mounted volume** | `DATA_DIR` | Point at a Render disk / Railway volume / Docker `-v` mount, e.g. `DATA_DIR=/var/data`. Render disks need a paid instance type. |

`render.yaml` has both wired up as commented blocks — uncomment whichever you want.

---

## 🚀 Deploy in Under 5 Minutes

Pick any platform below. **Render.com is the easiest** (free tier, no credit card).

---

> 📘 **Deploying to Render: [DEPLOY.md](DEPLOY.md)** — includes setting the
> Anthropic key and keeping the forecast accuracy history across redeploys.
>
> 💻 **Running it from your own laptop: [LAPTOP.md](LAPTOP.md)** — no hosting
> needed, and it sidesteps the Yahoo Finance datacenter-IP blocking that can
> leave a cloud-hosted board empty.

### Option 1: Render.com (Recommended — Free)

1. **Create a free account** at [render.com](https://render.com)
2. **Push this folder to GitHub:**
   ```bash
   cd iran-tracker-web
   git init
   git add .
   git commit -m "Initial commit"
   gh repo create iran-tracker --public --source=. --push
   ```
3. **In Render dashboard:**
   - Click **New** → **Web Service**
   - Connect your GitHub repo
   - Render auto-detects the `render.yaml`
   - Click **Deploy**
4. Your site is live at `https://iran-tracker-xxxx.onrender.com`

> ⚠️ Free tier sleeps after 15 min of inactivity. First visit after sleep takes ~30s to wake.

---

### Option 2: Railway.app (Free $5/month credits)

1. **Create account** at [railway.app](https://railway.app)
2. **Push to GitHub** (see step 2 above)
3. In Railway:
   - Click **New Project** → **Deploy from GitHub repo**
   - Select your repo
   - Railway auto-detects the Procfile
   - Click **Deploy**
4. Go to **Settings** → **Networking** → **Generate Domain**
5. Your site is live!

---

### Option 3: Heroku ($5/month Eco plan)

```bash
# Install Heroku CLI: https://devcenter.heroku.com/articles/heroku-cli
cd iran-tracker-web
heroku login
heroku create iran-tracker
git push heroku main
heroku open
```

---

### Option 4: Docker (Self-hosted / Any VPS)

```bash
cd iran-tracker-web
docker build -t iran-tracker .
docker run -p 5000:5000 iran-tracker
```

Then visit `http://localhost:5000`

For a cloud VPS (DigitalOcean, AWS, Linode):
```bash
# On your VPS:
git clone https://github.com/YOUR_USER/iran-tracker.git
cd iran-tracker
docker build -t iran-tracker .
docker run -d -p 80:5000 --restart always iran-tracker
```

---

### Option 5: Run Locally

```bash
cd iran-tracker-web
pip install -r requirements.txt
python app.py
```
Visit `http://localhost:5000`

---

## 📁 Project Structure

```
iran-tracker-web/
├── app.py              ← Flask backend (fetches data, serves API)
├── templates/
│   └── index.html      ← Dashboard frontend (vanilla HTML/CSS/JS)
├── requirements.txt    ← Python dependencies
├── Procfile            ← For Heroku/Railway/Render
├── Dockerfile          ← For Docker deployment
├── render.yaml         ← Render.com auto-config
└── data/               ← Auto-created: CSV snapshots, alerts
```

---

## 🔧 How It Works

```
┌─────────────────────────────────────────────────────┐
│                   YOUR BROWSER                       │
│  ┌─────────────────────────────────────────────┐    │
│  │         Live Dashboard (index.html)          │    │
│  │  • Auto-refreshes every 5 minutes            │    │
│  │  • Tier filters, search, sort by any column  │    │
│  │  • Color-coded change %, alerts panel         │    │
│  │  • Download CSV button                        │    │
│  └──────────────────┬──────────────────────────┘    │
│                     │ fetch /api/prices              │
└─────────────────────┼───────────────────────────────┘
                      │
┌─────────────────────┼───────────────────────────────┐
│            FLASK SERVER (app.py)                      │
│                     │                                 │
│  ┌─────────────────┴──────────────────────────┐     │
│  │         Background Scheduler                │     │
│  │  • Fetches Yahoo Finance every 5 min        │     │
│  │  • Checks for ±5% alert triggers            │     │
│  │  • Appends to CSV log every cycle            │     │
│  │  • Refreshes 30-day history every 6 hrs     │     │
│  └─────────────────┬──────────────────────────┘     │
│                     │                                 │
│        ┌────────────┼────────────┐                   │
│        ▼            ▼            ▼                    │
│   /api/prices  /api/history  /api/download/csv       │
│                                                       │
│   data/snapshots.csv  ← grows over time              │
│   data/alerts.json    ← alert history                │
└──────────────────────────────────────────────────────┘
```

**Auto-Refresh Cycle:**
1. Backend scheduler calls Yahoo Finance every 5 minutes
2. Parses price/change/volume for all 36 tickers
3. Stores in memory cache + appends to CSV
4. Frontend polls `/api/prices` with a 5-minute countdown
5. Dashboard re-renders with updated data
6. Alerts fire for any ticker moving ±5% in a session

---

## 🔌 API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Dashboard HTML page |
| `/api/prices` | GET | Current prices for all 36 tickers (JSON) |
| `/api/history` | GET | 30-day price history for sparklines (JSON) |
| `/api/refresh` | POST | Force an immediate data refresh |
| `/api/download/csv` | GET | Download full snapshot history as CSV |

---

## 🔑 Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | No | Enables the Claude catalyst overlay on `/foresight`. Unset = quant-only mode. Set it in your host's dashboard — never commit it. |
| `DATABASE_URL` | No | Postgres connection string. When set, all storage uses Postgres instead of SQLite. |
| `DATA_DIR` | No | Where SQLite and CSV snapshots are written (default `data`). Point at a mounted volume to persist across redeploys. |
| `MARKET_DATA_SOURCE` | No | Which price providers to use, in order. `auto` (default) = Yahoo chart API → yfinance → Stooq, each asked only for what the previous one missed. `yahoo` drops Stooq; `stooq`, `chart` and `yfinance` each force a single provider (useful for isolating a fault). |
| `PORT` | No | Port to bind (default `5000`). Most hosts set this for you. |

---

## ⚙️ Configuration

**Change refresh interval:** In `app.py`, find:
```python
scheduler.add_job(fetch_prices, "interval", minutes=5, ...)
```
Change `minutes=5` to your preferred interval.

**Add/remove tickers:** Edit the `TIERS` dictionary in `app.py`.

**Custom alerts threshold:** Change `abs(change) >= 5` in the `fetch_prices()` function.

---

## ⚠️ Disclaimer

This application is for **informational tracking purposes only**. It does not constitute financial, legal, or investment advice. Data is sourced from Yahoo Finance and may be delayed 15–20 minutes. Always verify with your broker's live feed before making any investment decisions. Consult a licensed financial advisor.
