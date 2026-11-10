"""Bounded public raw-depth recovery for every age-rejected target, not selected P&L."""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import pandas as pd
import requests

from research_scout.run_absorption_hft_20260930 import OUT as STUDY
from research_scout.run_absorption_hft_20260930 import ROOT

OUT = STUDY / "depth_admission"
TOTAL_CAP, SLICE_CAP = 400_000_000, 12_000_000
TOTAL, LOCK = 0, threading.Lock()


def fetch(item):
    global TOTAL
    path = OUT / "raw" / f"{item['date']}_{item['symbol']}_{item['minute']:04d}.ndjson"
    if path.exists():
        payload = path.read_bytes()
        with LOCK:
            TOTAL += len(payload)
            if TOTAL > TOTAL_CAP:
                raise ValueError("Cached and downloaded raw-depth bytes exceed cap")
    else:
        session = requests.Session()
        session.trust_env = False
        params = {"from": item["date"], "offset": item["minute"], "sliceSize": 2,
                  "filters": json.dumps([{"channel": "depth", "symbols": [item["symbol"].lower()]}])}
        for attempt in range(4):
            try:
                with session.get("https://api.tardis.dev/v1/data-feeds/binance-futures", params=params,
                                 headers={"Accept-Encoding": "gzip"}, stream=True, timeout=(15, 60)) as response:
                    response.raise_for_status()
                    chunks, size = [], 0
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        with LOCK:
                            TOTAL += len(chunk)
                            if TOTAL > TOTAL_CAP:
                                raise ValueError("Cumulative public raw-depth byte cap exceeded")
                        if size > SLICE_CAP:
                            raise ValueError("Raw-depth slice cap exceeded")
                        chunks.append(chunk)
                payload = b"".join(chunks)
                break
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
                if attempt == 3:
                    raise
                time.sleep(min(20, 2 ** attempt))
        path.write_bytes(payload)
    return {**item, "path": str(path.relative_to(ROOT)), "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    path = OUT / "specification.json"
    if not path.exists():
        records = []
        for symbol in ("BTCUSDT", "SOLUSDT"):
            for file in sorted((STUDY / symbol / "panels").glob("*_quotes.parquet")):
                panel = pd.read_parquet(file)
                selected = panel.loc[panel.clock_kind.eq("exchange") & panel.exchange_age_us.gt(250000)]
                for row in selected.to_dict("records"):
                    records.append({"date": file.stem[:10], "symbol": symbol, "target_us": int(row["target_us"]),
                                    "quote_local_us": int(row["quote_local_us"]), "quote_exchange_us": int(row["quote_exchange_us"]),
                                    "age_us": int(row["exchange_age_us"])})
        records = pd.DataFrame(records).drop_duplicates(["date", "symbol", "target_us"]).sort_values(["symbol", "date", "target_us"]).to_dict("records")
        jobs = sorted({(r["symbol"], r["date"], min(r["quote_local_us"], r["quote_exchange_us"]) // 60000000) for r in records})
        spec = {"created_at_utc": datetime.now(UTC).isoformat(), "targets": records,
                "jobs": [{"symbol": symbol, "date": day, "minute": int(minute)} for symbol, day, minute in jobs],
                "slice_minutes": 2, "total_decoded_byte_cap": TOTAL_CAP, "per_slice_decoded_byte_cap": SLICE_CAP,
                "selection": "Every execution target in every original rule/scenario whose retained native quote is >250ms old, including targets not reached after a prior unknown. No filtering on P&L or whether it rescues a strategy.",
                "purpose": "Verify that a standing top-five state persisted through sequential raw depth messages, rather than simply loosening quote-age gates. Match cached source capture/native timestamps, require native pu/u continuity through a successor at/after target, no disconnect marker, and no top-five change before target. This remains a feed-state proxy, not proof of live matching-engine fills.",
                "pilot": "First chronological target per instrument; source schema and size check only. The full target set is fixed before retrieval.",
                "authentication": "None. Public first-of-month samples only; no paid fallback.",
                "documentation": "https://docs.tardis.dev/historical-data-details/binance-futures.md"}
        path.write_text(json.dumps(spec, indent=2) + "\n")
    spec = json.loads(path.read_text())
    jobs = spec["jobs"]
    if args.pilot:
        jobs = [next(job for job in jobs if job["symbol"] == symbol) for symbol in ("BTCUSDT", "SOLUSDT")]
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=6) as pool:
        pending = {pool.submit(fetch, job): job for job in jobs}
        for task in as_completed(pending):
            try:
                results.append(task.result())
            except Exception as exc:
                errors.append({**pending[task], "error": str(exc)})
            if len(results) % 20 == 0 or len(results) + len(errors) == len(jobs):
                print(f"Raw depth {len(results)}/{len(jobs)}, {len(errors)} errors, {sum(r['bytes'] for r in results):,} saved bytes", flush=True)
    output = OUT / ("pilot_manifest.json" if args.pilot else "manifest.json")
    output.write_text(json.dumps({"complete": not errors and len(results) == len(jobs), "files": results, "errors": errors}, indent=2) + "\n")
    if args.pilot:
        for item in results:
            lines = (ROOT / item["path"]).read_text().splitlines()
            first = next(line for line in lines if line.strip())
            stamp, raw = first.split(" ", 1)
            value = json.loads(raw)
            data = value.get("data", value)
            print(json.dumps({"symbol": item["symbol"], "bytes": item["bytes"], "records": len(lines),
                              "first_capture": stamp, "stream": value.get("stream"), "fields": list(data),
                              "T": data.get("T"), "E": data.get("E"), "U": data.get("U"), "u": data.get("u"), "pu": data.get("pu")}))


if __name__ == "__main__":
    main()
