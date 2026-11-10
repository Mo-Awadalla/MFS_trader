"""Download only the two inspected public samples, without credentials or billing."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import requests

from research_scout.inspect_databento_public_sample_20261003 import OUT, URLS, PublicOnly


def download(source):
    schema = source["schema"]
    assert URLS[schema] == source["url"]
    directory = OUT / "sources"
    directory.mkdir(exist_ok=True)
    prefix = (OUT / (schema + ".prefix.csv")).read_bytes()
    assert hashlib.sha256(prefix).hexdigest() == source["sha256"] and len(prefix) == 65536
    target = directory / ("xnas_itch_" + schema + ".csv")
    partial = target.with_suffix(".csv.partial")
    assert target.resolve().parent == partial.resolve().parent == directory.resolve()
    assert not target.exists() and not partial.exists()
    ceiling = {"mbo": 1073741824, "mbp1": 536870912}[schema]
    digest, total, lines, last_report, head = hashlib.sha256(), 0, 0, 0, b""
    started = datetime.now(UTC).isoformat()
    with requests.get(URLS[schema], auth=PublicOnly(), stream=True, timeout=(10, 45),
                      allow_redirects=False) as response:
        assert response.status_code == 200, response.status_code
        assert response.headers.get("Content-Type", "").startswith("text/csv")
        headers = {k: v for k, v in response.headers.items() if k.lower() in (
            "content-type", "content-length", "content-disposition", "etag", "last-modified")}
        with partial.open("xb") as handle:
            for chunk in response.iter_content(1024 * 1024):
                assert total + len(chunk) <= ceiling, "Public sample exceeds declared download ceiling"
                if len(head) < len(prefix):
                    head += chunk[:len(prefix) - len(head)]
                    assert head == prefix[:len(head)], "Public sample changed since prefix inspection"
                handle.write(chunk)
                digest.update(chunk)
                total += len(chunk)
                lines += chunk.count(b"\n")
                if total - last_report >= 64 * 1024 * 1024:
                    print(json.dumps({"schema": schema, "bytes_received": total}), flush=True)
                    last_report = total
    assert total > 65536 and head == prefix
    if "Content-Length" in response.headers:
        assert total == int(response.headers["Content-Length"])
    partial.rename(target)
    result = {"schema": schema, "url": URLS[schema], "source_page": "https://databento.com/tick-data",
              "started_at_utc": started, "completed_at_utc": datetime.now(UTC).isoformat(),
              "headers": headers, "bytes": total, "newline_count": lines, "sha256": digest.hexdigest(),
              "path": str(target), "prefix_sha256": source["sha256"], "reached_response_eof": True,
              "public_sample_gets": 1, "authentication_used": False, "paid_calls": 0}
    (directory / (schema + "_acquisition.json")).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    inspection = json.loads((OUT / "public_sample_inspection.json").read_text())
    assert len(inspection["sources"]) == 2
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(download, source) for source in inspection["sources"]]):
            result = future.result()
            results.append(result)
            print(json.dumps(result), flush=True)
    report = {"completed_at_utc": datetime.now(UTC).isoformat(), "sources": sorted(results, key=lambda r: r["schema"]),
              "public_sample_gets": 2, "authentication_used": False, "paid_calls": 0,
              "account_credit_queries": 0, "returns_calculated": False, "reliable_edge_established": False}
    (OUT / "acquisition.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
