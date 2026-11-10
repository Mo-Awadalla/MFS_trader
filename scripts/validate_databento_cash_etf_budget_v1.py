"""Validate the local Databento cash-ETF package without API calls."""

from __future__ import annotations

import hashlib
import json
import sys
import warnings
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import databento as db  # noqa: E402

DATA_ROOT = ROOT / "external_artifacts" / "databento_cash_etf_budget_v1"
OUTPUT = DATA_ROOT / "validation_report.json"
CHUNK_ROWS = 1_000_000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scalar(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def inspect(path: Path) -> dict[str, Any]:
    store = db.read_dbn(path)
    result: dict[str, Any] = {
        "path": path.relative_to(ROOT).as_posix(),
        "filename_marks_partial": ".partial." in path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "dataset": store.dataset,
        "schema": str(store.schema),
        "metadata_start": scalar(store.start),
        "metadata_end": scalar(store.end),
        "metadata_stype_in": str(store.metadata.stype_in),
        "metadata_stype_out": str(store.metadata.stype_out),
        "mapping_keys": sorted(store.mappings),
    }
    rows = 0
    chunks = 0
    first_timestamp: pd.Timestamp | None = None
    last_timestamp: pd.Timestamp | None = None
    monotonic = True
    columns: list[str] = []
    symbols: Counter[str] = Counter()
    instrument_ids: set[int] = set()
    sides: Counter[str] = Counter()
    crossed_quotes = 0
    nonpositive_quotes = 0
    invalid_trade_prices = 0
    nonpositive_trade_sizes = 0
    iteration_error: str | None = None

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            frames = store.to_df(count=CHUNK_ROWS, map_symbols=True)
            for frame in frames:
                chunks += 1
                if not columns:
                    columns = list(frame.columns)
                if frame.empty:
                    continue
                index = pd.DatetimeIndex(frame.index)
                chunk_first = index.min()
                chunk_last = index.max()
                if first_timestamp is None:
                    first_timestamp = chunk_first
                if last_timestamp is not None and chunk_first < last_timestamp:
                    monotonic = False
                monotonic = monotonic and bool(index.is_monotonic_increasing)
                last_timestamp = chunk_last
                rows += len(frame)
                if "symbol" in frame:
                    symbols.update(frame["symbol"].dropna().astype(str).tolist())
                if "instrument_id" in frame:
                    instrument_ids.update(
                        int(value) for value in frame["instrument_id"].dropna().unique()
                    )
                if "side" in frame:
                    sides.update(frame["side"].dropna().astype(str).tolist())
                if {"bid_px_00", "ask_px_00"}.issubset(frame.columns):
                    bid = frame["bid_px_00"]
                    ask = frame["ask_px_00"]
                    crossed_quotes += int(ask.lt(bid).sum())
                    nonpositive_quotes += int((bid.le(0) | ask.le(0)).sum())
                if "price" in frame:
                    invalid_trade_prices += int(frame["price"].le(0).sum())
                if "size" in frame:
                    nonpositive_trade_sizes += int(frame["size"].le(0).sum())
                if chunks % 10 == 0:
                    print(
                        f"{path.name}: chunks={chunks} rows={rows} "
                        f"last={last_timestamp}",
                        flush=True,
                    )
        except Exception as exc:  # Preserve a usable-prefix report for truncated files.
            iteration_error = f"{type(exc).__name__}: {exc}"
        warning_messages = [str(item.message) for item in caught]

    result.update(
        {
            "rows_decoded": rows,
            "chunks_decoded": chunks,
            "columns": columns,
            "first_record_timestamp": scalar(first_timestamp),
            "last_record_timestamp": scalar(last_timestamp),
            "monotonic_timestamps": monotonic,
            "symbols": dict(sorted(symbols.items())),
            "instrument_ids": sorted(instrument_ids),
            "sides": dict(sorted(sides.items())),
            "crossed_quotes": crossed_quotes,
            "nonpositive_quotes": nonpositive_quotes,
            "invalid_trade_prices": invalid_trade_prices,
            "nonpositive_trade_sizes": nonpositive_trade_sizes,
            "warnings": warning_messages,
            "iteration_error": iteration_error,
            "clean_eof": iteration_error is None
            and not any("truncated" in message.lower() for message in warning_messages),
        }
    )
    print(
        f"INSPECTED {result['path']} rows={rows} "
        f"last={result['last_record_timestamp']} clean_eof={result['clean_eof']}",
        flush=True,
    )
    return result


def main() -> int:
    files = sorted(DATA_ROOT.glob("*/*/*.dbn.zst"))
    if not files:
        raise RuntimeError(f"No DBN files found under {DATA_ROOT}")
    summaries = [inspect(path) for path in files]
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "paid_api_calls_made": False,
        "files_found": len(files),
        "all_clean_eof": all(item["clean_eof"] for item in summaries),
        "partial_files": [
            item["path"] for item in summaries if item["filename_marks_partial"]
        ],
        "files": summaries,
    }
    temporary = OUTPUT.with_suffix(".partial.json")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps(payload, indent=2), flush=True)
    return 0 if payload["all_clean_eof"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
