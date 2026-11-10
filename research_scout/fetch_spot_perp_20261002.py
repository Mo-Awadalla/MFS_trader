"""Bounded unauthenticated first-of-month native spot BBO acquisition."""

import argparse
import gzip
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from research_scout.prepare_spot_perp_20261002 import OUT, ROOT, sha


def fetch(day, spec):
    path = OUT / "native" / f"spot_{day}_0900.ndjson.gz"
    sidecar = path.with_suffix(path.suffix + ".json")
    if sidecar.exists():
        old = json.loads(sidecar.read_text())
        if old["complete"]:
            assert sha(path) == old["compressed_sha256"]
        return old
    cfg = spec["download"]
    params = {"from": day, "offset": cfg["offset"], "sliceSize": cfg["slice_minutes"],
              "filters": json.dumps([{"channel": name} for name in cfg["channels"]])}
    result = {"date": day, "path": str(path.relative_to(ROOT)), "complete": False,
              "params": params, "authenticated": False}
    session = requests.Session()
    session.trust_env = False
    size = 0
    started = time.monotonic()
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
                        raise ValueError("Frozen decoded cap exceeded")
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    (OUT / "native").mkdir(exist_ok=True)
    spec = json.loads((OUT / "specification.json").read_text())
    assert len(spec["dates"]) * spec["download"]["per_slice_decoded_cap"] <= spec["download"]["total_decoded_cap"]
    dates = spec["dates"][:1] if args.pilot else spec["dates"]
    records = []
    with ThreadPoolExecutor(max_workers=spec["download"]["workers"]) as pool:
        futures = [pool.submit(fetch, day, spec) for day in dates]
        for job in as_completed(futures):
            row = job.result()
            records.append(row)
            manifest = {"files": sorted(records, key=lambda x: x["date"]), "expected_files": len(dates),
                        "complete": len(records) == len(dates) and all(x["complete"] for x in records),
                        "specification_sha256": sha(OUT / "specification.json"),
                        "acquisition_sha256": sha(__file__),
                        "decoded_bytes": sum(x.get("decoded_bytes", 0) for x in records)}
            name = "pilot_manifest.json" if args.pilot else "spot_manifest.json"
            (OUT / name).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({k: row.get(k) for k in ("date", "complete", "decoded_bytes", "error")}), flush=True)


if __name__ == "__main__":
    main()
