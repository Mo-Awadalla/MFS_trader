"""Acquire bounded public settlement evidence and native pre/post quote windows."""

import argparse
import gzip
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

from research_scout.fetch_bybit_funding_20261002 import request_payload
from research_scout.prepare_single_funding_20261002 import OUT, ROOT, sha


def fetch_payment(event, cap):
    target = event["settlement_ns"]//1_000_000
    params = {"category": "linear", "symbol": event["symbol"], "startTime": target-1, "endTime": target+1, "limit": 3}
    path = OUT/"payments"/f"{event['date']}_{event['hour']}_{event['symbol']}.json"
    if path.exists():
        return json.loads(path.read_text())
    record = {k: event[k] for k in ("date", "hour", "symbol")}
    record.update(url="https://api.bybit.com/v5/market/funding/history", params=params, complete=False, authenticated=False)
    session = requests.Session()
    session.trust_env = False
    try:
        with session.get(record["url"], params=params, stream=True, allow_redirects=False, timeout=(15, 45)) as response:
            record["http_status"] = response.status_code
            content = bytearray()
            for block in response.iter_content(8192):
                content.extend(block)
                if len(content) > cap:
                    raise ValueError("Frozen response cap exceeded")
            record["response_sha256"] = hashlib.sha256(content).hexdigest()
            record["response_body"] = content.decode(errors="replace")
            response.raise_for_status()
            assert response.status_code == 200
        payload = json.loads(content)
        assert payload["retCode"] == 0, payload.get("retMsg")
        matching = [row for row in payload["result"]["list"] if row["symbol"] == event["symbol"] and int(row["fundingRateTimestamp"]) == target]
        assert len(matching) == 1, "No unique realized funding record at the target"
        record.update(complete=True, funding_rate=matching[0]["fundingRate"], funding_time_ms=target)
    except Exception as error:
        record.update(error_type=type(error).__name__, error=str(error))
    path.write_text(json.dumps(record, indent=2)+"\n")
    return record


def fetch_native(job, cap):
    path = OUT/"native"/f"{job['date']}_{job['hour']}.ndjson.gz"
    sidecar = path.with_suffix(path.suffix+".json")
    if sidecar.exists():
        record = json.loads(sidecar.read_text())
        if record["complete"]:
            assert sha(path) == record["compressed_sha256"]
        return record
    params = {"from": job["date"], "offset": job["offset"], "sliceSize": job["slice_minutes"],
              "filters": json.dumps([{"channel": c, "symbols": job["symbols"]} for c in ("tickers", "orderbook.1")])}
    record = {**job, "params": params, "path": str(path.relative_to(ROOT)), "complete": False, "authenticated": False}
    try:
        payload = request_payload("https://api.tardis.dev/v1/data-feeds/bybit", cap, params)
        assert payload.strip()
        compressed = gzip.compress(payload, compresslevel=3, mtime=0)
        with path.open("xb") as stream:
            stream.write(compressed)
        record.update(complete=True, decoded_bytes=len(payload), compressed_bytes=len(compressed),
                      decoded_sha256=hashlib.sha256(payload).hexdigest(), compressed_sha256=sha(path))
    except Exception as error:
        record.update(error_type=type(error).__name__, error=str(error))
    sidecar.write_text(json.dumps(record, indent=2)+"\n")
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("pilot", "payments", "native"))
    args = parser.parse_args()
    spec = json.loads((OUT/"specification.json").read_text())
    assert sha(OUT/"events.parquet") == spec["events_sha256"]
    events = pd.read_parquet(OUT/"events.parquet").sort_values(["date", "hour", "symbol"]).to_dict("records")
    (OUT/"payments").mkdir(exist_ok=True)
    (OUT/"native").mkdir(exist_ok=True)
    freeze = OUT/"acquisition_implementation.json"
    current = {"specification_sha256": sha(OUT/"specification.json"),
               "code_sha256": {p: sha(ROOT/p) for p in ("research_scout/fetch_single_funding_20261002.py", "research_scout/fetch_bybit_funding_20261002.py")}}
    if freeze.exists():
        assert json.loads(freeze.read_text()) == current
    else:
        freeze.write_text(json.dumps(current, indent=2)+"\n")
    if args.mode in ("pilot", "payments"):
        chosen = events[:1] if args.mode == "pilot" else events
        if args.mode == "payments":
            pilot = json.loads((OUT/"payment_pilot.json").read_text())
            assert pilot["complete"], "Do not repeat a failed/denied public API pilot across symbols"
        rows = []
        for event in chosen:
            row = fetch_payment(event, spec["download"]["funding_history_response_cap"])
            rows.append(row)
            print(json.dumps({k: row.get(k) for k in ("date", "hour", "symbol", "complete", "http_status", "funding_rate", "error")}), flush=True)
            if row.get("http_status") in (403, 429):
                break
            time.sleep(0.2)
        output = OUT/("payment_pilot.json" if args.mode == "pilot" else "payment_manifest.json")
        output.write_text(json.dumps(rows[0] if args.mode == "pilot" else {"files": rows, "expected_events": len(events), "complete": len(rows) == len(events) and all(r["complete"] for r in rows)}, indent=2)+"\n")
        return
    jobs = spec["download"]["jobs"]
    assert len(jobs)*spec["download"]["per_file_decoded_cap"] <= spec["download"]["aggregate_decoded_cap"]
    rows = []
    with ThreadPoolExecutor(max_workers=spec["download"]["workers"]) as pool:
        pending = [pool.submit(fetch_native, job, spec["download"]["per_file_decoded_cap"]) for job in jobs]
        for task in as_completed(pending):
            row = task.result()
            rows.append(row)
            manifest = {"files": rows, "expected_files": len(jobs), "complete": len(rows) == len(jobs) and all(r["complete"] for r in rows),
                        "decoded_bytes": sum(r.get("decoded_bytes", 0) for r in rows)}
            (OUT/"native_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
            print(json.dumps({k: row.get(k) for k in ("date", "hour", "complete", "decoded_bytes", "error")}), flush=True)


if __name__ == "__main__":
    main()
