"""Build a checksum-verified public BTCUSDT spot/perpetual research dataset."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.binance_public_archive import normalize_kline_csv

S3_LIST_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
PUBLIC_BASE = "https://data.binance.vision"
OUTPUT_ROOT = Path("data/parquet/binance_bitcoin_derivatives_public_v1")
START_MONTH = "2020-01"
END_MONTH = "2025-12"
MAX_FILES = 2_500
MAX_COMPRESSED_BYTES = 20_000_000
MAX_UNCOMPRESSED_BYTES = 100_000_000
TOTAL_DOWNLOAD_LIMIT = 1_000_000_000


@dataclass(frozen=True)
class Product:
    name: str
    prefix: str
    frequency: str
    parser: str


PRODUCTS = (
    Product("spot_klines_30m", "data/spot/monthly/klines/BTCUSDT/30m/", "monthly", "kline"),
    Product("perp_klines_30m", "data/futures/um/monthly/klines/BTCUSDT/30m/", "monthly", "kline"),
    Product(
        "mark_price_klines_30m",
        "data/futures/um/monthly/markPriceKlines/BTCUSDT/30m/",
        "monthly",
        "kline",
    ),
    Product(
        "index_price_klines_30m",
        "data/futures/um/monthly/indexPriceKlines/BTCUSDT/30m/",
        "monthly",
        "kline",
    ),
    Product(
        "premium_index_klines_30m",
        "data/futures/um/monthly/premiumIndexKlines/BTCUSDT/30m/",
        "monthly",
        "kline",
    ),
    Product(
        "funding_rate",
        "data/futures/um/monthly/fundingRate/BTCUSDT/",
        "monthly",
        "funding",
    ),
    Product("futures_metrics_5m", "data/futures/um/daily/metrics/BTCUSDT/", "daily", "metrics"),
)


def _session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=4, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504))
    session.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=32, pool_maxsize=32))
    session.headers["User-Agent"] = "mfs-trader public Binance data research"
    return session


def list_zip_keys(session: requests.Session, prefix: str) -> list[str]:
    keys: list[str] = []
    token: str | None = None
    while True:
        params = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            params["continuation-token"] = token
        response = session.get(S3_LIST_URL, params=params, timeout=60, allow_redirects=False)
        response.raise_for_status()
        if response.status_code != 200:
            raise RuntimeError(f"unexpected S3 listing status {response.status_code}")
        root = ElementTree.fromstring(response.content)
        namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        keys.extend(
            element.text
            for element in root.findall(".//s3:Key", namespace)
            if element.text and element.text.endswith(".zip")
        )
        truncated = root.findtext("s3:IsTruncated", default="false", namespaces=namespace)
        if truncated.lower() != "true":
            break
        token = root.findtext("s3:NextContinuationToken", namespaces=namespace)
        if not token:
            raise RuntimeError("truncated S3 listing omitted continuation token")
    return keys


def _key_period(key: str, frequency: str) -> str | None:
    pattern = r"-(\d{4}-\d{2})\.zip$" if frequency == "monthly" else r"-(\d{4}-\d{2}-\d{2})\.zip$"
    match = re.search(pattern, key)
    return match.group(1) if match else None


def _in_bounds(key: str, product: Product) -> bool:
    period = _key_period(key, product.frequency)
    if period is None:
        return False
    month = period[:7]
    return START_MONTH <= month <= END_MONTH


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def download_verified(key: str, *, raw_root: Path, product: Product) -> dict[str, Any]:
    relative = key.removeprefix(product.prefix)
    target = raw_root / product.name / relative
    checksum_target = target.with_name(target.name + ".CHECKSUM")
    target.parent.mkdir(parents=True, exist_ok=True)
    session = _session()
    url = f"{PUBLIC_BASE}/{key}"
    if not target.exists() or not checksum_target.exists():
        response = session.get(url, timeout=120, allow_redirects=False)
        response.raise_for_status()
        if response.status_code != 200:
            raise RuntimeError(f"unexpected archive status {response.status_code}: {key}")
        if len(response.content) > MAX_COMPRESSED_BYTES:
            raise RuntimeError(f"compressed archive exceeds cap: {key}")
        checksum = session.get(f"{url}.CHECKSUM", timeout=60, allow_redirects=False)
        checksum.raise_for_status()
        if checksum.status_code != 200:
            raise RuntimeError(f"unexpected checksum status {checksum.status_code}: {key}")
        target.write_bytes(response.content)
        checksum_target.write_bytes(checksum.content)
    content = target.read_bytes()
    if len(content) > MAX_COMPRESSED_BYTES:
        raise RuntimeError(f"cached archive exceeds cap: {key}")
    checksum_text = checksum_target.read_text(encoding="utf-8").strip()
    expected = checksum_text.split()[0].lower()
    actual = _sha256(content)
    if actual != expected:
        raise RuntimeError(f"checksum mismatch: {key}")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].is_dir() or not members[0].filename.endswith(".csv"):
            raise RuntimeError(f"unexpected ZIP members: {key}")
        if members[0].file_size > MAX_UNCOMPRESSED_BYTES:
            raise RuntimeError(f"uncompressed archive exceeds cap: {key}")
    return {
        "key": key,
        "product": product.name,
        "source_url": url,
        "checksum_url": f"{url}.CHECKSUM",
        "source_checksum_text": checksum_text,
        "sha256": actual,
        "compressed_bytes": len(content),
        "uncompressed_bytes": members[0].file_size,
        "local_path": str(target),
    }


def _csv_content(path: Path) -> bytes:
    with zipfile.ZipFile(path) as archive:
        member = archive.infolist()[0]
        return archive.read(member)


def _parse_kline(paths: list[Path], product: Product) -> pd.DataFrame:
    frames = []
    for path in paths:
        frame = normalize_kline_csv(_csv_content(path), symbol="BTCUSDT", interval="30m")
        frame.insert(2, "product", product.name)
        frames.append(frame)
    result = pd.concat(frames, ignore_index=True).sort_values("open_time", kind="stable")
    if result["open_time"].duplicated().any():
        raise RuntimeError(f"duplicate kline timestamps in {product.name}")
    return result.reset_index(drop=True)


def _parse_funding(paths: list[Path]) -> pd.DataFrame:
    frames = [pd.read_csv(io.BytesIO(_csv_content(path))) for path in paths]
    result = pd.concat(frames, ignore_index=True)
    required = {"calc_time", "funding_interval_hours", "last_funding_rate"}
    if set(result.columns) != required:
        raise RuntimeError(f"funding schema drift: {result.columns.tolist()}")
    result["calc_time_raw"] = pd.to_numeric(result["calc_time"], errors="raise").astype("int64")
    result["calc_time"] = pd.to_datetime(result["calc_time_raw"], unit="ms", utc=True)
    result["funding_interval_hours"] = pd.to_numeric(
        result["funding_interval_hours"], errors="coerce"
    )
    result["last_funding_rate"] = pd.to_numeric(result["last_funding_rate"], errors="coerce")
    result = result.sort_values("calc_time", kind="stable")
    duplicate = result.duplicated("calc_time", keep=False)
    if duplicate.any():
        unique_counts = result.loc[duplicate].groupby("calc_time")["last_funding_rate"].nunique(dropna=False)
        if (unique_counts > 1).any():
            raise RuntimeError("conflicting duplicate funding timestamps")
        result = result.drop_duplicates("calc_time", keep="last")
    return result.reset_index(drop=True)


def _parse_metrics(paths: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames = [pd.read_csv(io.BytesIO(_csv_content(path))) for path in paths]
    result = pd.concat(frames, ignore_index=True)
    required = {
        "create_time",
        "symbol",
        "sum_open_interest",
        "sum_open_interest_value",
        "count_toptrader_long_short_ratio",
        "sum_toptrader_long_short_ratio",
        "count_long_short_ratio",
        "sum_taker_long_short_vol_ratio",
    }
    if set(result.columns) != required:
        raise RuntimeError(f"metrics schema drift: {result.columns.tolist()}")
    result["create_time"] = pd.to_datetime(result["create_time"], utc=True, errors="raise")
    numeric = sorted(required - {"create_time", "symbol"})
    result[numeric] = result[numeric].apply(pd.to_numeric, errors="coerce")
    end_exclusive = pd.Timestamp(f"{int(END_MONTH[:4]) + 1}-01-01", tz="UTC")
    result = result.loc[result["create_time"] < end_exclusive].copy()
    result = result.sort_values("create_time", kind="stable")
    duplicate = result.duplicated("create_time", keep=False)
    if duplicate.any():
        groups = result.loc[duplicate].groupby("create_time")[numeric].nunique(dropna=False)
        if (groups > 1).any(axis=None):
            raise RuntimeError("conflicting duplicate futures-metrics timestamps")
        result = result.drop_duplicates("create_time", keep="last")
    result = result.reset_index(drop=True)
    thirty = (
        result.set_index("create_time")[numeric]
        .resample("30min", label="right", closed="right")
        .last()
        .dropna(how="all")
        .reset_index()
    )
    thirty.insert(1, "symbol", "BTCUSDT")
    return result, thirty


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    raw_root = output / "raw"
    session = _session()
    selected: list[tuple[Product, str]] = []
    listing: dict[str, Any] = {}
    for product in PRODUCTS:
        keys = list_zip_keys(session, product.prefix)
        bounded = [key for key in keys if _in_bounds(key, product)]
        listing[product.name] = {
            "prefix": product.prefix,
            "available_zip_count": len(keys),
            "selected_zip_count": len(bounded),
            "first_available": _key_period(keys[0], product.frequency) if keys else None,
            "last_available": _key_period(keys[-1], product.frequency) if keys else None,
        }
        selected.extend((product, key) for key in bounded)
    if len(selected) > MAX_FILES:
        raise RuntimeError(f"selected file count {len(selected)} exceeds cap {MAX_FILES}")

    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(download_verified, key, raw_root=raw_root, product=product): (product, key)
            for product, key in selected
        }
        for index, future in enumerate(as_completed(futures), start=1):
            record = future.result()
            records.append(record)
            if index % 100 == 0 or index == len(futures):
                print(f"downloaded_verified={index}/{len(futures)}")
    total_bytes = sum(int(record["compressed_bytes"]) for record in records)
    if total_bytes > TOTAL_DOWNLOAD_LIMIT:
        raise RuntimeError(f"downloaded bytes {total_bytes} exceed cap {TOTAL_DOWNLOAD_LIMIT}")

    normalized: dict[str, Any] = {}
    for product in PRODUCTS:
        product_records = sorted(
            (record for record in records if record["product"] == product.name),
            key=lambda item: item["key"],
        )
        paths = [Path(record["local_path"]) for record in product_records]
        if product.parser == "kline":
            frame = _parse_kline(paths, product)
            path = output / "normalized" / f"{product.name}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(path, index=False)
            normalized[product.name] = {
                "path": str(path),
                "rows": len(frame),
                "first_timestamp": frame["open_time"].min().isoformat(),
                "last_timestamp": frame["open_time"].max().isoformat(),
                "sha256": _sha256(path.read_bytes()),
            }
        elif product.parser == "funding":
            frame = _parse_funding(paths)
            path = output / "normalized" / "funding_rate.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(path, index=False)
            normalized[product.name] = {
                "path": str(path),
                "rows": len(frame),
                "null_rates": int(frame["last_funding_rate"].isna().sum()),
                "first_timestamp": frame["calc_time"].min().isoformat(),
                "last_timestamp": frame["calc_time"].max().isoformat(),
                "sha256": _sha256(path.read_bytes()),
            }
        else:
            frame, thirty = _parse_metrics(paths)
            path_5m = output / "normalized" / "futures_metrics_5m.parquet"
            path_30m = output / "normalized" / "futures_metrics_30m.parquet"
            path_5m.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(path_5m, index=False)
            thirty.to_parquet(path_30m, index=False)
            normalized[product.name] = {
                "path_5m": str(path_5m),
                "path_30m": str(path_30m),
                "rows_5m": len(frame),
                "rows_30m": len(thirty),
                "first_timestamp": frame["create_time"].min().isoformat(),
                "last_timestamp": frame["create_time"].max().isoformat(),
                "sha256_5m": _sha256(path_5m.read_bytes()),
                "sha256_30m": _sha256(path_30m.read_bytes()),
            }

    manifest = {
        "schema_version": "binance_bitcoin_derivatives_public:v1",
        "created_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "symbol": "BTCUSDT",
        "selected_month_bounds": [START_MONTH, END_MONTH],
        "official_repository": "https://github.com/binance/binance-public-data",
        "official_archive": PUBLIC_BASE,
        "s3_listing_endpoint": S3_LIST_URL,
        "listing": listing,
        "archive_count": len(records),
        "compressed_bytes": total_bytes,
        "all_checksums_verified": all(
            record["sha256"] == record["source_checksum_text"].split()[0].lower()
            for record in records
        ),
        "archives": sorted(records, key=lambda item: item["key"]),
        "normalized": normalized,
        "excluded_by_design": {
            "aggTrades_and_trades": "Not required for a 30-minute-to-8-hour non-latency hypothesis; much larger event-level data.",
            "bookTicker": "Available only from 2023-05 and roughly tens of MB per day; too large and unnecessary for the proposed horizon.",
            "bookDepth": "Public percentage-depth snapshots start in 2023; useful only for a separate depth hypothesis and not full order-event history.",
            "liquidations": "No BTCUSDT liquidationSnapshot keys found in the official archive prefix.",
        },
        "interpretation_limits": [
            "BTCUSDT perpetual and spot are Binance-only, not consolidated crypto markets.",
            "Top-trader and long/short ratios are exchange-defined aggregates, not trader-level positions.",
            "Funding-rate rows record settlement rates; signal availability must be lagged until calc_time.",
            "Open interest is a snapshot and does not identify whether new exposure is long or short.",
            "Downloading data does not authorize inspecting locked future-return partitions for hypothesis tuning.",
        ],
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"archives={len(records)} compressed_bytes={total_bytes}")
    print(f"manifest={manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
