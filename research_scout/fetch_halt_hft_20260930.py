"""Bounded read-only SIP acquisition for the frozen halt development cohort."""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from dotenv import dotenv_values

from data.alpaca_l1 import AlpacaHistoricalL1Client
from research.crypto_symbol_cache import digest
from research_scout.prepare_halt_hft_20260930 import OUT, ROOT


def acquire(event, kind, key, secret, limits):
    folder = OUT / "raw" / event["date"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{event['symbol']}_{kind}.parquet"
    sidecar = path.with_suffix(".json")
    if sidecar.exists():
        record = json.loads(sidecar.read_text())
        if path.exists() and digest(path) == record.get("sha256"):
            return record
        if record.get("complete") is False:
            return record
        raise RuntimeError("Cached source hash mismatch")
    session = requests.Session()
    session.trust_env = False
    client = AlpacaHistoricalL1Client(key, secret, feed="sip", session=session,
                                    max_total_bytes=limits["per_file_max_bytes"],
                                    max_duration_seconds=limits["max_seconds_per_file"])
    record = {"date": event["date"], "symbol": event["symbol"], "kind": kind,
              "path": str(path.relative_to(ROOT)), "complete": False}
    try:
        start = pd.Timestamp(event["start_ns"], tz="UTC")
        end = pd.Timestamp(event["end_ns"], tz="UTC")
        method = client.download_quotes if kind == "quotes" else client.download_trades
        result = method(event["symbol"], start, end, max_pages=limits["max_pages"])
        frame = result.data
        assert result.metadata["pagination_complete"]
        assert frame.timestamp.is_monotonic_increasing
        assert frame.timestamp.between(start, end, inclusive="both").all()
        frame.to_parquet(path, index=False)
        record.update(complete=True, sha256=digest(path), rows=len(frame), metadata=result.metadata)
    except Exception as exc:
        # Do not serialize potentially credential-bearing request objects.
        record.update(error_type=type(exc).__name__, error="Historical acquisition incomplete; no trading result inferred.")
    finally:
        session.close()
    sidecar.write_text(json.dumps(record, indent=2)+"\n")
    time.sleep(0.8)
    return record


def main():
    spec = json.loads((OUT/"specification.json").read_text())
    assert digest(OUT/"cohort.parquet") == spec["source_sha256"]["cohort.parquet"]
    panel = pd.read_parquet(OUT/"cohort.parquet")
    panel = panel.loc[panel.date.str.startswith(spec["download"]["initial_year"])]
    config = dotenv_values(ROOT/".env")
    key = os.getenv("ALPACA_API_KEY") or config.get("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or config.get("APCA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET") or config.get("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or config.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("Existing historical data credentials missing")
    records, total = [], 0
    # Submit at most one two-file event batch at a time, so the cumulative cap is enforced.
    with ThreadPoolExecutor(max_workers=2) as pool:
        for event in panel.to_dict("records"):
            if total+2*spec["download"]["per_file_max_bytes"] > spec["download"]["max_total_response_bytes"]:
                raise RuntimeError("Frozen cumulative response cap would be exceeded")
            futures = [pool.submit(acquire, event, kind, key, secret, spec["download"]) for kind in ["quotes", "trades"]]
            for future in as_completed(futures):
                record = future.result()
                total += record.get("metadata", {}).get("response_bytes", spec["download"]["per_file_max_bytes"])
                records.append(record)
            manifest = {"complete": len(records) == 2*len(panel) and all(r["complete"] for r in records),
                        "expected_files": 2*len(panel), "files": records, "response_byte_upper_bound": total,
                        "specification_sha256": digest(OUT/"specification.json"),
                        "billing_changed": False, "orders_submitted": False}
            (OUT/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
            print(json.dumps({"date": event["date"], "symbol": event["symbol"],
                              "files": len(records), "expected": 2*len(panel),
                              "incomplete": sum(not r["complete"] for r in records), "bytes_upper": total}), flush=True)


if __name__ == "__main__":
    main()
