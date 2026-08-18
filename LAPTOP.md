# Running it from your own laptop

You don't need Render. The app runs on your machine and your phone connects to
it over your home network — and this route has one significant advantage.

## Why this may fix the empty board

Yahoo Finance aggressively throttles and blocks **datacenter IP ranges**, which
is what a Render server has. Your home internet connection is a residential IP
and is not treated the same way. If the deployed board comes back empty because
Yahoo refuses the host, **the same code on your laptop will very likely just
work.** That is the single best reason to try this path.

---

## Step 1 — Start it (2 minutes, once)

```bash
git clone https://github.com/adigp4-alt/drrrd.git
cd drrrd
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Leave that terminal open — closing it stops the app. Then open
<http://localhost:5000/foresight> on the laptop and press **Scan market**. If
numbers appear, the data path works and the rest is just reaching it from your
phone.

**To enable the Claude catalyst layer**, set the key before `python main.py`:

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # Windows: set ANTHROPIC_API_KEY=sk-ant-...
```

---

## Step 2 — Reach it from your phone

Both devices must be on the **same WiFi**. Find your laptop's local address:

| OS | Command | Looks like |
|---|---|---|
| macOS | `ipconfig getifaddr en0` | `192.168.1.24` |
| Linux | `hostname -I \| awk '{print $1}'` | `192.168.1.24` |
| Windows | `ipconfig` → *IPv4 Address* | `192.168.1.24` |

On your phone, open `http://192.168.1.24:5000/foresight` (your number, not
that one).

`main.py` already listens on all interfaces, so no code change is needed. If it
doesn't load, the cause is almost always the laptop's firewall — macOS asks the
first time (choose **Allow**); on Windows, tick *Private networks* in the
Windows Defender prompt.

### What you get, and what you don't

Over plain `http://` on a LAN address, browsers withhold some app features,
because **service workers require a secure context** (HTTPS, or `localhost`):

| | LAN over `http://` | With HTTPS (Step 3) |
|---|---|---|
| Works on the phone | ✅ | ✅ |
| Full-screen from home screen (iOS) | ✅ | ✅ |
| Chrome/Android **Install app** button | ❌ | ✅ |
| Offline launch / cached board | ❌ | ✅ |

So on iOS you can still *Share → Add to Home Screen* and it opens full-screen —
it just won't work offline. That's fine if you only use it at home with the
laptop running.

---

## Step 3 — Optional: a real HTTPS address

This gets you the complete app — the Install button, offline launch — and works
**anywhere**, not just on your WiFi. It puts a public HTTPS URL in front of the
app still running on your laptop.

```bash
# macOS:  brew install cloudflared
# Windows/Linux: https://github.com/cloudflare/cloudflared/releases

cloudflared tunnel --url http://localhost:5000
```

It prints a URL like `https://random-words-1234.trycloudflare.com`. Open
`<that-url>/foresight` on your phone and install it as an app.

⚠️ **That URL is public while the tunnel runs** — anyone with the link reaches
your app, and the app has no login. Don't post it anywhere, and stop the tunnel
with `Ctrl-C` when you're done. The address changes each time you start it,
which is inconvenient but also limits the exposure.

---

## Keeping your data

By default the forecast ledger goes to `data/tracker.db` next to the code, and
it persists between restarts automatically — no configuration needed. This is
actually more durable than the Render free tier, where the disk is wiped on
every redeploy.

To put it somewhere specific:

```bash
export DATA_DIR=~/foresight-data
```

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Phone can't connect | Different WiFi network, or laptop firewall blocking. Check the laptop can reach `http://localhost:5000` first. |
| Works on laptop, not phone | Firewall. macOS: System Settings → Network → Firewall → Options. Windows: allow Python on *Private networks*. |
| Board empty on the laptop too | Run `python diagnose.py` — it prints a full report naming the cause, including yfinance's own internal log. Paste the output when reporting. |
| No **Install app** button | Expected over plain `http://` — see Step 3. |
| `command not found: python3` | Install Python 3.10+ from [python.org](https://www.python.org/downloads/). |
| App stops when you close the laptop | Expected — it runs only while that terminal is open and the machine is awake. |

---

## Which path should you use?

- **Just want to see if the forecasts work at all** → Step 1, on the laptop.
- **Want it on your phone at home** → Steps 1–2. Simplest, no extra tools.
- **Want the full installable app, or access away from home** → add Step 3.
- **Want it always on, without your laptop running** → that's what the Render
  deployment is for; see [DEPLOY.md](DEPLOY.md).
