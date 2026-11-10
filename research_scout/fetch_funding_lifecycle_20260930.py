"""Save bounded public lifecycle evidence and the missing-source diagnostic."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent / "funding_universe_hft_20260930" / "lifecycle_sources"
JOBS = {
    "binance_dgb_ctk.html": "https://www.binance.com/en/support/announcement/detail/ce74360a3fd444b2b35da7186f8dd0ad",
    "binance_fet_update.html": "https://www.binance.com/en/support/announcement/detail/e485541c370240adba3929fded74f269",
    "bybit_fet.html": "https://announcements.bybit.com/en/article/delisting-of-fetusdt-oceanusdt-and-agixusdt-perpetual-contracts-blt76ce31b7f7becb38/",
    "fet_source_diagnostic.txt": "https://datasets.tardis.dev/v1/bybit/derivative_ticker/2024/07/01/FETUSDT.csv.gz",
}


def main():
    OUT.mkdir(exist_ok=True)
    manifest = OUT / "manifest.json"
    if manifest.exists():
        raise RuntimeError("Preserve original lifecycle retrieval")
    session = requests.Session()
    session.trust_env = False
    records = []
    for filename, url in JOBS.items():
        record = {"filename": filename, "url": url, "retrieved_at_utc": datetime.now(UTC).isoformat(),
                  "authenticated": False, "complete": False}
        try:
            with session.get(url, stream=True, timeout=(15, 45), allow_redirects=False) as response:
                record.update(http_status=response.status_code, content_type=response.headers.get("Content-Type"))
                payload = bytearray()
                for block in response.iter_content(65536):
                    payload.extend(block)
                    if len(payload) > 4_000_000:
                        raise ValueError("Public source exceeded four-megabyte bound")
                (OUT / filename).write_bytes(payload)
                record.update(complete=True, bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        except Exception as error:
            record.update(error_type=type(error).__name__, error=str(error))
        records.append(record)
        print(json.dumps(record), flush=True)
        manifest.write_text(json.dumps({"sources": records, "paid_fallback": False}, indent=2)+"\n")


if __name__ == "__main__":
    main()
