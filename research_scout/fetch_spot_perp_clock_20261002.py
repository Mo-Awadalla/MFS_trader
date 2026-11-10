"""Acquire the fixed expanded clock samples under per-file and aggregate caps."""

import gzip
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from research_scout.prepare_spot_perp_clock_20261002 import OUT, ROOT, sha

TOTAL = 0
LOCK = threading.Lock()


def reserve(size, cap):
    global TOTAL
    with LOCK:
        TOTAL += size
        if TOTAL > cap:
            raise ValueError("Frozen aggregate decoded cap exceeded")


def fetch(job, cfg):
    day, offset, venue = job["date"], job["offset"], job["venue"]
    path = OUT / "native" / f"{venue}_{day}_{offset:04d}.ndjson.gz"
    sidecar = path.with_suffix(path.suffix + ".json")
    if sidecar.exists():
        old = json.loads(sidecar.read_text())
        if old["complete"]:
            assert sha(path) == old["compressed_sha256"]
        reserve(old.get("decoded_bytes", 0), cfg["total_decoded_cap"])
        return old
    params = {"from": day, "offset": offset, "sliceSize": 1,
              "filters": json.dumps([{"channel": "bookTicker"}])}
    result = {**job, "path": str(path.relative_to(ROOT)), "params": params,
              "complete": False, "authenticated": False}
    session = requests.Session()
    session.trust_env = False
    started, size = time.monotonic(), 0
    try:
        url = "https://api.tardis.dev/v1/data-feeds/" + cfg["exchanges"][venue]
        with session.get(url, params=params, headers={"Accept-Encoding": "gzip"},
                         timeout=(15, 45), stream=True, allow_redirects=False) as response:
            result["http_status"] = response.status_code
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("Unexpected status")
            with path.open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=3, mtime=0) as sink:
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    reserve(len(chunk), cfg["total_decoded_cap"])
                    if size > cfg["per_slice_decoded_cap"]:
                        raise ValueError("Frozen file decoded cap exceeded")
                    if time.monotonic() - started > cfg["request_deadline_seconds"]:
                        raise ValueError("Frozen request deadline exceeded")
                    sink.write(chunk)
        if size == 0:
            raise ValueError("Empty source")
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
    jobs = [{"date": day, "offset": offset, "venue": venue}
            for day in spec["dates"] for offset in spec["offset_minutes"]
            for venue in ("spot", "perpetual")]
    records = []
    with ThreadPoolExecutor(max_workers=spec["download"]["workers"]) as pool:
        pending = [pool.submit(fetch, job, spec["download"]) for job in jobs]
        for task in as_completed(pending):
            row = task.result()
            records.append(row)
            manifest = {"files": sorted(records, key=lambda r: (r["date"], r["offset"], r["venue"])),
                        "expected_files": len(jobs), "complete": len(records) == len(jobs) and all(r["complete"] for r in records),
                        "decoded_bytes": sum(r.get("decoded_bytes", 0) for r in records),
                        "specification_sha256": sha(OUT / "specification.json"),
                        "acquisition_sha256": sha(__file__)}
            (OUT / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({**{k: row.get(k) for k in ("date", "offset", "venue", "complete", "decoded_bytes", "error")},
                              "completed_files": len(records), "expected_files": len(jobs)}), flush=True)


if __name__ == "__main__":
    main()
