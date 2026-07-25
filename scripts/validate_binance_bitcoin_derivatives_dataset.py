"""Validate the normalized public Binance BTCUSDT derivatives dataset without testing returns."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_ROOT = Path("data/parquet/binance_bitcoin_derivatives_public_v1")
KLINE_PRODUCTS = (
    "spot_klines_30m",
    "perp_klines_30m",
    "mark_price_klines_30m",
    "index_price_klines_30m",
    "premium_index_klines_30m",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not manifest["all_checksums_verified"]:
        raise RuntimeError("archive manifest does not verify every official checksum")

    report: dict[str, Any] = {
        "schema_version": "binance_bitcoin_derivatives_integrity:v1",
        "dataset_manifest": str(root / "manifest.json"),
        "archive_count": manifest["archive_count"],
        "official_checksums_verified": manifest["all_checksums_verified"],
        "products": {},
    }
    timestamp_sets: list[set[pd.Timestamp]] = []
    expected_30m = pd.date_range(
        "2020-01-01", "2026-01-01", freq="30min", inclusive="left", tz="UTC"
    )
    expected_set = set(expected_30m)
    for product in KLINE_PRODUCTS:
        path = root / "normalized" / f"{product}.parquet"
        frame = pd.read_parquet(path)
        timestamps = frame["open_time"]
        actual = set(timestamps)
        timestamp_sets.append(actual)
        report["products"][product] = {
            "path": str(path),
            "sha256": sha256(path),
            "rows": len(frame),
            "first_timestamp": timestamps.min().isoformat(),
            "last_timestamp": timestamps.max().isoformat(),
            "duplicate_timestamps": int(timestamps.duplicated().sum()),
            "off_grid_timestamps": int(
                (~timestamps.isin(expected_30m)).sum()
            ),
            "missing_30m_timestamps": len(expected_set - actual),
            "null_cells": int(frame.isna().sum().sum()),
        }
        if timestamps.duplicated().any():
            raise RuntimeError(f"duplicate timestamps: {product}")

    common = set.intersection(*timestamp_sets)
    union = set.union(*timestamp_sets)
    report["synchronization"] = {
        "five_product_union_timestamps": len(union),
        "five_product_common_timestamps": len(common),
        "timestamps_not_common_to_all": len(union - common),
        "common_coverage_fraction": len(common) / len(expected_30m),
        "first_common_timestamp": min(common).isoformat(),
        "last_common_timestamp": max(common).isoformat(),
        "policy": "Use only timestamps present in every required product; never fill prices.",
    }

    funding_path = root / "normalized" / "funding_rate.parquet"
    funding = pd.read_parquet(funding_path)
    report["products"]["funding_rate"] = {
        "path": str(funding_path),
        "sha256": sha256(funding_path),
        "rows": len(funding),
        "first_timestamp": funding["calc_time"].min().isoformat(),
        "last_timestamp": funding["calc_time"].max().isoformat(),
        "duplicate_timestamps": int(funding["calc_time"].duplicated().sum()),
        "null_rates": int(funding["last_funding_rate"].isna().sum()),
        "funding_interval_hours": {
            str(key): int(value)
            for key, value in funding["funding_interval_hours"].value_counts().items()
        },
        "availability_policy": "A settled funding rate becomes usable at or after calc_time, never before.",
    }

    metrics_path = root / "normalized" / "futures_metrics_5m.parquet"
    metrics_30m_path = root / "normalized" / "futures_metrics_30m.parquet"
    metrics = pd.read_parquet(metrics_path)
    metrics_30m = pd.read_parquet(metrics_30m_path)
    expected_5m = pd.date_range(
        "2020-09-01", "2026-01-01", freq="5min", inclusive="left", tz="UTC"
    )
    actual_metrics = set(metrics["create_time"])
    expected_metrics = set(expected_5m)
    report["products"]["futures_metrics_5m"] = {
        "path": str(metrics_path),
        "sha256": sha256(metrics_path),
        "rows": len(metrics),
        "first_timestamp": metrics["create_time"].min().isoformat(),
        "last_timestamp": metrics["create_time"].max().isoformat(),
        "duplicate_timestamps": int(metrics["create_time"].duplicated().sum()),
        "exact_grid_timestamps": len(actual_metrics & expected_metrics),
        "missing_exact_5m_grid_timestamps": len(expected_metrics - actual_metrics),
        "off_grid_actual_timestamps": len(actual_metrics - expected_metrics),
        "null_counts": {key: int(value) for key, value in metrics.isna().sum().items()},
        "availability_policy": "Use each observation only at or after its actual create_time; off-grid rows are not rounded backward.",
    }
    report["products"]["futures_metrics_30m"] = {
        "path": str(metrics_30m_path),
        "sha256": sha256(metrics_30m_path),
        "rows": len(metrics_30m),
        "first_timestamp": metrics_30m["create_time"].min().isoformat(),
        "last_timestamp": metrics_30m["create_time"].max().isoformat(),
        "duplicate_timestamps": int(metrics_30m["create_time"].duplicated().sum()),
        "null_counts": {key: int(value) for key, value in metrics_30m.isna().sum().items()},
        "aggregation": "Last observation in (t-30m, t], labeled t; no backward fill.",
    }
    report["honest_limits"] = [
        "The archive is Binance-only and does not represent consolidated global spot or derivatives markets.",
        "Metrics ratio fields have substantial missing history; open interest fields are much more complete.",
        "Historical liquidation snapshots are not present under the official BTCUSDT archive prefix.",
        "Public bookTicker history is enormous and begins only in 2023-05; it was not needed or downloaded.",
        "Public bookDepth is percentage-depth snapshots from 2023, not a reconstructable full order-event book.",
        "Archive availability is free/public access, but the repository does not state an open-data license; Binance terms still apply.",
        "No future-return relationship was calculated by this integrity audit.",
    ]
    output = root / "integrity_report.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "common_fraction": report["synchronization"]["common_coverage_fraction"], "metrics_rows": len(metrics), "funding_rows": len(funding)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
