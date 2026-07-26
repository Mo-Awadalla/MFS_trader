"""Validate the SH BBO files used by the frozen sensor-actuator test."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

from research_scout import test_upro_spxu_creative_hypotheses as base  # noqa: E402

FILES = {
    "ARCX.PILLAR": (
        ROOT
        / "external_artifacts"
        / "databento_sh_bbo"
        / "ARCX.PILLAR"
        / "bbo"
        / "sh_bbo_1m_2021-01-01_2026-07-25.dbn.zst"
    ),
    "EQUS.MINI": (
        ROOT
        / "external_artifacts"
        / "databento_sh_bbo"
        / "EQUS.MINI"
        / "bbo"
        / "sh_bbo_1m_2023-03-28_2026-07-25.dbn.zst"
    ),
}
OUTPUT = ROOT / "external_artifacts" / "databento_sh_bbo" / "validation_report.json"


def inspect(path: Path) -> dict[str, object]:
    frame = base.load_dbn(path)
    if frame.empty:
        raise RuntimeError(f"Empty DBN file: {path}")
    symbols = sorted(str(value) for value in frame.symbol.dropna().unique())
    if symbols != ["SH"]:
        raise RuntimeError(f"Unexpected symbols in {path}: {symbols}")
    bid = frame.bid_px_00.astype(float)
    ask = frame.ask_px_00.astype(float)
    valid = (bid > 0) & (ask > 0) & (ask >= bid)
    sessions = base.split_sessions(frame)
    exact_1101 = 0
    exact_1530 = 0
    executable_1101 = 0
    executable_1530 = 0
    for day, quotes in sessions.items():
        tz = quotes.index.tz
        entry_stamp = base.clock_timestamp(
            day,
            pd.Timestamp("11:01").time(),
            tz,
        )
        exit_stamp = base.clock_timestamp(
            day,
            pd.Timestamp("15:30").time(),
            tz,
        )
        if base.quote_at(
            quotes,
            entry_stamp,
        ) is not None:
            exact_1101 += 1
            executable_1101 += 1
        if base.quote_at(
            quotes,
            exit_stamp,
        ) is not None:
            exact_1530 += 1
        if base.quote_at(quotes, exit_stamp, max_lag_minutes=2) is not None:
            executable_1530 += 1
    midpoint = (bid + ask) / 2.0
    spread_bps = (ask - bid) / midpoint * 10_000.0
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "rows": int(len(frame)),
        "symbols": symbols,
        "first_timestamp": str(frame.index.min()),
        "last_timestamp": str(frame.index.max()),
        "sessions": len(sessions),
        "valid_quote_rows": int(valid.sum()),
        "invalid_or_crossed_quote_rows": int((~valid).sum()),
        "valid_quote_row_fraction": round(float(valid.mean()), 8),
        "sessions_with_exact_11_01_quote": exact_1101,
        "sessions_with_exact_15_30_quote": exact_1530,
        "sessions_with_executable_11_01_quote": executable_1101,
        "sessions_with_executable_15_30_quote": executable_1530,
        "executable_entry_exit_coverage_fraction": round(
            min(executable_1101, executable_1530) / len(sessions),
            6,
        ),
        "spread_bps_valid_rows": {
            "median": round(float(spread_bps[valid].median()), 6),
            "p95": round(float(spread_bps[valid].quantile(0.95)), 6),
            "maximum": round(float(spread_bps[valid].max()), 6),
        },
    }


def main() -> int:
    missing = [str(path) for path in FILES.values() if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing expected files: {missing}")
    feeds = {name: inspect(path) for name, path in FILES.items()}
    primary = feeds["ARCX.PILLAR"]
    audit = feeds["EQUS.MINI"]
    checks = {
        "primary_has_at_least_99pct_valid_quote_rows": (
            primary["valid_quote_row_fraction"] >= 0.99
        ),
        "audit_has_at_least_98pct_valid_quote_rows": (
            audit["valid_quote_row_fraction"] >= 0.98
        ),
        "primary_has_at_least_95pct_executable_entry_exit_coverage": (
            primary["executable_entry_exit_coverage_fraction"] >= 0.95
        ),
        "audit_has_at_least_95pct_executable_entry_exit_coverage": (
            audit["executable_entry_exit_coverage_fraction"] >= 0.95
        ),
    }
    payload = {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "feeds": feeds,
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
