"""Download official Cboe monthly VX contract history for V46."""

from __future__ import annotations

import csv
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "cboe_vx_monthly_v46"
BASE = "https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX"
SOURCE_PAGE = "https://www.cboe.com/markets/us/futures/market-statistics/historical-data/futures"
EXPIRATIONS = [
    "2021-01-20", "2021-02-17", "2021-03-17", "2021-04-21",
    "2021-05-19", "2021-06-16", "2021-07-21", "2021-08-18",
    "2021-09-15", "2021-10-20", "2021-11-17", "2021-12-22",
    "2022-01-19", "2022-02-16", "2022-03-15", "2022-04-20",
    "2022-05-18", "2022-06-15", "2022-07-20", "2022-08-17",
    "2022-09-21", "2022-10-19", "2022-11-16", "2022-12-21",
    "2023-01-18", "2023-02-15", "2023-03-22", "2023-04-19",
    "2023-05-17", "2023-06-21", "2023-07-19", "2023-08-16",
    "2023-09-20", "2023-10-18", "2023-11-15", "2023-12-20",
    "2024-01-17", "2024-02-14", "2024-03-20", "2024-04-17",
    "2024-05-22", "2024-06-18", "2024-07-17", "2024-08-21",
    "2024-09-18", "2024-10-16", "2024-11-20", "2024-12-18",
    "2025-01-22", "2025-02-19", "2025-03-18", "2025-04-16",
    "2025-05-21", "2025-06-18", "2025-07-16", "2025-08-20",
    "2025-09-17", "2025-10-22", "2025-11-19", "2025-12-17",
    "2026-01-21", "2026-02-18",
]
EXPECTED_HEADER = [
    "Trade Date", "Futures", "Open", "High", "Low", "Close", "Settle",
    "Change", "Total Volume", "EFP", "Open Interest",
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = []
    for expiration in EXPIRATIONS:
        name = f"VX_{expiration}.csv"
        url = f"{BASE}/{name}"
        path = OUT / name
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
            status = response.status
        path.write_bytes(data)
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle))
        if not rows or rows[0] != EXPECTED_HEADER:
            raise RuntimeError(f"Unexpected schema for {name}: {rows[:1]}")
        if len(rows) < 2:
            raise RuntimeError(f"No data rows for {name}")
        files.append(
            {
                "expiration": expiration,
                "url": url,
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "http_status": status,
                "bytes": len(data),
                "rows_excluding_header": len(rows) - 1,
                "sha256": hashlib.sha256(data).hexdigest(),
                "first_trade_date": rows[1][0],
                "last_trade_date": rows[-1][0],
            }
        )
    manifest = {
        "schema_version": 1,
        "source": "Cboe Futures Exchange official historical data",
        "source_page": SOURCE_PAGE,
        "contract_policy": "standard monthly VX contracts only; weekly VX01-VX53 excluded",
        "files": files,
    }
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "files": len(files),
                "bytes": sum(item["bytes"] for item in files),
                "rows": sum(item["rows_excluding_header"] for item in files),
                "manifest": str(manifest_path.relative_to(ROOT)).replace("\\", "/"),
            }
        )
    )


if __name__ == "__main__":
    main()
