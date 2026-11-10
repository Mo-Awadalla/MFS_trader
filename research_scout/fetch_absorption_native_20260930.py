"""Recover native transaction clocks for ALL frozen execution targets."""

from __future__ import annotations

import gzip
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import pandas as pd
import requests

from research.crypto_symbol_cache import digest
from research_scout.run_absorption_hft_20260930 import OUT as STUDY
from research_scout.run_absorption_hft_20260930 import ROOT

OUT = STUDY / "native_transaction_clock"
TOTAL_CAP, SLICE_CAP = 4_000_000_000, 64_000_000
TOTAL, LOCK = 0, threading.Lock()


def reserve(amount):
    global TOTAL
    with LOCK:
        TOTAL += amount
        if TOTAL > TOTAL_CAP:
            raise ValueError("Frozen cumulative decoded-byte cap exceeded")


def fetch(job):
    path = OUT / "raw" / f"{job['date']}_{job['symbol']}_{job['minute']:04d}_{job['slice_minutes']}.ndjson.gz"
    meta_path = path.with_suffix(path.suffix + ".json")
    if path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        assert digest(path) == meta["compressed_sha256"]
        reserve(meta["decoded_bytes"])
        return meta
    session = requests.Session()
    session.trust_env = False
    params = {"from": job["date"], "offset": job["minute"], "sliceSize": job["slice_minutes"],
              "filters": json.dumps([{"channel": "depth", "symbols": [job["symbol"].lower()]}])}
    for attempt in range(4):
        try:
            with session.get("https://api.tardis.dev/v1/data-feeds/binance-futures", params=params,
                             headers={"Accept-Encoding": "gzip"}, stream=True, timeout=(15, 60)) as response:
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    reserve(len(chunk))
                    size += len(chunk)
                    if size > SLICE_CAP:
                        raise ValueError("Native depth slice exceeded frozen cap")
                    chunks.append(chunk)
            payload = b"".join(chunks)
            break
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
            if attempt == 3:
                raise
            time.sleep(min(20, 2 ** attempt))
    encoded = gzip.compress(payload, compresslevel=3, mtime=0)
    path.write_bytes(encoded)
    meta = {**job, "path": str(path.relative_to(ROOT)), "decoded_bytes": len(payload),
            "compressed_bytes": len(encoded), "decoded_sha256": hashlib.sha256(payload).hexdigest(),
            "compressed_sha256": hashlib.sha256(encoded).hexdigest(), "authenticated": False}
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def plan():
    records, jobs = [], []
    hashes = {}
    for symbol in ("BTCUSDT", "SOLUSDT"):
        for file in sorted((STUDY / symbol / "panels").glob("*_quotes.parquet")):
            hashes[str(file.relative_to(ROOT))] = digest(file)
            panel = pd.read_parquet(file)
            selected = panel.loc[panel.clock_kind.eq("exchange")].drop_duplicates("target_us")
            minutes = set()
            for row in selected.to_dict("records"):
                records.append({"symbol": symbol, "date": file.stem[:10], "target_us": int(row["target_us"]),
                                "quote_local_us": int(row["quote_local_us"]), "quote_event_us": int(row["quote_exchange_us"])})
                low = min(row["quote_local_us"], row["quote_exchange_us"]) // 60000000
                high = (row["target_us"] + 1000000) // 60000000
                minutes.update(range(int(low), int(high) + 1))
            ordered = sorted(minutes)
            while ordered:
                start = stop = ordered.pop(0)
                while ordered and ordered[0] == stop + 1 and ordered[0] - start < 10:
                    stop = ordered.pop(0)
                jobs.append({"symbol": symbol, "date": file.stem[:10], "minute": start, "slice_minutes": stop - start + 1})
    return {"created_at_utc": datetime.now(UTC).isoformat(), "targets": records, "jobs": jobs,
            "quote_panel_sha256": hashes, "total_decoded_byte_cap": TOTAL_CAP, "per_slice_decoded_byte_cap": SLICE_CAP,
            "selection": "Every unique physical execution target requested by the original eight rules and all five stresses, regardless of quote age, reached/unreached status, fill or P&L. Union of source-state and target minutes plus one-second successor context, merged into <=10-minute slices. This supersedes the insufficient old-age-only acquisition scope.",
            "purpose": "Match the normalized source quote to its exact raw receipt, distinguish native event-publication E from transaction T, replay sequenced deltas through target T, retain unknown initial deeper depth, sequence gaps and timestamp ties. Do not rewrite original results or alter signals, orders, costs or sizing.",
            "storage": "Compressed raw NDJSON in the existing workspace. Pilot implies roughly2.2GB decoded across2311 minutes; bounded at4GB including retries and cached decoded sizes. Gzip reduces saved disk and network size.",
            "authentication": "None. Public first-of-month historical samples only, no paid fallback, no orders."}


def main():
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    spec_path = OUT / "acquisition_specification.json"
    if not spec_path.exists():
        spec_path.write_text(json.dumps(plan(), indent=2) + "\n")
    spec = json.loads(spec_path.read_text())
    for path, sha in spec["quote_panel_sha256"].items():
        assert digest(ROOT / path) == sha
    print(f"Frozen {len(spec['targets']):,} unique execution targets; {len(spec['jobs'])} raw slices / "
          f"{sum(j['slice_minutes'] for j in spec['jobs'])} minutes", flush=True)
    results, errors, last = [], [], time.monotonic()
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = {pool.submit(fetch, job): job for job in spec["jobs"]}
        for task in as_completed(jobs):
            try:
                results.append(task.result())
            except Exception as exc:
                errors.append({**jobs[task], "error": str(exc)})
            if time.monotonic() - last >= 25 or len(results) + len(errors) == len(jobs):
                progress = {"completed_slices": len(results), "planned_slices": len(jobs), "errors": errors,
                            "decoded_bytes_including_retries": TOTAL,
                            "compressed_saved_bytes": sum(r["compressed_bytes"] for r in results)}
                (OUT / "download_progress.json").write_text(json.dumps(progress, indent=2) + "\n")
                print(json.dumps(progress), flush=True)
                last = time.monotonic()
    result = {"complete": not errors and len(results) == len(jobs), "files": results, "errors": errors,
              "decoded_bytes_including_retries": TOTAL}
    (OUT / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
