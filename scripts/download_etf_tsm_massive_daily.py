"""Download and persist the frozen ETF TSM daily universe from Massive."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from data.base import BaseDownloader, DownloadRequest
from data.massive_downloader import MASSIVE_ETF_TSM_SYMBOLS, MassiveDownloader
from data.validate import QualityResult, validate_ohlcv
from storage.parquet_io import append_bars, parquet_path

SOURCE = "massive_rest"
DEFAULT_STORAGE_DIR = "data/parquet/equity"


def download_and_store(
    downloader: BaseDownloader,
    *,
    start: str,
    end: str | None = None,
    storage_dir: str | Path = DEFAULT_STORAGE_DIR,
    symbols: tuple[str, ...] = MASSIVE_ETF_TSM_SYMBOLS,
    refresh: bool = False,
) -> dict[str, Any]:
    """Download, quality-gate, store, and record provenance for the ETF universe."""
    storage_dir = Path(storage_dir)
    manifest_path = storage_dir / SOURCE / "manifest.json"
    summary: dict[str, Any] = {
        "source": SOURCE,
        "status": "in_progress",
        "symbols": {},
        "requested_symbols": list(symbols),
        "start": start,
        "end": end,
    }
    _write_manifest(manifest_path, summary)

    for symbol in symbols:
        path = parquet_path(storage_dir, symbol, "1d", source=SOURCE)
        if path.exists() and not refresh:
            summary["symbols"][symbol] = {"status": "skipped", "path": str(path)}
            _write_manifest(manifest_path, summary)
            continue

        try:
            result = downloader.download(
                DownloadRequest(symbol=symbol, start_date=start, end_date=end, frequency="1d")
            )
            report = validate_ohlcv(
                result.data,
                symbol=symbol,
                source=SOURCE,
                frequency="1d",
                expected_interval_seconds=86_400,
                is_live=False,
            )
            if report.result == QualityResult.FAIL:
                summary["symbols"][symbol] = {
                    "status": "quality_fail",
                    "issues": report.issues_json,
                }
            else:
                new_rows = append_bars(result.data, path)
                summary["symbols"][symbol] = {
                    "status": "stored",
                    "path": str(path),
                    "new_rows": new_rows,
                    "quality": report.result.value,
                    "quality_issues": report.issues_json,
                    "provenance": result.metadata,
                }
        except Exception as exc:  # noqa: BLE001 - batch continues to report per-symbol failures.
            summary["symbols"][symbol] = {"status": "error", "error": str(exc)}
        _write_manifest(manifest_path, summary)

    failed = [
        symbol
        for symbol, result in summary["symbols"].items()
        if result["status"] in {"error", "quality_fail"}
    ]
    summary["status"] = "failed" if failed else "complete"
    summary["failed_symbols"] = failed
    _write_manifest(manifest_path, summary)
    return summary


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the frozen ETF TSM Massive daily universe")
    parser.add_argument("--start", default="2005-01-01")
    parser.add_argument("--end")
    parser.add_argument("--storage-dir", default=DEFAULT_STORAGE_DIR)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    downloader = MassiveDownloader()
    if not downloader.is_available():
        print("ERROR: MASSIVE_API_KEY is not configured")
        return 2

    summary = download_and_store(
        downloader,
        start=args.start,
        end=args.end,
        storage_dir=args.storage_dir,
        refresh=args.refresh,
    )
    for symbol, result in summary["symbols"].items():
        print(f"{result['status'].upper():12s} {symbol:5s} {result.get('path', '')}")
    print(f"status={summary['status']} manifest={Path(args.storage_dir) / SOURCE / 'manifest.json'}")
    return 0 if summary["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
