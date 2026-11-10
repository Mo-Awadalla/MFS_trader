"""Three tiny read-only historical requests. Never emit credentials or raw headers."""
from pathlib import Path
import json
import os
import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
config = dotenv_values(ROOT / ".env")
key = os.getenv("ALPACA_API_KEY") or config.get("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or config.get("APCA_API_KEY_ID")
secret = os.getenv("ALPACA_API_SECRET") or config.get("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or config.get("APCA_API_SECRET_KEY")
report = {"credentials_present": bool(key and secret), "endpoint": "historical data only", "billing_or_subscription_changes": False, "probes": []}
if key and secret:
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    probes = [
        ("bars", "AAPL", {"feed": "sip", "timeframe": "1Min", "start": "2023-01-04T14:30:00Z", "end": "2023-01-04T14:35:00Z", "limit": 10}),
        ("quotes", "AAPL", {"feed": "sip", "start": "2023-01-04T14:30:00Z", "end": "2023-01-04T14:30:01Z", "limit": 10}),
        ("trades", "AAPL", {"feed": "sip", "start": "2023-01-04T14:30:00Z", "end": "2023-01-04T14:30:01Z", "limit": 10}),
    ]
    for kind, symbol, params in probes:
        result = {"kind": kind, "symbol": symbol, "feed": "sip", "historical_date": "2023-01-04"}
        try:
            response = requests.get(f"https://data.alpaca.markets/v2/stocks/{symbol}/{kind}", headers=headers, params=params, timeout=20)
            result["http_status"] = response.status_code
            payload = response.json()
            rows = payload.get(kind) or []
            result["rows_returned"] = len(rows)
            result["sample_fields"] = sorted(rows[0]) if rows else []
            result["more_pages"] = bool(payload.get("next_page_token"))
            if not response.ok:
                result["provider_error_code"] = payload.get("code")
        except Exception as e:
            result["error_type"] = type(e).__name__
        report["probes"].append(result)
out = ROOT / "research_scout/data_gap_audit_20260907/historical_sip_probe.json"
out.parent.mkdir(exist_ok=True)
with out.open("x", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
print(json.dumps(report, indent=2))
