"""Audit, download, and evaluate the frozen SEC Item 2.02 continuation scout."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.alpaca_event_bars import AlpacaEventBarsDownloader, download_event_sessions
from research.sec_item_202_premarket_continuation_scout import (
    SPEC_PATH,
    build_event_panel,
    evaluate_scout,
    format_report,
    load_spec,
    select_eligible_events,
    serializable_report,
)
from research.universes.residual_reversal_v1 import stock_symbols

OUTPUT_ROOT = Path("data/parquet/sec_item_202_premarket_continuation_v1")
EVENTS_PATH = Path("data/parquet/sec_filings/sec_filing_events.parquet")
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
    parser.add_argument("--events", type=Path, default=EVENTS_PATH)
    parser.add_argument("--bars", type=Path)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args()


def _audit(events: pd.DataFrame) -> dict[str, object]:
    local = pd.to_datetime(events["acceptance_datetime"], utc=True).dt.tz_convert(
        "America/New_York"
    )
    return {
        "eligible_events": int(len(events)),
        "symbols": int(events["symbol"].nunique()),
        "sessions": int(events["session_date"].nunique()),
        "first_acceptance": local.min().isoformat() if len(local) else None,
        "last_acceptance": local.max().isoformat() if len(local) else None,
        "events_by_year": {
            str(year): int(count) for year, count in events.groupby(local.dt.year).size().items()
        },
    }


def main() -> int:
    args = _parse_args()
    spec_path = args.spec.resolve()
    events_path = args.events.resolve()
    output_dir = args.output_dir.resolve()
    partition = str(args.partition)
    spec = load_spec(spec_path)
    raw_events = pd.read_parquet(events_path)
    events = select_eligible_events(
        raw_events,
        spec,
        partition=partition,
        universe=stock_symbols(),
    )
    audit = _audit(events)
    print(json.dumps(audit, indent=2))
    if args.audit_only:
        return 0
    try:
        _partition_guard(partition, output_dir)
    except RuntimeError as exc:
        print(f"BLOCKED: {exc}")
        return 2
    if events.empty:
        print("BLOCKED: no eligible events in partition")
        return 2

    partition_dir = output_dir / partition
    partition_dir.mkdir(parents=True, exist_ok=True)
    events_output = partition_dir / "eligible_events.parquet"
    events.to_parquet(events_output, index=False)

    if args.bars is not None:
        bars_source = args.bars.resolve()
        bars = pd.read_parquet(bars_source)
    else:
        load_dotenv()
        downloader = AlpacaEventBarsDownloader(
            feed=str(spec["data"]["feed"]),
            delay_seconds=float(spec["data"]["request_delay_seconds"]),
            maximum_rate_limit_retries=int(spec["data"]["maximum_rate_limit_retries"]),
        )
        if not downloader.is_available():
            print(
                "BLOCKED: Alpaca credentials are required unless --bars supplies "
                "a normalized long-form Parquet file"
            )
            return 2
        bars_source = partition_dir / "event_bars.parquet"
        bars = download_event_sessions(
            events,
            downloader,
            cache_dir=output_dir / "raw" / partition,
            benchmark=str(spec["universe"]["benchmark"]),
            frequency=str(spec["data"]["frequency"]),
            adjustment=str(spec["data"]["adjustment"]),
            timezone=str(spec["clocks"]["timezone"]),
            refresh=bool(args.refresh),
        )
        bars.to_parquet(bars_source, index=False)

    panel = build_event_panel(events, bars, spec)
    report = evaluate_scout(panel, spec, partition=partition)
    evaluated_panel = report.pop("panel")
    session_returns = report.pop("session_returns")
    panel_path = partition_dir / "panel.parquet"
    sessions_path = partition_dir / "session_returns.parquet"
    evaluated_panel.to_parquet(panel_path, index=False)
    session_returns.to_parquet(sessions_path, index=False)

    report["date_bounds"] = spec["partitions"][partition]
    report["event_audit"] = audit
    report["specification_sha256"] = _sha256(spec_path)
    report["files"] = {
        "events": {
            "path": str(events_output),
            "sha256": _sha256(events_output),
            "rows": len(events),
        },
        "bars": {
            "path": str(bars_source),
            "sha256": _sha256(bars_source),
            "rows": len(bars),
        },
        "panel": {
            "path": str(panel_path),
            "sha256": _sha256(panel_path),
            "rows": len(evaluated_panel),
        },
        "session_returns": {
            "path": str(sessions_path),
            "sha256": _sha256(sessions_path),
            "rows": len(session_returns),
        },
    }
    report_path = partition_dir / "report.json"
    report_path.write_text(
        json.dumps(serializable_report(report), indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown = format_report(report)
    (partition_dir / "report.md").write_text(markdown, encoding="utf-8")
    manifest = {
        "schema_version": "sec_item_202_premarket_continuation:v1",
        "specification_id": spec["specification_id"],
        "specification_sha256": report["specification_sha256"],
        "partition": partition,
        "data_source": spec["data"],
        "requested_bounds": spec["partitions"][partition],
        "files": report["files"],
    }
    (partition_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(markdown)
    print(f"report={report_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
