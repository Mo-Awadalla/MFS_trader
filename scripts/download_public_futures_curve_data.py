"""Download pinned public futures carry data from the pysystemtrade repository."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests

SOURCE_REPOSITORY = "pst-group/pysystemtrade"
SOURCE_COMMIT = "883c8681cf880d83acad5c39b842403a8eac5676"
SOURCE_BASE = f"https://raw.githubusercontent.com/{SOURCE_REPOSITORY}/{SOURCE_COMMIT}"
DEFAULT_OUTPUT = Path("external_artifacts/pysystemtrade_futures_data") / SOURCE_COMMIT[:12]
DEFAULT_START = "2010-01-01"
NORMALIZATION = (
    "Source-compatible business-day last observation. Carry price, carry contract, "
    "held price, and held contract coexist on one source timestamp; no forward filling."
)

INSTRUMENTS = (
    "SP500",
    "NASDAQ",
    "US2",
    "US5",
    "US10",
    "US20",
    "EUR",
    "JPY",
    "GBP",
    "CRUDE_W",
    "GAS_US",
    "GOLD",
    "COPPER",
    "CORN",
    "SOYBEAN",
)

MULTIPLE_COLUMNS = {
    "DATETIME",
    "CARRY",
    "CARRY_CONTRACT",
    "PRICE",
    "PRICE_CONTRACT",
    "FORWARD",
    "FORWARD_CONTRACT",
}


def _download(session: requests.Session, relative_path: str, output_path: Path) -> dict[str, Any]:
    url = f"{SOURCE_BASE}/{relative_path}"
    response = session.get(url, timeout=120)
    response.raise_for_status()
    content = response.content
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    return {
        "source_url": url,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _read_timeseries(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "DATETIME" not in frame.columns:
        raise ValueError(f"{path} has no DATETIME column")
    frame["DATETIME"] = pd.to_datetime(frame["DATETIME"], errors="raise")
    return frame.sort_values("DATETIME").set_index("DATETIME")


def _daily_panel(multiple_path: Path, adjusted_path: Path, start: str) -> pd.DataFrame:
    multiple = _read_timeseries(multiple_path)
    missing = MULTIPLE_COLUMNS.difference({"DATETIME", *multiple.columns})
    if missing:
        raise ValueError(f"{multiple_path} is missing columns: {sorted(missing)}")

    adjusted = _read_timeseries(adjusted_path)
    if "price" not in adjusted.columns:
        raise ValueError(f"{adjusted_path} has no price column")

    price_rows = multiple.dropna(subset=["PRICE", "PRICE_CONTRACT"])
    carry_rows = multiple.dropna(
        subset=["PRICE", "PRICE_CONTRACT", "CARRY", "CARRY_CONTRACT"]
    )
    forward_rows = multiple.dropna(subset=["FORWARD", "FORWARD_CONTRACT"])

    price_daily = price_rows[["PRICE", "PRICE_CONTRACT"]].resample("1B").last()
    carry_daily = carry_rows[
        ["PRICE", "PRICE_CONTRACT", "CARRY", "CARRY_CONTRACT"]
    ].resample("1B").last()
    forward_daily = forward_rows[["FORWARD", "FORWARD_CONTRACT"]].resample("1B").last()
    adjusted_daily = adjusted[["price"]].resample("1B").last().rename(
        columns={"price": "ADJUSTED"}
    )

    daily = price_daily.join(carry_daily, how="outer", rsuffix="_CARRY_ROW")
    carry_ready = daily["CARRY"].notna()
    daily.loc[carry_ready, "PRICE"] = daily.loc[carry_ready, "PRICE_CARRY_ROW"]
    daily.loc[carry_ready, "PRICE_CONTRACT"] = daily.loc[
        carry_ready, "PRICE_CONTRACT_CARRY_ROW"
    ]
    daily = daily.drop(columns=["PRICE_CARRY_ROW", "PRICE_CONTRACT_CARRY_ROW"])
    daily = daily.join(forward_daily, how="outer").join(adjusted_daily, how="outer")
    daily = daily[
        [
            "CARRY",
            "CARRY_CONTRACT",
            "PRICE",
            "PRICE_CONTRACT",
            "FORWARD",
            "FORWARD_CONTRACT",
            "ADJUSTED",
        ]
    ]
    daily.index.name = "DATE"
    return daily.loc[pd.Timestamp(start) :]


def _instrument_stats(instrument: str, daily: pd.DataFrame) -> dict[str, Any]:
    paired = daily[["PRICE", "CARRY", "PRICE_CONTRACT", "CARRY_CONTRACT"]].notna().all(axis=1)
    return {
        "instrument": instrument,
        "start": daily.index.min().date().isoformat(),
        "end": daily.index.max().date().isoformat(),
        "daily_rows": len(daily),
        "carry_ready_rows": int(paired.sum()),
        "carry_ready_fraction": float(paired.mean()),
        "price_contract_count": int(daily["PRICE_CONTRACT"].nunique(dropna=True)),
        "carry_contract_count": int(daily["CARRY_CONTRACT"].nunique(dropna=True)),
        "duplicate_dates": int(daily.index.duplicated().sum()),
        "has_volume": "VOLUME" in daily.columns,
        "has_open_interest": "OPEN_INTEREST" in daily.columns,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and normalize public pysystemtrade futures carry data"
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start", default=DEFAULT_START)
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    raw_dir = output_dir / "raw"
    daily_dir = output_dir / "daily"
    session = requests.Session()
    session.headers["User-Agent"] = "mfs-trader public research data downloader"

    files: dict[str, dict[str, Any]] = {}
    for relative_path in (
        "LICENSE",
        "README.md",
        "docs/data.md",
        "data/futures/csvconfig/instrumentconfig.csv",
        "data/futures/csvconfig/rollconfig.csv",
        "data/futures/csvconfig/spreadcosts.csv",
    ):
        target = raw_dir / relative_path
        files[relative_path] = _download(session, relative_path, target)

    stats = []
    for instrument in INSTRUMENTS:
        multiple_relative = f"data/futures/multiple_prices_csv/{instrument}.csv"
        adjusted_relative = f"data/futures/adjusted_prices_csv/{instrument}.csv"
        multiple_path = raw_dir / multiple_relative
        adjusted_path = raw_dir / adjusted_relative
        files[multiple_relative] = _download(session, multiple_relative, multiple_path)
        files[adjusted_relative] = _download(session, adjusted_relative, adjusted_path)

        daily = _daily_panel(multiple_path, adjusted_path, args.start)
        daily_path = daily_dir / f"{instrument}.parquet"
        daily_path.parent.mkdir(parents=True, exist_ok=True)
        daily.to_parquet(daily_path)
        stats.append(_instrument_stats(instrument, daily))

    manifest = {
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": SOURCE_COMMIT,
        "source_license": "GPL-3.0",
        "source_warning": (
            "Research/backtest data distributed by pysystemtrade. The source documentation "
            "calls the shipped CSV data stale and unsuitable for production."
        ),
        "downloaded_files": files,
        "normalization": NORMALIZATION,
        "requested_start": args.start,
        "known_limitations": [
            "Source data ends on 2024-03-28.",
            "Multiple-price files contain selected price, carry, and forward contracts rather than every listed contract.",
            "No volume or open-interest history is included.",
            "Roll calendars and multiple-price series may contain manual curation by the source maintainer.",
            "Use for research only, not live production.",
        ],
        "instruments": stats,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    total_rows = sum(item["daily_rows"] for item in stats)
    print(f"source={SOURCE_REPOSITORY}@{SOURCE_COMMIT}")
    print(f"instruments={len(stats)}")
    print(f"daily_rows={total_rows}")
    print(f"output={output_dir}")
    print(f"manifest={manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
