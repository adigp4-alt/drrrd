# Investment Tracker

Live stock dashboard tracking energy, defense, shipping, and tech tickers across 5 investment tiers.

---

## One-Click Launch (Docker — recommended)

> Works on any machine with Docker installed, including cloud VMs and servers.

```bash
git clone https://github.com/adigp4-alt/drrrd
cd drrrd
docker compose up
```

Then open **http://localhost:5000** in your browser.

To run in background (survives terminal close):
```bash
docker compose up -d
```

To stop:
```bash
docker compose down
```

---

## Quick Start (Python — no Docker)

**Requirements:** Python 3.10+

```bash
git clone https://github.com/adigp4-alt/drrrd
cd drrrd
bash run.sh
```

Or manually:
```bash
pip install -r requirements.txt
python3 utopia.py
```

Then open **http://localhost:5000**.

---

## Deploy to a Cloud Server (VPS / EC2 / etc.)

1. SSH into your server
2. Install Docker: https://docs.docker.com/engine/install/
3. Clone and run:
   ```bash
   git clone https://github.com/adigp4-alt/drrrd
   cd drrrd
   docker compose up -d
   ```
4. Open port 5000 in your firewall/security group
5. Access via `http://<your-server-ip>:5000`

To keep it running permanently and restart on reboot, `docker compose up -d` is enough — the `restart: unless-stopped` policy handles it.

---

## Files

| File | Purpose |
|------|---------|
| `utopia.py` | Backend — Flask server, data fetching, scheduler |
| `templates/index.html` | Frontend — dashboard UI |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container image definition |
| `docker-compose.yml` | One-command container launch |
| `run.sh` | Simple shell launcher (no Docker) |
| `data/` | Auto-created — stores price snapshots as CSV |

---

## Notes

- **Live data:** Fetches from Yahoo Finance every 5 minutes. Requires internet access.
- **Demo mode:** If Yahoo Finance is unreachable, realistic mock prices are shown automatically with `(demo)` in the timestamp.
- **Data export:** Use the "Download CSV" button on the dashboard to export all recorded snapshots.
- **Port:** Default is `5000`. Set `PORT=8080` environment variable to change it.
