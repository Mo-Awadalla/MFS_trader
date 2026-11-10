"""Recover public exchange-native fields for twelve preselected calendar days."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/force_order_full_20260930"
DATES = [f"2024-{month:02d}-01" for month in range(1, 13)]
FILTERS = [{"channel": "forceOrder", "symbols": ["btcusdt", "solusdt"]}]
LIMIT = 128_000_000
TOTAL = 0
LOCK = threading.Lock()
THREAD = threading.local()


def reserve(size):
    global TOTAL
    with LOCK:
        TOTAL += size
        if TOTAL > LIMIT:
            raise ValueError("Fixed cumulative decoded-byte cap exceeded")


def fetch(day, minute):
    path = OUT / "raw" / f"{day}_{minute:04d}.ndjson"
    if path.exists():
        payload = path.read_bytes()
        reserve(len(payload))
    else:
        if not hasattr(THREAD, "session"):
            THREAD.session = requests.Session()
            THREAD.session.trust_env = False
        params = {"from": day, "offset": minute, "sliceSize": 10,
                  "filters": json.dumps(FILTERS)}
        for attempt in range(4):
            try:
                with THREAD.session.get("https://api.tardis.dev/v1/data-feeds/binance-futures",
                                        params=params, headers={"Accept-Encoding": "gzip"},
                                        stream=True, timeout=(15, 60)) as response:
                    if response.status_code in {429, 500, 502, 503, 504}:
                        time.sleep(min(30, 2 ** (attempt + 1)))
                        response.raise_for_status()
                    response.raise_for_status()
                    chunks, size = [], 0
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        reserve(len(chunk))
                        if size > 2_000_000:
                            raise ValueError("Fixed two-MB decoded slice cap exceeded")
                        chunks.append(chunk)
                payload = b"".join(chunks)
                break
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
                if attempt == 3:
                    raise
                time.sleep(min(30, 2 ** (attempt + 1)))
        # A failed/partial request is never treated as a valid cached slice.
        path.write_bytes(payload)
    return {"date": day, "minute_offset": minute, "slice_minutes": 10,
            "path": str(path.relative_to(ROOT)), "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest()}


def main():
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    plan = OUT / "acquisition_plan.json"
    if not plan.exists():
        plan.write_text(json.dumps({"created_at_utc": datetime.now(UTC).isoformat(),
            "dates": DATES, "filters": FILTERS, "slices": 1728, "concurrency": 8,
            "maximum_decoded_bytes": LIMIT, "maximum_slice_decoded_bytes": 2_000_000,
            "authentication": "None. Public first-of-month samples only. No paid/authenticated fallback.",
            "selection": "Every ten-minute interval on the twelve calendar dates, including intervals with no CSV reports. Jan-Jun calibration; Jul-Dec previously exposed price dates for discovery, not fresh confirmation.",
            "purpose": "Preserve actual cumulative filled quantity z and average execution price ap. Do not infer residual liquidation demand from original q or IOC status.",
            "source": "https://docs.tardis.dev/api/http-api-reference.md"}, indent=2) + "\n")
    completed, errors, last_log = [], [], time.monotonic()
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = {pool.submit(fetch, day, minute): (day, minute)
                for day in DATES for minute in range(0, 1440, 10)}
        for job in as_completed(jobs):
            try:
                completed.append(job.result())
            except Exception as exc:
                day, minute = jobs[job]
                errors.append({"date": day, "minute_offset": minute, "error": str(exc)})
            if time.monotonic() - last_log > 25 or len(completed) + len(errors) == len(jobs):
                print(f"Raw recovery: {len(completed)}/{len(jobs)} slices, {len(errors)} errors, {TOTAL:,} decoded bytes", flush=True)
                last_log = time.monotonic()
                (OUT / "download_progress.json").write_text(json.dumps({"complete_slices": len(completed), "errors": errors, "decoded_bytes_including_retries": TOTAL}, indent=2) + "\n")
    completed.sort(key=lambda x: (x["date"], x["minute_offset"]))
    result = {"complete": not errors and len(completed) == 1728, "files": completed,
              "errors": errors, "decoded_bytes_including_retries": TOTAL,
              "public_unauthenticated": True}
    (OUT / "download_manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    if not result["complete"]:
        raise RuntimeError("Incomplete raw recovery; use no strategy outcomes from partial data")


if __name__ == "__main__":
    main()
