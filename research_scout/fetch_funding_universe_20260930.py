"""Bounded unauthenticated native full-channel funding slices."""

import gzip
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from research.crypto_symbol_cache import digest
from research_scout.prepare_funding_universe_20260930 import OUT, ROOT

TOTAL = 0
LOCK = threading.Lock()


def reserve(amount, limit):
    global TOTAL
    with LOCK:
        TOTAL += amount
        if limit < TOTAL:
            raise ValueError("Frozen decoded byte cap exceeded")


def fetch(job, config):
    path = OUT/"native"/f"{job['date']}_{job['hour']:02d}.ndjson.gz"
    sidecar = path.with_suffix(path.suffix+".json")
    if sidecar.exists():
        old = json.loads(sidecar.read_text())
        if old["complete"]:
            assert digest(path) == old["compressed_sha256"]
            reserve(old["decoded_bytes"], config["total_decoded_cap"])
        return old
    session = requests.Session()
    session.trust_env = False
    params = {"from": job["date"], "offset": job["hour"]*60-1, "sliceSize": 1,
              "filters": json.dumps([{"channel": "markPrice"}])}
    result = {**job, "path": str(path.relative_to(ROOT)), "complete": False, "authenticated": False}
    try:
        with session.get("https://api.tardis.dev/v1/data-feeds/binance-futures", params=params,
                         headers={"Accept-Encoding": "gzip"}, stream=True, timeout=(15, 60), allow_redirects=False) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("Unexpected native response")
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                reserve(len(chunk), config["total_decoded_cap"])
                size += len(chunk)
                if size > config["per_slice_decoded_cap"]:
                    raise ValueError("Native slice exceeded frozen cap")
                chunks.append(chunk)
            payload = b"".join(chunks)
        if not payload.strip():
            raise ValueError("No source records in scheduled minute")
        encoded = gzip.compress(payload, compresslevel=3, mtime=0)
        path.write_bytes(encoded)
        result.update(complete=True, decoded_bytes=len(payload), compressed_bytes=len(encoded),
                      decoded_sha256=hashlib.sha256(payload).hexdigest(), compressed_sha256=digest(path))
    except Exception as error:
        result.update(error_type=type(error).__name__, error=str(error))
    sidecar.write_text(json.dumps(result, indent=2)+"\n")
    time.sleep(.25)
    return result


def main():
    spec = json.loads((OUT/"specification.json").read_text())
    (OUT/"native").mkdir(exist_ok=True)
    jobs = [{"date": day, "hour": hour} for day in spec["dates"] for hour in spec["settlement_hours_utc"]]
    records = []
    with ThreadPoolExecutor(max_workers=spec["download"]["workers"]) as pool:
        pending = [pool.submit(fetch, job, spec["download"]) for job in jobs]
        for task in as_completed(pending):
            record = task.result()
            records.append(record)
            result = {"complete": len(records) == len(jobs) and all(r["complete"] for r in records),
                      "files": records, "expected_files": len(jobs), "decoded_bytes": TOTAL,
                      "specification_sha256": digest(OUT/"specification.json"), "orders_submitted": False}
            (OUT/"native_manifest.json").write_text(json.dumps(result, indent=2)+"\n")
            print(json.dumps({"date": record["date"], "hour": record["hour"], "complete": record["complete"],
                              "files": len(records), "decoded_bytes": TOTAL}), flush=True)


if __name__ == "__main__":
    main()
