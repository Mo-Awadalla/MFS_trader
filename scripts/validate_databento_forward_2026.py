"""Validate the acquired 2026 forward-test files without calculating strategy P&L."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

VENDOR_DIR = Path(__file__).resolve().parents[1] / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

import databento as db  # noqa: E402, I001
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "external_artifacts" / "databento_forward_2026"
BARS = (
    DATA_ROOT
    / "ARCX.PILLAR"
    / "bars"
    / "spy_upro_spxu_ohlcv_1m_2026-01-02_2026-07-25.dbn.zst"
)
BBO = (
    DATA_ROOT
    / "ARCX.PILLAR"
    / "bbo"
    / "upro_spxu_bbo_1m_2026-01-02_2026-07-25.dbn.zst"
)
CONDITIONS = DATA_ROOT / "ARCX.PILLAR" / "dataset_condition_2026.json"
OUTPUT = DATA_ROOT / "validation_report.json"


def load(path: Path) -> pd.DataFrame:
    frame = db.DBNStore.from_file(path).to_df()
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    return frame.tz_convert("America/New_York").sort_index()


def symbol_summary(frame: pd.DataFrame, symbol: str) -> dict[str, Any]:
    subset = frame[frame.symbol == symbol]
    rth = subset.between_time("09:30", "15:59", inclusive="both")
    counts = rth.groupby(rth.index.normalize()).size()
    return {
        "rows_all_hours": int(len(subset)),
        "rows_rth": int(len(rth)),
        "first_timestamp": str(subset.index.min()),
        "last_timestamp": str(subset.index.max()),
        "rth_session_dates": int(len(counts)),
        "median_rth_rows_per_date": float(counts.median()),
    }


def main() -> int:
    bars = load(BARS)
    bbo = load(BBO)
    condition_payload = json.loads(CONDITIONS.read_text(encoding="utf-8"))
    degraded = [
        row["date"]
        for row in condition_payload["conditions"]
        if row["condition"] == "degraded"
    ]
    bar_summary = {
        symbol: symbol_summary(bars, symbol)
        for symbol in ["SPY", "UPRO", "SPXU"]
    }
    bbo_summary = {
        symbol: symbol_summary(bbo, symbol)
        for symbol in ["UPRO", "SPXU"]
    }
    bid = bbo.bid_px_00.astype(float)
    ask = bbo.ask_px_00.astype(float)
    valid = (bid > 0) & (ask > 0) & (ask >= bid)
    midpoint = (bid[valid] + ask[valid]) / 2.0
    spread_bps = (ask[valid] - bid[valid]) / midpoint * 10000.0
    exact_clock_coverage: dict[str, dict[str, int]] = {}
    for symbol in ["UPRO", "SPXU"]:
        subset = bbo[bbo.symbol == symbol]
        exact_clock_coverage[symbol] = {
            clock: int(
                len(subset.between_time(clock, clock, inclusive="both"))
            )
            for clock in ["11:01", "15:30"]
        }
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "valid",
        "purpose": "Pre-outcome validation only; no strategy signal or P&L calculated",
        "bars": {
            "path": BARS.relative_to(ROOT).as_posix(),
            "bytes": BARS.stat().st_size,
            "rows": int(len(bars)),
            "symbols": sorted(bars.symbol.unique().tolist()),
            "by_symbol": bar_summary,
            "nonpositive_price_rows": int(
                (
                    (bars.open <= 0)
                    | (bars.high <= 0)
                    | (bars.low <= 0)
                    | (bars.close <= 0)
                ).sum()
            ),
            "negative_volume_rows": int((bars.volume < 0).sum()),
        },
        "bbo": {
            "path": BBO.relative_to(ROOT).as_posix(),
            "bytes": BBO.stat().st_size,
            "rows": int(len(bbo)),
            "symbols": sorted(bbo.symbol.unique().tolist()),
            "by_symbol": bbo_summary,
            "invalid_or_crossed_rows": int((~valid).sum()),
            "valid_spread_bps": {
                "median": float(np.median(spread_bps)),
                "p95": float(np.quantile(spread_bps, 0.95)),
                "p99": float(np.quantile(spread_bps, 0.99)),
            },
            "exact_clock_observations": exact_clock_coverage,
        },
        "dataset_condition": {
            "path": CONDITIONS.relative_to(ROOT).as_posix(),
            "condition_rows": len(condition_payload["conditions"]),
            "degraded_dates": degraded,
        },
    }
    expected_bar_symbols = {"SPY", "UPRO", "SPXU"}
    expected_bbo_symbols = {"UPRO", "SPXU"}
    failures = []
    if set(payload["bars"]["symbols"]) != expected_bar_symbols:
        failures.append("unexpected_bar_symbols")
    if set(payload["bbo"]["symbols"]) != expected_bbo_symbols:
        failures.append("unexpected_bbo_symbols")
    if payload["bars"]["nonpositive_price_rows"]:
        failures.append("nonpositive_bar_prices")
    if payload["bars"]["negative_volume_rows"]:
        failures.append("negative_bar_volume")
    if payload["bbo"]["invalid_or_crossed_rows"] > len(bbo) * 0.01:
        failures.append("too_many_invalid_quotes")
    if failures:
        payload["status"] = "invalid"
        payload["failures"] = failures
    OUTPUT.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
