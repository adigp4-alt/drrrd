"""Tier configuration and ticker metadata."""

from pathlib import Path

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
SNAPSHOT_CSV = DATA_DIR / "snapshots.csv"
DB_PATH = DATA_DIR / "tracker.db"

TIERS = {
    "T1": {
        "name": "Post-Conflict Reconstruction",
        "difficulty": "Hardest", "horizon": "2-5 Years", "min_capital": "$5,000+",
        "color": "#C0392B",
        "tickers": {
            "SLB": "SLB (Schlumberger)", "HAL": "Halliburton", "BKR": "Baker Hughes",
            "TTE": "TotalEnergies", "KBR": "KBR Inc", "FLR": "Fluor Corp",
            "ACM": "AECOM", "CAT": "Caterpillar",
        },
    },
    "T2": {
        "name": "Defense & Energy Stock Picking",
        "difficulty": "Hard", "horizon": "3-12 Months", "min_capital": "$2,000+",
        "color": "#E67E22",
        "tickers": {
            "LMT": "Lockheed Martin", "RTX": "RTX Corporation", "NOC": "Northrop Grumman",
            "AVAV": "AeroVironment", "ESLT": "Elbit Systems",
            "XOM": "ExxonMobil", "CVX": "Chevron", "COP": "ConocoPhillips",
            "LNG": "Cheniere Energy", "VG": "Venture Global",
        },
    },
    "T3": {
        "name": "Israeli Equities & Cybersecurity",
        "difficulty": "Medium", "horizon": "3-12 Months", "min_capital": "$1,000+",
        "color": "#2E86C1",
        "tickers": {
            "EIS": "iShares MSCI Israel ETF", "CHKP": "Check Point Software",
            "WIX": "Wix.com", "TEVA": "Teva Pharmaceutical",
            "CRWD": "CrowdStrike", "PANW": "Palo Alto Networks",
            "ZS": "Zscaler", "LDOS": "Leidos", "CIBR": "First Trust Cyber ETF",
        },
    },
    "T4": {
        "name": "Tanker & Shipping (TACTICAL)",
        "difficulty": "Moderate", "horizon": "Days-Weeks", "min_capital": "$500+",
        "color": "#8E44AD",
        "tickers": {
            "BWET": "Breakwave Tanker ETF", "FRO": "Frontline",
            "INSW": "Intl Seaways", "STNG": "Scorpio Tankers", "DHT": "DHT Holdings",
        },
    },
    "T5": {
        "name": "Broad Sector ETFs",
        "difficulty": "Easiest", "horizon": "Ongoing", "min_capital": "Any",
        "color": "#27AE60",
        "tickers": {
            "ITA": "iShares Aerospace & Defense", "XLE": "Energy Select SPDR",
            "XOP": "SPDR Oil & Gas E&P", "SHLD": "Global X Defense ETF",
        },
    },
}

ALL_TICKERS = []
TICKER_META = {}
for tid, tdata in TIERS.items():
    for sym, name in tdata["tickers"].items():
        ALL_TICKERS.append(sym)
        TICKER_META[sym] = {"tier": tid, "name": name, "color": tdata["color"]}
