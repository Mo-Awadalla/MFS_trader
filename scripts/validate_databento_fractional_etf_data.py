"""Validate the Databento SPY/SH bar files and overlapping feed agreement."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parents[1] / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

import databento as db  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

DEFAULT_ROOT = Path("external_artifacts/databento_fractional_etf")
ARCA_PATH = (
    DEFAULT_ROOT
    / "ARCX.PILLAR"
    / "bars"
    / "spy_sh_ohlcv_1m_2021-01-01_2026-01-01.dbn.zst"
)
MINI_PATH = (
    DEFAULT_ROOT
    / "EQUS.MINI"
    / "bars"
    / "spy_sh_ohlcv_1m_2023-03-28_2026-01-01.dbn.zst"
)


def load(path: Path) -> pd.DataFrame:
    frame = db.DBNStore.from_file(path).to_df()
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    frame = frame.tz_convert("America/New_York")
    return frame.sort_index()


def file_summary(path: Path, frame: pd.DataFrame) -> dict:
    rth = frame.between_time("09:30", "15:59")
    by_symbol = {}
    for symbol, group in frame.groupby("symbol"):
        symbol_rth = rth[rth.symbol == symbol]
        counts = symbol_rth.groupby(symbol_rth.index.date).size()
        by_symbol[str(symbol)] = {
            "rows_all_hours": int(len(group)),
            "rows_rth": int(len(symbol_rth)),
            "first_timestamp": group.index.min().isoformat(),
            "last_timestamp": group.index.max().isoformat(),
            "rth_session_dates": int(counts.index.nunique()),
            "median_rth_rows_per_date": (
                float(counts.median()) if len(counts) else None
            ),
            "nonpositive_price_rows": int(
                (
                    (group.open <= 0)
                    | (group.high <= 0)
                    | (group.low <= 0)
                    | (group.close <= 0)
                ).sum()
            ),
            "negative_volume_rows": int((group.volume < 0).sum()),
        }
    return {
        "path": path.as_posix(),
        "bytes": path.stat().st_size,
        "rows": int(len(frame)),
        "symbols": sorted(str(value) for value in frame.symbol.unique()),
        "instrument_ids": sorted(
            int(value) for value in frame.instrument_id.unique()
        ),
        "by_symbol": by_symbol,
    }


def overlap_summary(arca: pd.DataFrame, mini: pd.DataFrame) -> dict:
    fields = ["open", "high", "low", "close"]
    merged = (
        arca.reset_index()
        .merge(
            mini.reset_index(),
            on=["ts_event", "symbol"],
            suffixes=("_arca", "_mini"),
            how="inner",
        )
        .set_index("ts_event")
    )
    rth = merged.between_time("09:30", "15:59")
    by_symbol = {}
    for symbol, group in rth.groupby("symbol"):
        close_diff_bps = (
            (group.close_arca / group.close_mini - 1.0).abs() * 10000.0
        )
        exact_ohlc = np.ones(len(group), dtype=bool)
        for field in fields:
            exact_ohlc &= np.isclose(
                group[f"{field}_arca"],
                group[f"{field}_mini"],
                rtol=0.0,
                atol=1e-12,
            )
        by_symbol[str(symbol)] = {
            "overlapping_rth_minutes": int(len(group)),
            "exact_ohlc_fraction": round(float(exact_ohlc.mean()), 6),
            "median_absolute_close_difference_bps": round(
                float(close_diff_bps.median()), 6
            ),
            "p99_absolute_close_difference_bps": round(
                float(close_diff_bps.quantile(0.99)), 6
            ),
            "arca_volume_divided_by_consolidated_median": round(
                float(
                    (
                        group.volume_arca
                        / group.volume_mini.replace(0, np.nan)
                    ).median()
                ),
                6,
            ),
        }
    return {
        "overlapping_rows_all_hours": int(len(merged)),
        "overlapping_rows_rth": int(len(rth)),
        "by_symbol": by_symbol,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arca", type=Path, default=ARCA_PATH)
    parser.add_argument("--mini", type=Path, default=MINI_PATH)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_ROOT / "validation_report.json",
    )
    args = parser.parse_args()
    for path in [args.arca, args.mini]:
        if not path.exists() or path.stat().st_size == 0:
            raise FileNotFoundError(path)

    arca = load(args.arca)
    mini = load(args.mini)
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "valid",
        "expected_symbols": ["SH", "SPY"],
        "files": {
            "ARCX.PILLAR": file_summary(args.arca, arca),
            "EQUS.MINI": file_summary(args.mini, mini),
        },
        "overlap": overlap_summary(arca, mini),
        "known_limitations": [
            "ARCX.PILLAR contains only NYSE Arca executions and is not a consolidated tape.",
            "EQUS.MINI begins on 2023-03-28 and cannot validate 2021 through early 2023.",
            "One-minute bars do not provide executable fractional-share bid and ask fills.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
