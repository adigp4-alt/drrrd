# Deploying to Render

The repo ships a working `render.yaml`, so Render provisions the service for
you. Total time is about five minutes, and everything below happens in the
Render dashboard.

---

## Step 1 — Create the service

1. Sign in at [dashboard.render.com](https://dashboard.render.com)
2. **New → Blueprint**
3. Connect the GitHub repo `adigp4-alt/drrrd`
4. Render reads `render.yaml` and shows a service called **iran-tracker**
5. Click **Apply**

The first build takes a few minutes (it installs pandas, scikit-learn and
statsmodels). When it finishes you get a URL like
`https://iran-tracker-xxxx.onrender.com` — open `/foresight` on that URL from
your phone or laptop.

> On the free plan the service sleeps after 15 minutes idle, so the first visit
> after a nap takes ~30 seconds to wake. That is normal, not a failure.

---

## Step 2 — Add your Anthropic API key (optional)

Without this the forecast board still works — it runs the statistical engine
alone and shows a **quant-only mode** badge. Add the key to turn on the Claude
catalyst overlay:

1. Your service → **Environment** → **Add Environment Variable**
2. Key `ANTHROPIC_API_KEY`, value your key from
   [console.anthropic.com](https://console.anthropic.com)
3. **Save** — the service restarts automatically

The key is only ever read server-side. It is never sent to the browser.

---

## Step 3 — Keep the accuracy history (recommended)

**This is the one step that is easy to skip and annoying to discover later.**

Render's free plan has an ephemeral filesystem, so by default the SQLite
database is wiped on **every redeploy** — the forecast ledger's accuracy history
restarts from zero each time. The app works fine either way; you just lose the
track record, which is the whole point of the Accuracy tab.

To fix it, attach a free Postgres database:

1. **New → Postgres**, name it `iran-tracker-db`, choose the **Free** plan, create it
2. Open the new database and copy its **Internal Database URL**
3. Go back to your web service → **Environment** → **Add Environment Variable**
4. Key `DATABASE_URL`, value the URL you copied
5. **Save**

The app detects `DATABASE_URL` on boot, creates its schema automatically, and
switches all storage to Postgres. Nothing else to configure.

> Render allows one free Postgres per account, and free databases expire after a
> limited period — check the current terms in the dashboard. If you would rather
> not use Postgres, the alternative is a persistent disk with `DATA_DIR` set to
> its mount path, but disks require a paid instance type.

### Doing it automatically instead

If you would rather have the blueprint provision Postgres for you, replace the
commented blocks in `render.yaml` with this and re-apply the blueprint. Only do
this if your account does not already have a free Postgres, or the apply fails:

```yaml
    envVars:
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: DATABASE_URL
        fromDatabase:
          name: iran-tracker-db
          property: connectionString

databases:
  - name: iran-tracker-db
    plan: free
```

---

## Step 4 — First run

Open `/foresight` and:

1. Click **Scan market** — the first real test of the live market-data path.
   This was never exercisable in development because Yahoo Finance is blocked
   from the build sandbox, so if anything is going to misbehave, it is here.
2. Go to the **Accuracy** tab and click **Run backtest**. This replays the
   engine across historical sessions and tells you whether it has any measurable
   skill. Expect a small or zero edge — next-session direction is close to
   noise, and the board is built to admit that rather than hide it.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| First visit hangs ~30s | Free-plan cold start. Normal. |
| Board is empty after a scan | All three price providers failed. Open `/foresight/api/diagnostics` on the deployed URL — it probes each layer and names the cause. Yahoo throttles datacenter IPs hard, so `MARKET_DATA_SOURCE=stooq` is the usual workaround on a cloud host. |
| **quant-only mode** badge | `ANTHROPIC_API_KEY` is not set — see Step 2. |
| Accuracy tab empty after redeploy | Storage is ephemeral — see Step 3. |
| Scan times out | Gunicorn's timeout is already raised to 300s in `render.yaml`. If you changed the start command, put `--timeout 300` back; catalyst scans run web research and exceed the 30s default. |
| Build fails on dependencies | Confirm the build command is `pip install -r requirements.txt`. |

---

## Other hosts

`Procfile` (Railway, Heroku) and `Dockerfile` (any container host) are both in
the repo and use the same environment variables: `ANTHROPIC_API_KEY`,
`DATABASE_URL`, `DATA_DIR`, `PORT`. For Docker, mount a volume at `/data` or set
`DATABASE_URL`, or the ledger is lost when the container is replaced.
