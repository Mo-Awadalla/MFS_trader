"""Audit the free ES intraday samples collected during data-source research.

The script never downloads data and never reads API credentials. It validates
the local vendor/GitHub/Yahoo artifacts, reports their usable fields and
coverage, and cross-checks overlapping FirstRate Data and Yahoo OHLCV bars.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pandas as pd

DEFAULT_ROOT = Path("external_artifacts/public_intraday_futures_samples")
FIRST_RATE_RELATIVE = Path("firstratedata/frd_sample_futures_ES.zip")
GITHUB_RELATIVE = Path("github_pa_sampledata/pa-sampledata-master.zip")
YAHOO_RELATIVE = Path("yahoo/ES_F_1m_2026-07-18_2026-07-25.json")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _first_rate(path: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    with ZipFile(path) as archive:
        names = archive.namelist()
        required = {"ES_1min_sample.csv", "_readme_documentation.txt"}
        missing = required.difference(names)
        if missing:
            raise ValueError(f"FirstRate archive is missing {sorted(missing)}")

        frame = pd.read_csv(io.BytesIO(archive.read("ES_1min_sample.csv")))
        readme = archive.read("_readme_documentation.txt").decode(
            "utf-8-sig", errors="replace"
        )

    expected = ["timestamp", "open", "high", "low", "close", "volume"]
    if frame.columns.tolist() != expected:
        raise ValueError(f"Unexpected FirstRate columns: {frame.columns.tolist()}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="raise")
    frame = frame.set_index("timestamp").sort_index()

    return (
        {
            "path": path.as_posix(),
            "sha256": _sha256(path),
            "archive_bytes": path.stat().st_size,
            "members": names,
            "one_minute_rows": int(len(frame)),
            "start": frame.index.min().isoformat(),
            "end": frame.index.max().isoformat(),
            "duplicate_timestamps": int(frame.index.duplicated().sum()),
            "columns": frame.columns.tolist(),
            "timezone_claim": (
                "America/New_York"
                if "Timezone is US Eastern Time" in readme
                else "not documented"
            ),
            "contract_identity": "continuous root only; raw contract not present",
            "quote_fields": False,
            "aggressor_side": False,
            "license_reference_present": "firstratedata.com/about/license" in readme,
        },
        frame,
    )


def _github(path: Path) -> dict[str, Any]:
    with ZipFile(path) as archive:
        csv_names = sorted(
            name
            for name in archive.namelist()
            if "/data/ES/" in name and name.lower().endswith(".csv")
        )
        license_names = [
            name
            for name in archive.namelist()
            if Path(name).name.lower() in {"license", "license.md", "copying"}
        ]
        if not csv_names:
            raise ValueError("GitHub archive contains no ES CSV files")

        frames = []
        for name in csv_names:
            frame = pd.read_csv(
                io.BytesIO(archive.read(name)),
                header=None,
                names=["timestamp", "open", "high", "low", "close"],
            )
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="raise")
            frames.append(frame)

    combined = pd.concat(frames, ignore_index=True).sort_values("timestamp")
    return {
        "path": path.as_posix(),
        "sha256": _sha256(path),
        "archive_bytes": path.stat().st_size,
        "csv_files": len(csv_names),
        "five_minute_rows": int(len(combined)),
        "start": combined["timestamp"].min().isoformat(),
        "end": combined["timestamp"].max().isoformat(),
        "duplicate_timestamps": int(combined["timestamp"].duplicated().sum()),
        "columns": ["timestamp", "open", "high", "low", "close"],
        "timezone_claim": "not documented",
        "contract_identity": "ES root only; raw contract not present",
        "volume": False,
        "quote_fields": False,
        "aggressor_side": False,
        "repository_license_present": bool(license_names),
    }


def _yahoo(path: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    chart = payload["chart"]
    if chart.get("error") is not None or not chart.get("result"):
        raise ValueError(f"Yahoo chart error: {chart.get('error')}")

    result = chart["result"][0]
    timestamps = pd.to_datetime(result["timestamp"], unit="s", utc=True)
    timezone = result["meta"].get("exchangeTimezoneName", "UTC")
    index = timestamps.tz_convert(timezone).tz_localize(None)
    frame = pd.DataFrame(result["indicators"]["quote"][0], index=index)
    frame.index.name = "timestamp"
    frame = frame.dropna(subset=["close"]).sort_index()

    return (
        {
            "path": path.as_posix(),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
            "symbol": result["meta"].get("symbol"),
            "exchange": result["meta"].get("exchangeName"),
            "timezone": timezone,
            "rows_with_close": int(len(frame)),
            "start": frame.index.min().isoformat(),
            "end": frame.index.max().isoformat(),
            "duplicate_timestamps": int(frame.index.duplicated().sum()),
            "columns": frame.columns.tolist(),
            "contract_identity": "Yahoo continuous ticker; raw contract not present",
            "quote_fields": False,
            "aggressor_side": False,
        },
        frame,
    )


def _cross_check(first_rate: pd.DataFrame, yahoo: pd.DataFrame) -> dict[str, Any]:
    columns = ["open", "high", "low", "close", "volume"]
    joined = first_rate[columns].join(
        yahoo[columns],
        how="inner",
        lsuffix="_firstratedata",
        rsuffix="_yahoo",
    )
    if joined.empty:
        return {"overlap_rows": 0}

    result: dict[str, Any] = {
        "overlap_rows": int(len(joined)),
        "start": joined.index.min().isoformat(),
        "end": joined.index.max().isoformat(),
    }
    for column in columns:
        difference = (
            joined[f"{column}_firstratedata"] - joined[f"{column}_yahoo"]
        ).abs()
        result[column] = {
            "exact_rows": int(difference.eq(0).sum()),
            "exact_fraction": float(difference.eq(0).mean()),
            "max_absolute_difference": float(difference.max()),
            "mean_absolute_difference": float(difference.mean()),
        }
    ohlc_left = joined[[f"{column}_firstratedata" for column in columns[:4]]]
    ohlc_right = joined[[f"{column}_yahoo" for column in columns[:4]]]
    result["all_ohlc_exact_rows"] = int(
        (ohlc_left.to_numpy() == ohlc_right.to_numpy()).all(axis=1).sum()
    )
    result["all_ohlc_exact_fraction"] = (
        result["all_ohlc_exact_rows"] / result["overlap_rows"]
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    first_rate_path = root / FIRST_RATE_RELATIVE
    github_path = root / GITHUB_RELATIVE
    yahoo_path = root / YAHOO_RELATIVE
    for path in (first_rate_path, github_path, yahoo_path):
        if not path.exists():
            raise FileNotFoundError(path)

    first_rate, first_rate_frame = _first_rate(first_rate_path)
    github = _github(github_path)
    yahoo, yahoo_frame = _yahoo(yahoo_path)
    audit = {
        "purpose": "Free-source ES intraday data feasibility; not strategy evidence",
        "sources": {
            "firstratedata_sample": first_rate,
            "github_carpethooligan_pa_sampledata": github,
            "yahoo_es_f_recent": yahoo,
        },
        "cross_source_check": _cross_check(first_rate_frame, yahoo_frame),
        "decision": {
            "price_bar_plumbing": "pass",
            "multi_year_price_test": "fail",
            "aggressor_order_flow": "fail",
            "executable_mes_quotes": "fail",
            "promotion_quality_backtest": "fail",
        },
    }
    rendered = json.dumps(audit, indent=2) + "\n"
    if args.output is not None:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(output)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
