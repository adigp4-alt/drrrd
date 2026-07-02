# Iran Investment Tracker — Live Web Dashboard

A full-stack web application that tracks all 36 tickers from the Iran Regime Change Investment Plan. Live prices with WebSocket push, ML predictions, Prophet forecasting, portfolio tracking, backtesting, alerts, news sentiment, risk metrics, and an installable PWA — open it from any device, anywhere.

---

## 🌍 Open It Anywhere

Once deployed (see below), the app is a normal website URL — open it from any phone, tablet, or computer.

**Install it like an app (PWA):**
- **Android / Chrome:** open the site → menu (⋮) → *Add to Home screen*
- **iPhone / Safari:** open the site → Share → *Add to Home Screen*
- **Desktop Chrome/Edge:** click the install icon in the address bar

It launches full-screen like a native app and caches the shell for offline viewing.

**Remote API access:** set the `REMOTE_API_KEY` environment variable, then call the authenticated `/remote/*` endpoints (refresh, prices, portfolio, alert, holding) from anywhere with the `X-API-Key` header.

**Discord bot (optional):** set `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID` to get price alerts and query commands in your Discord server.

---

## 🚀 Deploy in Under 5 Minutes

### Option 1: Render.com (Recommended — Free)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/adigp4-alt/drrrd)

1. Create a free account at [render.com](https://render.com)
2. Click the button above (or **New → Blueprint** and connect `adigp4-alt/drrrd`)
3. Render auto-detects `render.yaml` — click **Deploy**
4. Your site is live at `https://iran-tracker-xxxx.onrender.com`

> ⚠️ Free tier sleeps after 15 min of inactivity. First visit after sleep takes ~30s to wake.

### Option 2: Railway.app

1. Create an account at [railway.app](https://railway.app)
2. **New Project → Deploy from GitHub repo** → select `adigp4-alt/drrrd`
3. Railway auto-detects the `Procfile` → **Deploy**
4. **Settings → Networking → Generate Domain**

### Option 3: Docker (Self-hosted / Any VPS)

```bash
git clone https://github.com/adigp4-alt/drrrd.git
cd drrrd
docker compose up -d --build
```

Then visit `http://localhost:5000` (or `http://YOUR_VPS_IP` with `-p 80:5000`).

### Option 4: Run Locally

```bash
git clone https://github.com/adigp4-alt/drrrd.git
cd drrrd
./run.sh          # creates venv, installs deps, starts the server
```

Visit `http://localhost:5000`

---

## 📁 Project Structure

```
drrrd/
├── main.py                 ← Entry point (Flask + SocketIO)
├── app/
│   ├── __init__.py         ← Flask app factory, blueprint registration
│   ├── config.py           ← Tickers, tiers, paths
│   ├── data_fetcher.py     ← Yahoo Finance fetching + cache
│   ├── scheduler.py        ← Background jobs (prices 5 min, history 6 hrs, daily AI)
│   ├── alerts.py           ← Custom alert engine
│   ├── ml_predictor.py     ← scikit-learn price direction model
│   ├── prophet_forecaster.py ← Prophet time-series forecasts
│   ├── nlp_engine.py       ← AI Copilot daily briefing
│   ├── strategy.py         ← Autonomous strategy scanner
│   ├── risk.py             ← Risk metrics (volatility, drawdown, Sharpe)
│   ├── auth.py             ← API-key auth for remote endpoints
│   ├── discord_bot.py      ← Optional Discord alerts/commands
│   ├── extensions.py       ← SocketIO instance
│   ├── static/             ← PWA manifest, service worker, icon
│   ├── routes/             ← One blueprint per feature
│   └── tasks/              ← Daily AI data collection
├── templates/              ← Dashboard, portfolio, analysis, news, risk, …
├── tests/                  ← Pytest suite (run: pytest -q)
├── requirements.txt
├── render.yaml             ← Render.com blueprint
├── Procfile                ← Railway/Heroku
├── Dockerfile + docker-compose.yml
└── run.sh                  ← Local quick-start
```

---

## 🔌 Key Pages & Endpoints

| Page | Description |
|---|---|
| `/` | Live dashboard (WebSocket price push, AI Copilot briefing) |
| `/portfolio` | Holdings, P&L, allocation |
| `/screener` | ML-scored ticker screener |
| `/backtest` | Strategy backtesting |
| `/stat-arb` | Pairs-trading / statistical arbitrage |
| `/analysis` | Indicators, Prophet forecast, news sentiment |
| `/alerts` | Custom alert rules + history |
| `/watchlist` | Personal watchlist |
| `/correlation` | Correlation matrix |
| `/reports` | Reports & exports |
| `/history` | Historical charts per ticker |
| `/news` | News feed with sentiment scoring |
| `/risk` | Risk metrics per ticker |
| `/compare` | Side-by-side ticker comparison |
| `/heatmap` | Performance heatmap |
| `/autonomous` | Autonomous strategy scanner |
| `/health` | Health check (JSON) |
| `/api/prices` | Current prices for all tickers (JSON) |
| `/remote/*` | Authenticated remote-control API (`X-API-Key`) |

---

## ⚙️ Configuration

Environment variables (all optional — see `.env.example`):

| Variable | Purpose |
|---|---|
| `PORT` | Server port (default 5000) |
| `REMOTE_API_KEY` | Enables the authenticated `/api/remote/*` endpoints |
| `DISCORD_BOT_TOKEN` | Enables the Discord bot |
| `DISCORD_CHANNEL_ID` | Channel for Discord price alerts |

**Change refresh interval:** in `app/scheduler.py`, change `minutes=5`.
**Add/remove tickers:** edit the `TIERS` dictionary in `app/config.py`.

## 🧪 Development

```bash
pip install -r requirements.txt pytest flake8
pytest -q            # run the test suite (no network needed)
flake8 . --select=E9,F63,F7,F82   # what CI enforces
```

Set `SKIP_STARTUP_FETCH=1` to import/run the app without background
data-fetching threads (used by the tests). CI (GitHub Actions) runs the
lint and the test suite on every push.

---

## ⚠️ Disclaimer

This application is for **informational tracking purposes only**. It does not constitute financial, legal, or investment advice. Data is sourced from Yahoo Finance and may be delayed 15–20 minutes. Always verify with your broker's live feed before making any investment decisions. Consult a licensed financial advisor.
