import requests
import time
import json

time.sleep(3) # Wait for Flask and Data Fetcher threads
try:
    print("Testing Screener API...")
    r = requests.get('http://127.0.0.1:5000/screener/api/data')
    j = r.json()
    print(f"Screener Status: {r.status_code}")
    print(f"Assets Found: {len(j)}")
    if len(j) > 0:
        print(f"Sample Consensus: {j[0].get('consensus', 'MISSING')}")
        print(f"Sample Conviction: {j[0].get('confidence', 'MISSING')}")
        print(f"Sample Rationale: {list(j[0].get('ai_rationale', {}).keys())[:2]}")
        
    print("\nTesting Analysis API (LMT)...")
    r2 = requests.get('http://127.0.0.1:5000/api/analysis/LMT')
    j2 = r2.json()
    print(f"Analysis Status: {r2.status_code}")
    if r2.status_code == 200:
        print(f"Prophet Accuracy: {j2.get('prophet_forecast', {}).get('accuracy_score', 'MISSING')}")
        print(f"LMT Rationale: {list(j2.get('ai_rationale', {}).keys())[:2]}")
        
except Exception as e:
    print(f"Error: {e}")
