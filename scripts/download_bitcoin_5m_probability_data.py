"""Download checksum-verified Binance BTCUSDT perpetual 5m klines."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.binance_public_archive import month_keys, normalize_kline_csv

BASE_URL = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m"
OUTPUT_ROOT = Path("data/parquet/bitcoin_5m_probability_binance_v1")
SYMBOL = "BTCUSDT"
INTERVAL = "5m"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _download_month(month: str, *, raw_dir: Path, refresh: bool) -> dict[str, Any]:
    filename = f"{SYMBOL}-{INTERVAL}-{month}.zip"
    url = f"{BASE_URL}/{filename}"
    archive_path = raw_dir / filename
    checksum_path = raw_dir / f"{filename}.CHECKSUM"
    raw_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = "mfs-trader public Binance research downloader"
    if refresh or not archive_path.exists() or not checksum_path.exists():
        archive_response = session.get(url, timeout=120)
        archive_response.raise_for_status()
        checksum_response = session.get(f"{url}.CHECKSUM", timeout=60)
        checksum_response.raise_for_status()
        archive_path.write_bytes(archive_response.content)
        checksum_path.write_bytes(checksum_response.content)

    archive = archive_path.read_bytes()
    checksum_text = checksum_path.read_text(encoding="utf-8").strip()
    expected_sha256 = checksum_text.split()[0].lower()
    actual_sha256 = _sha256(archive)
    if expected_sha256 != actual_sha256:
        raise ValueError(f"checksum mismatch for {filename}")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        members = zipped.namelist()
        if len(members) != 1 or not members[0].endswith(".csv"):
            raise ValueError(f"unexpected archive members for {filename}: {members}")
        frame = normalize_kline_csv(
            zipped.read(members[0]), symbol=SYMBOL, interval=INTERVAL
        )
    differences = frame["open_time"].diff().dropna()
    missing = int((differences / pd.Timedelta(minutes=5) - 1).sum())
    return {
        "month": month,
        "source_url": url,
        "checksum_url": f"{url}.CHECKSUM",
        "source_checksum_text": checksum_text,
        "expected_sha256": expected_sha256,
        "actual_sha256": actual_sha256,
        "bytes": len(archive),
        "rows": int(len(frame)),
        "missing_bar_count": missing,
        "incomplete_bar_count": int(frame.attrs.get("incomplete_bar_count", 0)),
        "off_grid_bar_count": int(frame.attrs.get("off_grid_bar_count", 0)),
        "first_open_time": frame["open_time"].min().isoformat(),
        "last_open_time": frame["open_time"].max().isoformat(),
        "raw_archive": str(archive_path),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2020-09-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.workers < 1 or args.workers > 16:
        raise ValueError("workers must be between 1 and 16")
    output_dir = args.output_dir.resolve()
    raw_dir = output_dir / "raw"
    months = month_keys(args.start, args.end)
    records: list[dict[str, Any]] = []
    frames: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                _download_month, month, raw_dir=raw_dir, refresh=bool(args.refresh)
            ): month
            for month in months
        }
        for index, future in enumerate(as_completed(futures), start=1):
            month = futures[future]
            record = future.result()
            records.append(record)
            print(f"[{index}/{len(months)}] {month} rows={record['rows']} sha256={record['actual_sha256'][:12]}")

    for record in sorted(records, key=lambda item: item["month"]):
        archive_path = Path(record["raw_archive"])
        with zipfile.ZipFile(archive_path) as zipped:
            frame = normalize_kline_csv(
                zipped.read(zipped.namelist()[0]), symbol=SYMBOL, interval=INTERVAL
            )
            frames.append(frame)
    bars = pd.concat(frames, ignore_index=True).sort_values("open_time", kind="stable")
    if bars["open_time"].duplicated().any():
        raise ValueError("duplicate 5m timestamps across monthly archives")
    start_ts = pd.Timestamp(args.start, tz="UTC")
    end_exclusive = pd.Timestamp(args.end, tz="UTC") + pd.Timedelta(days=1)
    bars = bars.loc[
        (bars["open_time"] >= start_ts) & (bars["open_time"] < end_exclusive)
    ].reset_index(drop=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    bars_path = output_dir / "bars_5m.parquet"
    bars.to_parquet(bars_path, index=False)
    manifest = {
        "schema_version": "binance_public_5m_klines:v1",
        "specification_id": "Bitcoin-5m-Probability-BinancePerp-v1",
        "provider": "binance_public_data",
        "venue": "binance_usds_m_perpetual",
        "instrument": SYMBOL,
        "interval": INTERVAL,
        "requested_bounds": {"start": args.start, "end": args.end},
        "archive_count": len(records),
        "archives": sorted(records, key=lambda item: item["month"]),
        "normalized_rows": int(len(bars)),
        "first_open_time": bars["open_time"].min().isoformat(),
        "last_open_time": bars["open_time"].max().isoformat(),
        "bars_sha256": _sha256(bars_path.read_bytes()),
        "bars_path": str(bars_path),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"bars={bars_path} rows={len(bars)} sha256={manifest['bars_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
