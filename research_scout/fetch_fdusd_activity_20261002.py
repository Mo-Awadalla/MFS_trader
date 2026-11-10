"""Bounded public historical spot trade retrieval; no credentials or paid fallback."""

import gzip
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from research_scout.prepare_fdusd_activity_20261002 import OUT, ROOT, sha


def fetch(window, cfg):
    day, offset = window["date"], window["offset"]
    path = OUT / "native" / f"{day}_{offset:04d}.ndjson.gz"
    sidecar = path.with_suffix(path.suffix + ".json")
    if sidecar.exists():
        result = json.loads(sidecar.read_text())
        if result["complete"]:
            assert sha(path) == result["compressed_sha256"]
        return result
    params = {"from": day, "offset": offset, "sliceSize": cfg["slice_minutes"],
              "filters": json.dumps([{"channel": cfg["channel"], "symbols": [s.lower() for s in window["symbols"]]}])}
    result = {**window, "path": str(path.relative_to(ROOT)), "params": params,
              "complete": False, "authenticated": False}
    session = requests.Session()
    session.trust_env = False
    size, started = 0, time.monotonic()
    try:
        with session.get("https://api.tardis.dev/v1/data-feeds/binance", params=params,
                         headers={"Accept-Encoding": "gzip"}, stream=True,
                         timeout=(15, 45), allow_redirects=False) as response:
            result["http_status"] = response.status_code
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("Unexpected status")
            with path.open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=3, mtime=0) as sink:
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > cfg["per_slice_decoded_cap"]:
                        raise ValueError("Frozen decoded byte cap exceeded")
                    if time.monotonic() - started > cfg["request_deadline_seconds"]:
                        raise ValueError("Frozen request deadline exceeded")
                    sink.write(chunk)
        result.update(complete=True, decoded_bytes=size, compressed_bytes=path.stat().st_size,
                      compressed_sha256=sha(path))
    except Exception as error:
        result.update(error_type=type(error).__name__, error=str(error), decoded_bytes=size)
    finally:
        session.close()
    with sidecar.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    return result


def main():
    (OUT / "native").mkdir(exist_ok=True)
    spec = json.loads((OUT / "specification.json").read_text())
    records = []
    with ThreadPoolExecutor(max_workers=spec["download"]["workers"]) as pool:
        jobs = [pool.submit(fetch, window, spec["download"]) for window in spec["windows"]]
        for job in as_completed(jobs):
            row = job.result()
            records.append(row)
            manifest = {"files": sorted(records, key=lambda r: (r["date"], r["offset"])),
                        "expected_files": len(spec["windows"]),
                        "complete": len(records) == len(spec["windows"]) and all(r["complete"] for r in records),
                        "specification_sha256": sha(OUT / "specification.json"),
                        "acquisition_sha256": sha(Path(__file__)),
                        "decoded_bytes": sum(r["decoded_bytes"] for r in records)}
            (OUT / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({k: row.get(k) for k in ("date", "offset", "complete", "decoded_bytes", "error")}), flush=True)


if __name__ == "__main__":
    main()
