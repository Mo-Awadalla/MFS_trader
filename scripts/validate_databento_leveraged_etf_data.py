"""Validate downloaded Databento UPRO/SPXU bars and one-minute BBO files."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parents[1] / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

import databento as db  # noqa: E402, I001
import pandas as pd  # noqa: E402


DEFAULT_ROOT = Path("external_artifacts/databento_leveraged_etf")
FILES = {
    "ARCX.PILLAR": {
        "ohlcv-1m": (
            DEFAULT_ROOT
            / "ARCX.PILLAR"
            / "bars"
            / "upro_spxu_ohlcv_1m_2021-01-01_2026-01-01.dbn.zst"
        ),
        "bbo-1m": (
            DEFAULT_ROOT
            / "ARCX.PILLAR"
            / "bbo"
            / "upro_spxu_bbo_1m_2021-01-01_2026-01-01.dbn.zst"
        ),
    },
    "EQUS.MINI": {
        "ohlcv-1m": (
            DEFAULT_ROOT
            / "EQUS.MINI"
            / "bars"
            / "upro_spxu_ohlcv_1m_2023-03-28_2026-01-01.dbn.zst"
        ),
        "bbo-1m": (
            DEFAULT_ROOT
            / "EQUS.MINI"
            / "bbo"
            / "upro_spxu_bbo_1m_2023-03-28_2026-01-01.dbn.zst"
        ),
    },
}


def load(path: Path) -> pd.DataFrame:
    frame = db.DBNStore.from_file(path).to_df()
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    return frame.tz_convert("America/New_York").sort_index()


def common(frame: pd.DataFrame, path: Path) -> dict[str, object]:
    rth = frame.between_time("09:30", "15:59")
    by_symbol: dict[str, object] = {}
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


def bar_summary(frame: pd.DataFrame, path: Path) -> dict[str, object]:
    output = common(frame, path)
    output["nonpositive_price_rows"] = int(
        (
            (frame.open <= 0)
            | (frame.high <= 0)
            | (frame.low <= 0)
            | (frame.close <= 0)
        ).sum()
    )
    output["negative_volume_rows"] = int((frame.volume < 0).sum())
    return output


def bbo_summary(frame: pd.DataFrame, path: Path) -> dict[str, object]:
    output = common(frame, path)
    required = {"bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} missing BBO columns: {sorted(missing)}")
    valid = frame[(frame.bid_px_00 > 0) & (frame.ask_px_00 > 0)].copy()
    valid_rth = valid.between_time("09:30", "15:59")
    midpoint = (valid_rth.bid_px_00 + valid_rth.ask_px_00) / 2.0
    spread_bps = (valid_rth.ask_px_00 - valid_rth.bid_px_00) / midpoint * 10000.0
    by_symbol_quote: dict[str, object] = {}
    for symbol, group in valid_rth.groupby("symbol"):
        mid = (group.bid_px_00 + group.ask_px_00) / 2.0
        spread = (group.ask_px_00 - group.bid_px_00) / mid * 10000.0
        by_symbol_quote[str(symbol)] = {
            "valid_rth_quotes": int(len(group)),
            "median_spread_bps": round(float(spread.median()), 6),
            "p95_spread_bps": round(float(spread.quantile(0.95)), 6),
            "p99_spread_bps": round(float(spread.quantile(0.99)), 6),
            "median_bid_size": float(group.bid_sz_00.median()),
            "median_ask_size": float(group.ask_sz_00.median()),
        }
    output.update(
        {
            "invalid_or_empty_quote_rows": int(len(frame) - len(valid)),
            "crossed_quote_rows": int((valid.ask_px_00 < valid.bid_px_00).sum()),
            "nonpositive_size_rows": int(
                ((valid.bid_sz_00 <= 0) | (valid.ask_sz_00 <= 0)).sum()
            ),
            "valid_rth_spread_bps": {
                "median": round(float(spread_bps.median()), 6),
                "p95": round(float(spread_bps.quantile(0.95)), 6),
                "p99": round(float(spread_bps.quantile(0.99)), 6),
            },
            "by_symbol_quote": by_symbol_quote,
        }
    )
    return output


def overlap_bars(arca: pd.DataFrame, mini: pd.DataFrame) -> dict[str, object]:
    joined = (
        arca.reset_index()
        .merge(
            mini.reset_index(),
            on=["ts_event", "symbol"],
            suffixes=("_arca", "_mini"),
            how="inner",
        )
        .set_index("ts_event")
        .between_time("09:30", "15:59")
    )
    by_symbol: dict[str, object] = {}
    for symbol, group in joined.groupby("symbol"):
        diff = (group.close_arca / group.close_mini - 1.0).abs() * 10000.0
        by_symbol[str(symbol)] = {
            "overlapping_rth_minutes": int(len(group)),
            "median_absolute_close_difference_bps": round(
                float(diff.median()), 6
            ),
            "p99_absolute_close_difference_bps": round(
                float(diff.quantile(0.99)), 6
            ),
        }
    return {"rows": int(len(joined)), "by_symbol": by_symbol}


def overlap_bbo(arca: pd.DataFrame, mini: pd.DataFrame) -> dict[str, object]:
    columns = ["bid_px_00", "ask_px_00", "symbol"]
    arca_rows = arca[columns].reset_index()
    mini_rows = mini[columns].reset_index()
    arca_rows = arca_rows.rename(columns={arca_rows.columns[0]: "timestamp"})
    mini_rows = mini_rows.rename(columns={mini_rows.columns[0]: "timestamp"})
    joined = (
        arca_rows
        .merge(
            mini_rows,
            on=["timestamp", "symbol"],
            suffixes=("_arca", "_mini"),
            how="inner",
        )
        .set_index("timestamp")
        .between_time("09:30", "15:59")
    )
    joined = joined[
        (joined.bid_px_00_arca > 0)
        & (joined.ask_px_00_arca > 0)
        & (joined.bid_px_00_mini > 0)
        & (joined.ask_px_00_mini > 0)
    ]
    by_symbol: dict[str, object] = {}
    for symbol, group in joined.groupby("symbol"):
        arca_mid = (group.bid_px_00_arca + group.ask_px_00_arca) / 2.0
        mini_mid = (group.bid_px_00_mini + group.ask_px_00_mini) / 2.0
        diff = (arca_mid / mini_mid - 1.0).abs() * 10000.0
        arca_spread = (
            (group.ask_px_00_arca - group.bid_px_00_arca) / arca_mid * 10000.0
        )
        mini_spread = (
            (group.ask_px_00_mini - group.bid_px_00_mini) / mini_mid * 10000.0
        )
        by_symbol[str(symbol)] = {
            "overlapping_rth_minutes": int(len(group)),
            "median_absolute_midpoint_difference_bps": round(
                float(diff.median()), 6
            ),
            "p99_absolute_midpoint_difference_bps": round(
                float(diff.quantile(0.99)), 6
            ),
            "median_arca_spread_bps": round(float(arca_spread.median()), 6),
            "median_consolidated_spread_bps": round(
                float(mini_spread.median()), 6
            ),
        }
    return {"rows": int(len(joined)), "by_symbol": by_symbol}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_ROOT / "validation_report.json",
    )
    args = parser.parse_args()
    for schemas in FILES.values():
        for path in schemas.values():
            if not path.exists() or path.stat().st_size == 0:
                raise FileNotFoundError(path)

    frames: dict[str, dict[str, pd.DataFrame]] = {}
    summaries: dict[str, object] = {}
    for dataset, schemas in FILES.items():
        frames[dataset] = {}
        summaries[dataset] = {}
        for schema, path in schemas.items():
            frame = load(path)
            frames[dataset][schema] = frame
            summaries[dataset][schema] = (
                bar_summary(frame, path)
                if schema == "ohlcv-1m"
                else bbo_summary(frame, path)
            )

    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "valid",
        "expected_symbols": ["SPXU", "UPRO"],
        "files": summaries,
        "overlap": {
            "bars": overlap_bars(
                frames["ARCX.PILLAR"]["ohlcv-1m"],
                frames["EQUS.MINI"]["ohlcv-1m"],
            ),
            "bbo": overlap_bbo(
                frames["ARCX.PILLAR"]["bbo-1m"],
                frames["EQUS.MINI"]["bbo-1m"],
            ),
        },
        "known_limitations": [
            "ARCX.PILLAR is a single exchange rather than the consolidated market.",
            "EQUS.MINI begins on 2023-03-28.",
            "One-minute BBO samples cannot reconstruct sub-minute quote paths.",
            "Leveraged ETFs target daily returns and may not equal exactly three times the underlying intraday return.",
        ],
    }
    args.output.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
