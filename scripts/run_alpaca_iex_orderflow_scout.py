"""Acquire and evaluate one locked partition of the frozen Alpaca IEX order-flow scout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.alpaca_l1 import AlpacaHistoricalL1Client
from data.l1_validate import validate_quotes, validate_trades
from data.validate import QualityResult
from research.alpaca_iex_orderflow_scout import (
    SPEC_PATH,
    evaluate_scout,
    format_report,
    load_spec,
    prepare_session_features,
)
from storage.microstructure_io import read_events, sha256_file, write_events

OUTPUT_ROOT = Path("data/parquet/alpaca_iex_orderflow_v1")
PARTITION_KEYS = {
    "development": "development",
    "internal_validation": "internal_validation",
    "final_holdout": "final_holdout",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partition", choices=tuple(PARTITION_KEYS), default="development")
    parser.add_argument("--spec", type=Path, default=SPEC_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args()


def _partition_guard(partition: str, output_dir: Path) -> None:
    prerequisite = {
        "development": [],
        "internal_validation": ["development"],
        "final_holdout": ["development", "internal_validation"],
    }[partition]
    for name in prerequisite:
        path = output_dir / name / "report.json"
        if not path.exists():
            raise RuntimeError(f"{partition} locked: missing prerequisite report {path}")
        report = json.loads(path.read_text(encoding="utf-8"))
        if not bool(report.get("passed")):
            raise RuntimeError(f"{partition} locked: prerequisite {name} did not pass")


def _window(session_date: str) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    zone = "America/New_York"
    start = pd.Timestamp(f"{session_date} 09:30:00", tz=zone).tz_convert("UTC")
    split = pd.Timestamp(f"{session_date} 10:00:00", tz=zone).tz_convert("UTC")
    end = pd.Timestamp(f"{session_date} 10:30:05", tz=zone).tz_convert("UTC")
    return start, split, end


def _download_event_chunks(
    client: AlpacaHistoricalL1Client,
    *,
    event_type: str,
    symbol: str,
    start: pd.Timestamp,
    split: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    downloader = client.download_trades if event_type == "trades" else client.download_quotes
    chunks = [
        downloader(symbol, start, split, page_size=10_000, max_pages=100),
        downloader(
            symbol,
            split + pd.Timedelta(nanoseconds=1),
            end,
            page_size=10_000,
            max_pages=100,
        ),
    ]
    if not all(bool(chunk.metadata["pagination_complete"]) for chunk in chunks):
        raise RuntimeError(f"{symbol} {event_type} pagination cap reached")
    frame = pd.concat([chunk.data for chunk in chunks], ignore_index=True)
    frame = frame.sort_values(["timestamp", "page_index", "row_index"], kind="stable")
    return frame.reset_index(drop=True), [chunk.metadata for chunk in chunks]


def _session_paths(root: Path, partition: str, symbol: str, session_date: str) -> dict[str, Path]:
    directory = root / partition / symbol / session_date
    return {
        "directory": directory,
        "trades": directory / "trades.parquet",
        "quotes": directory / "quotes.parquet",
        "features": directory / "features.parquet",
        "manifest": directory / "manifest.json",
    }


def _write_session(
    client: AlpacaHistoricalL1Client,
    *,
    output_dir: Path,
    partition: str,
    symbol: str,
    session_date: str,
    spec_path: Path,
) -> pd.DataFrame:
    paths = _session_paths(output_dir, partition, symbol, session_date)
    start, split, end = _window(session_date)
    trades, trade_downloads = _download_event_chunks(
        client,
        event_type="trades",
        symbol=symbol,
        start=start,
        split=split,
        end=end,
    )
    quotes, quote_downloads = _download_event_chunks(
        client,
        event_type="quotes",
        symbol=symbol,
        start=start,
        split=split,
        end=end,
    )
    trade_quality = validate_trades(
        trades,
        symbol=symbol,
        requested_start=start,
        requested_end=end,
    )
    quote_quality = validate_quotes(
        quotes,
        symbol=symbol,
        requested_start=start,
        requested_end=end,
    )
    if trade_quality.result == QualityResult.FAIL or quote_quality.result == QualityResult.FAIL:
        raise RuntimeError(
            f"{symbol} {session_date} quality failure: "
            f"trades={trade_quality.result.value}, quotes={quote_quality.result.value}"
        )

    features = prepare_session_features(
        trades,
        quotes,
        symbol=symbol,
        session_date=session_date,
    )
    if len(features) != 11 or int(features["next_midpoint_return"].notna().sum()) != 11:
        raise RuntimeError(
            f"{symbol} {session_date} expected 11 complete signal rows, got {len(features)}"
        )

    paths["directory"].mkdir(parents=True, exist_ok=True)
    files = {
        "trades": write_events(trades, paths["trades"]),
        "quotes": write_events(quotes, paths["quotes"]),
        "features": write_events(features, paths["features"]),
    }
    for name, metadata in files.items():
        metadata["path"] = paths[name].name
    manifest = {
        "schema_version": "alpaca_iex_orderflow_session:v1",
        "specification_id": "Alpaca-IEX-OrderFlow-Predictiveness-v1",
        "specification_sha256": sha256_file(spec_path),
        "partition": partition,
        "symbol": symbol,
        "session_date": session_date,
        "provider": "alpaca",
        "feed": "iex",
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "credentials_recorded": False,
        "downloads": {"trades": trade_downloads, "quotes": quote_downloads},
        "quality": {
            "trades": trade_quality.to_dict(),
            "quotes": quote_quality.to_dict(),
        },
        "feature_rows": len(features),
        "files": files,
    }
    temporary = paths["manifest"].with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(paths["manifest"])
    return features


def main() -> int:
    args = _parse_args()
    load_dotenv()
    spec_path = args.spec.resolve()
    spec = load_spec(spec_path)
    partition = str(args.partition)
    output_dir = args.output_dir.resolve()
    try:
        _partition_guard(partition, output_dir)
    except RuntimeError as exc:
        print(f"BLOCKED: {exc}")
        return 2
    partition_spec = spec["partitions"][PARTITION_KEYS[partition]]
    symbols = [str(value) for value in spec["symbols"]]
    sessions = [str(value) for value in partition_spec["sessions"]]
    client = AlpacaHistoricalL1Client(max_total_bytes=100_000_000, max_duration_seconds=300.0)
    if not client.is_available():
        print("BLOCKED: ALPACA_API_KEY and ALPACA_API_SECRET are required")
        return 2

    frames: list[pd.DataFrame] = []
    total = len(symbols) * len(sessions)
    completed = 0
    for session_date in sessions:
        for symbol in symbols:
            paths = _session_paths(output_dir, partition, symbol, session_date)
            if paths["manifest"].exists() and paths["features"].exists() and not args.refresh:
                features = read_events(paths["features"])
            else:
                features = _write_session(
                    client,
                    output_dir=output_dir,
                    partition=partition,
                    symbol=symbol,
                    session_date=session_date,
                    spec_path=spec_path,
                )
            frames.append(features)
            completed += 1
            print(f"[{completed}/{total}] {partition} {session_date} {symbol} rows={len(features)}")

    panel = pd.concat(frames, ignore_index=True)
    report = evaluate_scout(panel, spec)
    partition_dir = output_dir / partition
    partition_dir.mkdir(parents=True, exist_ok=True)
    panel_metadata = write_events(panel, partition_dir / "panel.parquet")
    panel_metadata["path"] = "panel.parquet"
    report["partition"] = partition
    report["panel_file"] = panel_metadata
    report["specification_sha256"] = sha256_file(spec_path)
    (partition_dir / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (partition_dir / "report.md").write_text(
        format_report(report, partition=partition), encoding="utf-8"
    )
    print(format_report(report, partition=partition))
    print(f"report={partition_dir / 'report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
