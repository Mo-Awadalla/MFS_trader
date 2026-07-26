"""Test the preregistered sparse-event UPRO/SPXU volume clock."""

from __future__ import annotations

import argparse
import json
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_pair_geometry as geo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "research_scout" / "upro_spxu_sparse_volume_clock_results_v3.json"
HYPOTHESIS = "sparse_event_volume_clock"


def volume_centroid(
    day: pd.Timestamp,
    bars: pd.DataFrame,
) -> float | None:
    window = base.between(bars, "09:30", "10:59")
    if window.empty:
        return None
    volume = window.volume.astype(float)
    total = float(volume.sum())
    if total <= 0:
        return None
    tz = window.index.tz
    origin = base.clock_timestamp(day, time(9, 30), tz)
    minute_offsets = (window.index - origin).total_seconds() / 60.0
    valid = (minute_offsets >= 0) & (minute_offsets <= 89)
    if not valid.all():
        return None
    return float((minute_offsets.to_numpy() * volume.to_numpy()).sum() / total)


def make_signal(
    day: pd.Timestamp,
    pair_bars: dict[str, pd.DataFrame],
) -> dict[str, Any] | None:
    if not {"UPRO", "SPXU"}.issubset(pair_bars):
        return None
    u = volume_centroid(day, pair_bars["UPRO"])
    s = volume_centroid(day, pair_bars["SPXU"])
    if u is None or s is None:
        return None
    score = u - s
    signal_direction = int(score > 0) - int(score < 0)
    if signal_direction == 0:
        return None
    return {
        "hypothesis": HYPOTHESIS,
        "date": day,
        "direction": signal_direction,
        "score": score,
    }


def run_period(
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    pair_sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    feed_sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    years: range,
    additional_delay_minutes: int = 0,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for day in sorted(spy_sessions):
        if day.year not in years or day in excluded:
            continue
        pair_bars = pair_sessions.get(day)
        quotes = feed_sessions.get(day)
        if pair_bars is None or quotes is None:
            continue
        signal = make_signal(day, pair_bars)
        if signal is None:
            continue
        symbol = "UPRO" if signal["direction"] == 1 else "SPXU"
        if symbol not in quotes:
            continue
        trade = geo.simulate(
            signal,
            spy_sessions[day],
            quotes[symbol],
            additional_delay_minutes,
        )
        if trade is not None:
            records.append(trade)
    return pd.DataFrame(records)


def magnitude_quintiles(trades: pd.DataFrame) -> list[dict[str, Any]]:
    if len(trades) < 5:
        return []
    work = trades.copy()
    work["pnl"] = base.trade_pnl(work)
    work["score_magnitude_quintile"] = pd.qcut(
        work.score.abs(),
        5,
        labels=False,
        duplicates="drop",
    )
    records: list[dict[str, Any]] = []
    for quintile, rows in work.groupby("score_magnitude_quintile", observed=True):
        records.append(
            {
                "quintile_zero_is_smallest": int(quintile),
                "trades": int(len(rows)),
                "net_pnl_usd": round(float(rows.pnl.sum()), 4),
                "mean_pnl_usd": round(float(rows.pnl.mean()), 5),
                "median_abs_score_minutes": round(float(rows.score.abs().median()), 4),
            }
        )
    return records


def stress_table(
    trades: pd.DataFrame,
    sample: str,
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    pair_sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    feed_sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    years: range,
) -> dict[str, Any]:
    delayed_one = run_period(
        spy_sessions,
        pair_sessions,
        feed_sessions,
        excluded,
        years,
        1,
    )
    delayed_five = run_period(
        spy_sessions,
        pair_sessions,
        feed_sessions,
        excluded,
        years,
        5,
    )
    return {
        "observed_bbo": geo.summary_or_empty(trades, sample),
        "midpoint_diagnostic": geo.midpoint_or_empty(trades, sample),
        "one_extra_cent_each_fill": geo.summary_or_empty(trades, sample, 0.01),
        "two_extra_cents_each_fill": geo.summary_or_empty(trades, sample, 0.02),
        "one_additional_minute_delay": geo.summary_or_empty(delayed_one, sample),
        "five_additional_minutes_delay": geo.summary_or_empty(delayed_five, sample),
        "score_magnitude_quintiles_non_actionable": magnitude_quintiles(trades),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    spy_sessions, feeds = base.load_inputs()
    pair_sessions = geo.load_pair_bars()
    excluded = base.degraded_dates()
    development = run_period(
        spy_sessions,
        pair_sessions,
        feeds["arca"],
        excluded,
        range(2021, 2024),
    )
    development_stress = stress_table(
        development,
        "development",
        spy_sessions,
        pair_sessions,
        feeds["arca"],
        excluded,
        range(2021, 2024),
    )
    passed, failures = geo.development_gate(development_stress)
    results: dict[str, Any] = {
        "specification": "research_scout/upro_spxu_sparse_volume_clock_prereg_v3.json",
        "status": "development_screen_complete",
        "excluded_degraded_dates": len(excluded),
        "development": development_stress,
        "gate_passed": passed,
        "gate_failures": failures,
        "secondary_holdout": "not_evaluated",
    }
    if passed:
        holdout = run_period(
            spy_sessions,
            pair_sessions,
            feeds["arca"],
            excluded,
            range(2024, 2026),
        )
        holdout_stress = stress_table(
            holdout,
            "holdout",
            spy_sessions,
            pair_sessions,
            feeds["arca"],
            excluded,
            range(2024, 2026),
        )
        consolidated = run_period(
            spy_sessions,
            pair_sessions,
            feeds["consolidated"],
            excluded,
            range(2024, 2026),
        )
        holdout_stress["consolidated_bbo"] = geo.summary_or_empty(
            consolidated,
            "holdout",
        )
        holdout_days = [
            day
            for day in sorted(spy_sessions)
            if day.year in range(2024, 2026) and day not in excluded
        ]
        holdout_stress["five_session_block_bootstrap"] = (
            base.moving_block_bootstrap(holdout, holdout_days)
            if not holdout.empty
            else {"trades": 0}
        )
        results["secondary_holdout"] = holdout_stress
        results["status"] = "secondary_holdout_complete"
    args.output.write_text(
        json.dumps(results, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    compact = {
        "development": {
            "trades_per_week": development_stress["observed_bbo"].get(
                "trades_per_week"
            ),
            "net_pnl_usd": development_stress["observed_bbo"].get("net_pnl_usd"),
            "profit_factor": development_stress["observed_bbo"].get(
                "profit_factor"
            ),
            "gate_passed": passed,
            "gate_failures": failures,
        },
        "secondary_holdout": (
            {
                "net_pnl_usd": results["secondary_holdout"]["observed_bbo"].get(
                    "net_pnl_usd"
                ),
                "profit_factor": results["secondary_holdout"]["observed_bbo"].get(
                    "profit_factor"
                ),
            }
            if passed
            else "not_evaluated"
        ),
    }
    print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
