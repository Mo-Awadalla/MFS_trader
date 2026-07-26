"""Validate the Massive ES continuous-bar artifact without network access."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

NY = "America/New_York"
REQUIRED_COLUMNS = {
    "ticker",
    "window_start",
    "session_end_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.artifact_root
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    bars_path = root / "selected_contract_1min.parquet"
    mapping_path = root / "previous_session_volume_roll_map.parquet"
    candidates_path = root / "candidate_session_bars.parquet"
    for path in (bars_path, mapping_path, candidates_path):
        expected_hash = manifest["files"][path.name]["sha256"]
        actual_hash = _sha256(path)
        if actual_hash != expected_hash:
            raise ValueError(f"SHA-256 mismatch for {path}")

    bars = pd.read_parquet(bars_path)
    mapping = pd.read_parquet(mapping_path)
    candidates = pd.read_parquet(candidates_path)
    missing_columns = REQUIRED_COLUMNS.difference(bars.columns)
    if missing_columns:
        raise ValueError(f"Missing bar columns: {sorted(missing_columns)}")

    duplicate_keys = int(bars.duplicated(["ticker", "window_start"]).sum())
    null_counts = {
        column: int(bars[column].isna().sum())
        for column in ["open", "high", "low", "close", "volume"]
    }
    if duplicate_keys or any(null_counts.values()):
        raise ValueError(
            f"Invalid bars: duplicates={duplicate_keys}, nulls={null_counts}"
        )

    bars["session_end_date"] = bars["session_end_date"].astype(str)
    mapping["session_end_date"] = mapping["session_end_date"].astype(str)
    merged = bars.merge(
        mapping,
        on=["session_end_date", "ticker"],
        how="left",
        indicator=True,
        validate="many_to_one",
    )
    wrong_contract_rows = int(merged["_merge"].ne("both").sum())
    if wrong_contract_rows:
        raise ValueError(f"{wrong_contract_rows} bars do not match the roll map")

    timestamp = pd.to_datetime(bars["window_start"], unit="ns", utc=True).dt.tz_convert(NY)
    bars["clock"] = timestamp.dt.strftime("%H:%M")
    rth = bars[bars["clock"].between("09:30", "15:59")]
    rth_counts = rth.groupby("session_end_date").size()
    full_rth_sessions = int(rth_counts.eq(390).sum())
    short_rth_sessions = {
        str(key): int(value) for key, value in rth_counts[rth_counts.lt(390)].items()
    }

    candidate_dates = set(candidates["session_end_date"].astype(str))
    mapped_dates = set(mapping["session_end_date"])
    bar_dates = set(bars["session_end_date"])
    audit: dict[str, Any] = {
        "artifact_root": root.as_posix(),
        "source": manifest["source"],
        "year": manifest["year"],
        "api_calls": manifest["api_calls"],
        "rows": int(len(bars)),
        "mapping_business_dates": int(len(mapping)),
        "dates_with_minute_bars": int(len(bar_dates)),
        "candidate_session_dates": int(len(candidate_dates)),
        "mapped_dates_without_bars": sorted(mapped_dates.difference(bar_dates)),
        "candidate_dates_not_in_mapping": sorted(candidate_dates.difference(mapped_dates)),
        "duplicate_ticker_window_rows": duplicate_keys,
        "null_counts": null_counts,
        "wrong_contract_rows": wrong_contract_rows,
        "full_390_minute_rth_sessions": full_rth_sessions,
        "short_rth_sessions": short_rth_sessions,
        "roll_intervals": manifest["intervals"],
        "hashes_verified": True,
    }
    rendered = json.dumps(audit, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
