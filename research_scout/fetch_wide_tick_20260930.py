"""Bounded public historical book/trade slices for all contemporaneous symbols."""

import gzip
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from research_scout.prepare_wide_tick_20260930 import OUT, ROOT

TOTAL = 0
LOCK = threading.Lock()


def reserve(amount, cap):
    global TOTAL
    with LOCK:
        TOTAL += amount
        if cap < TOTAL:
            raise ValueError("Frozen total decoded bound exceeded")


def acquire(day, spec):
    path = OUT / "native" / f"{day}_09.ndjson.gz"
    sidecar = path.with_suffix(path.suffix+".json")
    if sidecar.exists():
        old = json.loads(sidecar.read_text())
        if old["complete"]:
            assert hashlib.sha256(path.read_bytes()).hexdigest() == old["compressed_sha256"]
            reserve(old["decoded_bytes"], spec["download"]["total_decoded_cap"])
        return old
    params = {"from": day, "offset": 540, "sliceSize": 1,
              "filters": json.dumps([{"channel": name} for name in spec["channels"]])}
    record = {"date": day, "path": str(path.relative_to(ROOT)), "complete": False, "params": params, "authenticated": False}
    session = requests.Session()
    session.trust_env = False
    try:
        with session.get("https://api.tardis.dev/v1/data-feeds/binance-futures", params=params,
                         headers={"Accept-Encoding": "gzip"}, stream=True, timeout=(15, 60), allow_redirects=False) as response:
            record["http_status"] = response.status_code
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("Unexpected historical HTTP response")
            blocks, size = [], 0
            for block in response.iter_content(65536):
                reserve(len(block), spec["download"]["total_decoded_cap"])
                size += len(block)
                if size > spec["download"]["per_slice_decoded_cap"]:
                    raise ValueError("Frozen per-slice decoded bound exceeded")
                blocks.append(block)
            payload = b"".join(blocks)
        if not payload.strip():
            raise ValueError("No native observations")
        encoded = gzip.compress(payload, compresslevel=3, mtime=0)
        path.write_bytes(encoded)
        record.update(complete=True, decoded_bytes=len(payload), compressed_bytes=len(encoded),
                      decoded_sha256=hashlib.sha256(payload).hexdigest(), compressed_sha256=hashlib.sha256(encoded).hexdigest())
    except Exception as error:
        record.update(error_type=type(error).__name__, error=str(error))
    sidecar.write_text(json.dumps(record, indent=2)+"\n")
    return record


def main():
    spec_path = OUT / "specification.json"
    spec = json.loads(spec_path.read_text())
    (OUT / "native").mkdir(exist_ok=True)
    records = []
    with ThreadPoolExecutor(max_workers=spec["download"]["workers"]) as pool:
        futures = [pool.submit(acquire, day, spec) for day in spec["dates"]]
        for future in as_completed(futures):
            record = future.result()
            records.append(record)
            manifest = {"expected_files": len(spec["dates"]), "files": records,
                        "complete": len(records) == len(spec["dates"]) and all(r["complete"] for r in records),
                        "decoded_bytes_reserved": TOTAL,
                        "specification_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest()}
            (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
            print(json.dumps({"date": record["date"], "complete": record["complete"], "files": len(records),
                              "decoded_bytes": record.get("decoded_bytes"), "error": record.get("error_type")}), flush=True)


if __name__ == "__main__":
    main()
