# Iran Investment Tracker — Live Web Dashboard

A full-stack web application that automatically tracks all 36 tickers from the Iran Regime Change Investment Plan. Live prices, auto-refresh, alerts, CSV export, and a production-ready dashboard.

---

## 🚀 Deploy in Under 5 Minutes

Pick any platform below. **Render.com is the easiest** (free tier, no credit card).

---

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
