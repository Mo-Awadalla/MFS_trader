"""Acquire the frozen public Bybit slices without credentials or paid fallback."""

import argparse
import gzip
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import requests

from research_scout.prepare_external_quote_20261002 import OUT, ROOT


def fetch(job, config, folder="native"):
    path = OUT/folder/f"{job['date']}_{job['offset']:04d}.ndjson.gz"
    sidecar = path.with_suffix(path.suffix+".json")
    if sidecar.exists():
        previous = json.loads(sidecar.read_text())
        if previous["complete"]:
            assert hashlib.sha256(path.read_bytes()).hexdigest() == previous["compressed_sha256"]
        return previous
    params = {"from": job["date"], "offset": job["offset"], "sliceSize": config["slice_minutes"],
              "filters": json.dumps([{"channel": config["channel"], "symbols": job["symbols"]}])}
    record = {**job, "params": params, "path": str(path.relative_to(ROOT)), "complete": False, "authenticated": False}
    session = requests.Session()
    session.trust_env = False
    try:
        with session.get("https://api.tardis.dev/v1/data-feeds/bybit", params=params,
                         headers={"Accept-Encoding": "gzip"}, stream=True, timeout=(15, 60), allow_redirects=False) as response:
            record["http_status"] = response.status_code
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("Unexpected response status")
            blocks, size = [], 0
            for block in response.iter_content(65536):
                size += len(block)
                if size > config["per_slice_decoded_cap"]:
                    raise ValueError("Frozen per-slice size cap exceeded")
                blocks.append(block)
            payload = b"".join(blocks)
        if not payload.strip():
            raise ValueError("Empty external venue source")
        encoded = gzip.compress(payload, compresslevel=3, mtime=0)
        path.write_bytes(encoded)
        record.update(complete=True, decoded_bytes=len(payload), compressed_bytes=len(encoded),
                      decoded_sha256=hashlib.sha256(payload).hexdigest(), compressed_sha256=hashlib.sha256(encoded).hexdigest())
    except Exception as error:
        record.update(error_type=type(error).__name__, error=str(error))
    sidecar.write_text(json.dumps(record, indent=2)+"\n")
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--retry-network-errors", action="store_true")
    args = parser.parse_args()
    spec_path = OUT/"specification.json"
    spec = json.loads(spec_path.read_text())
    folder, manifest_name = "native", "source_manifest.json"
    if args.retry_network_errors:
        failed_path = OUT/"source_manifest.json"
        failed = json.loads(failed_path.read_text())
        assert len(failed["files"]) == failed["expected_files"] == 30
        assert all(not f["complete"] and f["error_type"] == "ConnectionError" and "WinError 10051" in f["error"] for f in failed["files"])
        recovery = OUT/"network_retry_plan.json"
        if not recovery.exists():
            recovery.write_text(json.dumps({"created_at_utc": datetime.now(UTC).isoformat(),
                                           "reason": "The sandbox network was unreachable. Repeat exactly the same frozen public requests with network permission; preserve all initial failures.",
                                           "failed_manifest_sha256": hashlib.sha256(failed_path.read_bytes()).hexdigest(),
                                           "specification_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest()}, indent=2)+"\n")
        folder, manifest_name = "native_network_retry1", "source_manifest_network_retry1.json"
    (OUT/folder).mkdir(exist_ok=True)
    jobs = [{**cohort, "offset": offset} for cohort in spec["cohorts"] for offset in spec["download"]["offsets"]]
    assert len(jobs)*spec["download"]["per_slice_decoded_cap"] <= spec["download"]["total_decoded_cap"]
    files = []
    with ThreadPoolExecutor(max_workers=spec["download"]["workers"]) as pool:
        pending = [pool.submit(fetch, job, spec["download"], folder) for job in jobs]
        for task in as_completed(pending):
            result = task.result()
            files.append(result)
            manifest = {"files": files, "expected_files": len(jobs), "complete": len(files) == len(jobs) and all(x["complete"] for x in files),
                        "specification_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(),
                        "decoded_bytes": sum(x.get("decoded_bytes", 0) for x in files), "orders_submitted": False}
            (OUT/manifest_name).write_text(json.dumps(manifest, indent=2)+"\n")
            print(json.dumps({k: result.get(k) for k in ("date", "offset", "complete", "decoded_bytes", "error")}), flush=True)


if __name__ == "__main__":
    main()
