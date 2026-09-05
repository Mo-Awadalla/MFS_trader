"""Produce immutable Yahoo-versus-Massive ETF daily-bar parity evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from data.massive_downloader import MASSIVE_ETF_TSM_SYMBOLS
from storage.parquet_io import read_bars

DEFAULT_YAHOO_DIR = Path("data/parquet/equity/yahoo_chart")
DEFAULT_MASSIVE_DIR = Path("data/parquet/equity/massive_rest")
DEFAULT_OUTPUT = Path("runs/etf_tsm_yahoo_massive_parity/parity.json")
BAR_FIELDS = ("open", "high", "low", "close", "volume")


def compare_sources(
    yahoo_dir: str | Path = DEFAULT_YAHOO_DIR,
    massive_dir: str | Path = DEFAULT_MASSIVE_DIR,
    symbols: tuple[str, ...] = MASSIVE_ETF_TSM_SYMBOLS,
) -> dict[str, Any]:
    """Compare aligned daily bars without changing either source dataset."""
    yahoo_dir = Path(yahoo_dir)
    massive_dir = Path(massive_dir)
    symbol_reports: dict[str, Any] = {}

    for symbol in symbols:
        yahoo = _load_daily(yahoo_dir / f"{symbol}_1d.parquet")
        massive = _load_daily(massive_dir / f"{symbol}_1d.parquet")
        overlap = yahoo.index.intersection(massive.index)
        if overlap.empty:
            raise ValueError(f"no overlapping daily dates for {symbol}")
        symbol_reports[symbol] = {
            "yahoo": _coverage(yahoo),
            "massive": _coverage(massive),
            "overlap": _coverage(yahoo.loc[overlap]),
            "field_metrics": {
                field: _field_metrics(yahoo.loc[overlap, field], massive.loc[overlap, field])
                for field in BAR_FIELDS
            },
            "input_hashes": {
                "yahoo": _frame_sha256(yahoo),
                "massive": _frame_sha256(massive),
            },
        }

    return {
        "report_kind": "etf_tsm_yahoo_massive_parity",
        "status": "complete",
        "manual_review_required": True,
        "symbols": list(symbols),
        "adjustment_semantics": {
            "yahoo": "adjusted OHLC reconstructed from Yahoo adj_close",
            "massive": "Massive adjusted=true; split-adjusted prices, not dividend-adjusted",
        },
        "comparison": {
            "date_alignment": "UTC calendar date extracted from each daily-bar timestamp",
            "within_1bp_definition": "absolute difference <= max(abs(Yahoo value) * 0.0001, 1e-8)",
            "interpretation": "metrics are evidence for operator review; no automatic source promotion",
        },
        "symbols_report": symbol_reports,
    }


def write_immutable_report(report: dict[str, Any], path: str | Path = DEFAULT_OUTPUT) -> Path:
    """Write parity evidence once and refuse to overwrite it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _load_daily(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"missing parity input: {path}")
    data = read_bars(path).loc[:, list(BAR_FIELDS)].astype(float)
    if data.index.tz is None:
        raise ValueError(f"parity input must have a timezone-aware index: {path}")
    data.index = data.index.tz_convert("UTC").normalize()
    if data.index.has_duplicates:
        raise ValueError(f"parity input has duplicate calendar dates: {path}")
    return data.sort_index()


def _coverage(data: pd.DataFrame) -> dict[str, Any]:
    return {
        "row_count": len(data),
        "start": data.index[0].isoformat() if len(data) else None,
        "end": data.index[-1].isoformat() if len(data) else None,
    }


def _field_metrics(left: pd.Series, right: pd.Series) -> dict[str, float]:
    left_values = left.to_numpy(dtype=float)
    right_values = right.to_numpy(dtype=float)
    absolute = np.abs(left_values - right_values)
    denominator = np.maximum(np.abs(left_values), 1e-8)
    within_1bp = absolute <= denominator * 0.0001
    correlation = float(np.corrcoef(left_values, right_values)[0, 1])
    return {
        "mean_abs_diff": float(absolute.mean()),
        "max_abs_diff": float(absolute.max()),
        "mean_abs_relative_diff": float((absolute / denominator).mean()),
        "within_1bp_fraction": float(within_1bp.mean()),
        "correlation": correlation if np.isfinite(correlation) else 0.0,
    }


def _frame_sha256(data: pd.DataFrame) -> str:
    canonical = data.reset_index()
    canonical["timestamp"] = canonical["timestamp"].map(pd.Timestamp.isoformat)
    text = canonical.to_csv(index=False, float_format="%.17g", lineterminator="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Yahoo and Massive ETF TSM daily bars")
    parser.add_argument("--yahoo-dir", default=str(DEFAULT_YAHOO_DIR))
    parser.add_argument("--massive-dir", default=str(DEFAULT_MASSIVE_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    try:
        report = compare_sources(args.yahoo_dir, args.massive_dir)
        path = write_immutable_report(report, args.output)
    except FileExistsError:
        print(f"ERROR: immutable parity report already exists: {args.output}")
        return 2
    except (FileNotFoundError, ValueError) as exc:
        print(f"BLOCKED: {exc}")
        return 2

    print(f"status={report['status']} symbols={len(report['symbols'])} output={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
