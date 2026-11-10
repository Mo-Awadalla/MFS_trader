"""Get only the selected contract's native BBO and post-settlement clock."""

import gzip
import json
import time

import requests

from research_scout.prepare_spot_perp_replay_20261002 import OUT, ROOT, sha


def main():
    spec = json.loads((OUT / "specification.json").read_text())
    cfg = spec["acquisition"]
    path = OUT / "ena_native.ndjson.gz"
    manifest_path = OUT / "source_manifest.json"
    assert not manifest_path.exists()
    params = {"from": cfg["date"], "offset": cfg["offset"], "sliceSize": cfg["slice_minutes"],
              "filters": json.dumps([{"channel": channel, "symbols": [cfg["symbol"]]}
                                     for channel in cfg["channels"]])}
    record = {"params": params, "path": str(path.relative_to(ROOT)), "complete": False,
              "authenticated": False, "specification_sha256": sha(OUT / "specification.json"),
              "acquisition_sha256": sha(__file__)}
    session = requests.Session()
    session.trust_env = False
    started, size = time.monotonic(), 0
    try:
        with session.get("https://api.tardis.dev/v1/data-feeds/binance-futures", params=params,
                         headers={"Accept-Encoding": "gzip"}, stream=True,
                         timeout=(15, 45), allow_redirects=False) as response:
            response.raise_for_status()
            assert response.status_code == 200
            with path.open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=3, mtime=0) as sink:
                for block in response.iter_content(65536):
                    size += len(block)
                    if size > cfg["decoded_cap"] or time.monotonic() - started > 90:
                        raise ValueError("Frozen byte/time bound exceeded")
                    sink.write(block)
        assert size > 0
        record.update(complete=True, decoded_bytes=size, compressed_bytes=path.stat().st_size,
                      compressed_sha256=sha(path))
    except Exception as error:
        record.update(error_type=type(error).__name__, error=str(error), decoded_bytes=size)
    finally:
        session.close()
    with manifest_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
