"""Bounded public native quote/mark acquisition for the frozen five events."""

import gzip
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from research_scout.prepare_perp_shock_replay_20261002 import OUT, ROOT, sha


def fetch(job, cfg):
    path = OUT / "native" / f"{job['date']}_{job['offset']:04d}_{job['symbol']}.ndjson.gz"
    sidecar = path.with_suffix(path.suffix + ".json")
    if sidecar.exists():
        row = json.loads(sidecar.read_text())
        if row["complete"]:
            assert sha(path) == row["compressed_sha256"]
        return row
    params = {"from": job["date"], "offset": job["offset"], "sliceSize": cfg["slice_minutes"],
              "filters": json.dumps([{"channel": c, "symbols": [job["symbol"].lower()]} for c in cfg["channels"]])}
    result = {**job, "path": str(path.relative_to(ROOT)), "params": params,
              "complete": False, "authenticated": False}
    session = requests.Session()
    session.trust_env = False
    size, started = 0, time.monotonic()
    try:
        with session.get("https://api.tardis.dev/v1/data-feeds/binance-futures", params=params,
                         headers={"Accept-Encoding": "gzip"}, stream=True,
                         timeout=(15, 45), allow_redirects=False) as response:
            result["http_status"] = response.status_code
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("Unexpected response status")
            with path.open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=3, mtime=0) as sink:
                for block in response.iter_content(65536):
                    size += len(block)
                    if size > cfg["per_slice_decoded_cap"] or time.monotonic() - started > cfg["request_deadline_seconds"]:
                        raise ValueError("Frozen acquisition cap exceeded")
                    sink.write(block)
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
    spec = json.loads((OUT / "specification.json").read_text())
    (OUT / "native").mkdir(exist_ok=True)
    rows = []
    with ThreadPoolExecutor(max_workers=spec["download"]["workers"]) as pool:
        futures = [pool.submit(fetch, j, spec["download"]) for j in spec["jobs"]]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            manifest = {"files": sorted(rows, key=lambda x: (x["date"], x["offset"], x["symbol"])),
                        "complete": len(rows) == len(spec["jobs"]) and all(x["complete"] for x in rows),
                        "specification_sha256": sha(OUT / "specification.json"), "acquisition_sha256": sha(Path(__file__))}
            (OUT / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({k: row.get(k) for k in ("date", "symbol", "complete", "decoded_bytes", "error")}), flush=True)


if __name__ == "__main__":
    main()
