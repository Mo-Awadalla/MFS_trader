"""Download and evaluate one locked partition of the frozen Bitcoin momentum scout."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.binance_public_archive import (
    combine_months,
    download_month,
    month_keys,
    write_manifest,
)
from research.bitcoin_intraday_momentum_scout import (
    SPEC_PATH,
    build_session_panel,
    evaluate_scout,
    format_report,
    load_spec,
    serializable_report,
)

OUTPUT_ROOT = Path("data/parquet/bitcoin_us_session_close_momentum_binance_v1")
PARTITIONS = ("development", "internal_validation", "final_holdout")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _partition_guard(partition: str, output_dir: Path) -> None:
    index = PARTITIONS.index(partition)
    for prerequisite in PARTITIONS[:index]:
        report_path = output_dir / prerequisite / "report.json"
        if not report_path.exists():
            raise RuntimeError(f"{partition} locked: missing {report_path}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if not bool(report.get("passed")):
            raise RuntimeError(f"{partition} locked: {prerequisite} did not pass")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partition", choices=PARTITIONS, default="development")
    parser.add_argument("--spec", type=Path, default=SPEC_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    spec_path = args.spec.resolve()
    output_dir = args.output_dir.resolve()
    partition = str(args.partition)
    try:
        _partition_guard(partition, output_dir)
    except RuntimeError as exc:
        print(f"BLOCKED: {exc}")
        return 2
    spec = load_spec(spec_path)
    period = spec["partitions"][partition]
    symbol = str(spec["instrument"])
    interval = str(spec["interval"])
    raw_dir = output_dir / "raw"
    session = requests.Session()
    session.headers["User-Agent"] = "mfs-trader public Binance research downloader"
    results = []
    warmup_start = (pd.Timestamp(period["start"]) - pd.Timedelta(days=1)).date().isoformat()
    months = month_keys(warmup_start, period["end"])
    for index, month in enumerate(months, start=1):
        result = download_month(
            session,
            symbol=symbol,
            interval=interval,
            month=month,
            raw_dir=raw_dir,
            refresh=bool(args.refresh),
        )
        results.append(result)
        print(f"[{index}/{len(months)}] {month} rows={len(result.data)} sha256={result.metadata['actual_sha256'][:12]}")
    bars = combine_months(results, start=warmup_start, end=period["end"])
    partition_dir = output_dir / partition
    partition_dir.mkdir(parents=True, exist_ok=True)
    bars_path = partition_dir / "bars.parquet"
    bars.to_parquet(bars_path, index=False)
    panel = build_session_panel(bars, spec)
    panel = panel.loc[
        panel["session_date"].between(period["start"], period["end"], inclusive="both")
    ].reset_index(drop=True)
    report = evaluate_scout(panel, spec)
    evaluated_panel = report.pop("panel")
    panel_path = partition_dir / "panel.parquet"
    evaluated_panel.to_parquet(panel_path, index=False)
    report["partition"] = partition
    report["date_bounds"] = period
    report["specification_sha256"] = _sha256(spec_path)
    report["files"] = {
        "bars": {"path": str(bars_path), "sha256": _sha256(bars_path), "rows": len(bars)},
        "panel": {"path": str(panel_path), "sha256": _sha256(panel_path), "rows": len(evaluated_panel)},
    }
    manifest = {
        "schema_version": "binance_public_monthly_klines:v1",
        "specification_id": spec["specification_id"],
        "specification_sha256": report["specification_sha256"],
        "partition": partition,
        "provider": "binance_public_data",
        "venue": spec["venue"],
        "instrument": symbol,
        "interval": interval,
        "requested_bounds": period,
        "warmup_start": warmup_start,
        "archive_count": len(results),
        "archives": [result.metadata for result in results],
        "normalized_rows": len(bars),
        "first_open_time": bars["open_time"].min().isoformat(),
        "last_open_time": bars["open_time"].max().isoformat(),
    }
    write_manifest(partition_dir / "manifest.json", manifest)
    (partition_dir / "report.json").write_text(
        json.dumps(serializable_report(report), indent=2) + "\n", encoding="utf-8"
    )
    markdown = format_report(report, partition=partition)
    (partition_dir / "report.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"report={partition_dir / 'report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
