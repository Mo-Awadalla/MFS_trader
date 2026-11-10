"""Acquire only the outcome windows selected before observing their returns."""

import gzip
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from research_scout.prepare_wide_tick_20260930 import OUT, ROOT

TOTAL = 0
LOCK = threading.Lock()


def reserve(size, cap):
    global TOTAL
    with LOCK:
        TOTAL += size
        if cap < TOTAL:
            raise ValueError("Frozen total acquisition bound exceeded")


def fetch(job, config):
    path = OUT / "replay_native" / f"{job['date']}_{job['offset']:04d}.ndjson.gz"
    sidecar = path.with_suffix(path.suffix+".json")
    if sidecar.exists():
        old = json.loads(sidecar.read_text())
        if old["complete"]:
            assert hashlib.sha256(path.read_bytes()).hexdigest() == old["compressed_sha256"]
            reserve(old["decoded_bytes"], config["total_decoded_cap"])
        return old
    params = {"from": job["date"], "offset": job["offset"], "sliceSize": config["slice_minutes"],
              "filters": json.dumps([{"channel": name, "symbols": [s.lower() for s in job["symbols"]]} for name in config["channels"]])}
    record = {**job, "params": params, "path": str(path.relative_to(ROOT)), "complete": False, "authenticated": False}
    session = requests.Session()
    session.trust_env = False
    try:
        with session.get("https://api.tardis.dev/v1/data-feeds/binance-futures", params=params,
                         headers={"Accept-Encoding": "gzip"}, stream=True, timeout=(15, 60), allow_redirects=False) as response:
            record["http_status"] = response.status_code
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("Unexpected public historical response")
            blocks, size = [], 0
            for block in response.iter_content(65536):
                reserve(len(block), config["total_decoded_cap"])
                size += len(block)
                if size > config["per_slice_decoded_cap"]:
                    raise ValueError("Frozen per-slice acquisition bound exceeded")
                blocks.append(block)
            payload = b"".join(blocks)
        if not payload.strip():
            raise ValueError("Empty selected replay source")
        encoded = gzip.compress(payload, compresslevel=3, mtime=0)
        path.write_bytes(encoded)
        record.update(complete=True, decoded_bytes=len(payload), compressed_bytes=len(encoded),
                      decoded_sha256=hashlib.sha256(payload).hexdigest(), compressed_sha256=hashlib.sha256(encoded).hexdigest())
    except Exception as error:
        record.update(error_type=type(error).__name__, error=str(error))
    sidecar.write_text(json.dumps(record, indent=2)+"\n")
    return record


def main():
    spec_path = OUT / "replay_specification.json"
    spec = json.loads(spec_path.read_text())
    assert hashlib.sha256((OUT / "selected.parquet").read_bytes()).hexdigest() == spec["selected_sha256"]
    (OUT / "replay_native").mkdir(exist_ok=True)
    jobs = [{**cohort, "offset": offset} for cohort in spec["cohorts"] for offset in spec["download"]["offsets"]]
    records = []
    with ThreadPoolExecutor(max_workers=spec["download"]["workers"]) as pool:
        tasks = [pool.submit(fetch, job, spec["download"]) for job in jobs]
        for task in as_completed(tasks):
            record = task.result()
            records.append(record)
            manifest = {"files": records, "expected_files": len(jobs),
                        "complete": len(records) == len(jobs) and all(r["complete"] for r in records),
                        "specification_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(),
                        "decoded_bytes_reserved": TOTAL, "orders_submitted": False}
            (OUT / "replay_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
            print(json.dumps({"date": record["date"], "offset": record["offset"], "complete": record["complete"],
                              "files": len(records), "decoded_bytes": record.get("decoded_bytes"), "error": record.get("error")}), flush=True)


if __name__ == "__main__":
    main()
