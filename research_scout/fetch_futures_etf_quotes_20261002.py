"""Acquire every selected SPY SIP window, without placing orders or buying data."""

import json
import os
import time
from datetime import UTC, datetime

import pandas as pd
import requests
from dotenv import dotenv_values

from data.alpaca_l1 import AlpacaHistoricalL1Client
from research_scout.screen_futures_etf_20261002 import OUT, ROOT, sha


def main():
    results = json.loads((OUT/"source_screen_results.json").read_text())
    assert sha(OUT/"es_impulses.parquet") == results["impulses_sha256"]
    events = pd.read_parquet(OUT/"es_impulses.parquet").sort_values(["date", "decision_ns"]).to_dict("records")
    jobs = []
    for event in events:
        start, end = event["decision_ns"]-5_000_000_000, event["decision_ns"]+30_000_000_000
        if jobs and jobs[-1]["date"] == event["date"] and start <= jobs[-1]["end_ns"]:
            jobs[-1]["end_ns"] = max(jobs[-1]["end_ns"], end)
            jobs[-1]["decision_ns"].append(event["decision_ns"])
        else:
            jobs.append({"date": event["date"], "start_ns": start, "end_ns": end, "decision_ns": [event["decision_ns"]], "window_id": len(jobs)})
    plan = {"created_at_utc": datetime.now(UTC).isoformat(), "symbol": "SPY", "feed": "sip", "jobs": jobs,
            "impulses_sha256": results["impulses_sha256"], "window": "Decision minus 5 seconds through plus 30 seconds; merge overlapping windows only. Fetch every frozen event, with no return-based pruning.",
            "per_file_cap": 32_000_000, "aggregate_cap": 32_000_000*len(jobs), "max_pages": 16, "max_seconds": 180,
            "code_sha256": {p: sha(ROOT/p) for p in ["research_scout/fetch_futures_etf_quotes_20261002.py", "data/alpaca_l1.py"]},
            "orders_submitted": False, "paid_fallback": False, "billing_changed": False,
            "historical_receipt_verified": False, "future_returns_evaluated": False}
    plan_path = OUT/"quote_acquisition_plan.json"
    if plan_path.exists():
        previous = json.loads(plan_path.read_text())
        for key in ("jobs", "code_sha256", "impulses_sha256"):
            assert previous[key] == plan[key]
    else:
        plan_path.write_text(json.dumps(plan, indent=2)+"\n")
    config = dotenv_values(ROOT/".env")
    key = os.getenv("ALPACA_API_KEY") or config.get("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or config.get("APCA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET") or config.get("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or config.get("APCA_API_SECRET_KEY")
    session = requests.Session()
    session.trust_env = False
    client = AlpacaHistoricalL1Client(key, secret, feed="sip", session=session, max_total_bytes=plan["per_file_cap"], max_duration_seconds=plan["max_seconds"])
    assert client.is_available(), "Historical data credentials unavailable"
    (OUT/"quotes").mkdir(exist_ok=True)
    rows = []
    for job in jobs:
        path = OUT/"quotes"/f"{job['date']}_{job['window_id']:03d}_SPY.parquet"
        sidecar = path.with_suffix(".json")
        if sidecar.exists():
            row = json.loads(sidecar.read_text())
            if row["complete"]:
                assert sha(path) == row["sha256"]
        else:
            row = {**job, "symbol": "SPY", "path": str(path.relative_to(ROOT)), "complete": False}
            try:
                start, end = pd.Timestamp(job["start_ns"], tz="UTC"), pd.Timestamp(job["end_ns"], tz="UTC")
                response = client.download_quotes("SPY", start, end, max_pages=plan["max_pages"])
                frame = response.data
                assert response.metadata["pagination_complete"] and len(frame) > 0
                assert frame.timestamp.is_monotonic_increasing and frame.timestamp.between(start, end, inclusive="both").all()
                assert frame.symbol.eq("SPY").all() and not path.exists()
                frame.to_parquet(path, index=False)
                row.update(complete=True, sha256=sha(path), rows=len(frame), metadata=response.metadata)
            except Exception as error:
                row.update(error_type=type(error).__name__, error="Bounded historical quote acquisition failed; no quote or return substitution.")
            sidecar.write_text(json.dumps(row, indent=2)+"\n")
        rows.append(row)
        manifest = {"files": rows, "expected_files": len(jobs), "complete": len(rows) == len(jobs) and all(r["complete"] for r in rows),
                    "response_byte_upper_bound": sum(r.get("metadata", {}).get("response_bytes", plan["per_file_cap"]) for r in rows),
                    "quote_plan_sha256": sha(plan_path), "orders_submitted": False, "billing_changed": False}
        assert manifest["response_byte_upper_bound"] <= plan["aggregate_cap"]
        (OUT/"quote_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
        print(json.dumps({k: row.get(k) for k in ("date", "window_id", "complete", "rows", "error")}), flush=True)
        time.sleep(.2)


if __name__ == "__main__":
    main()
