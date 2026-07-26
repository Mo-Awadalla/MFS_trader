"""Test preregistered UPRO/SPXU activity-mask topology hypotheses."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_inventory_state as inventory
from research_scout import test_upro_spxu_pair_geometry as geo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "research_scout" / "upro_spxu_activity_topology_results_v5.json"
HYPOTHESES = [
    "synchronization_transition_charge",
    "silence_debt_release",
    "activity_lead_lag_braid",
    "longest_run_recency",
    "silence_entropy_order",
    "binary_event_clock_braid",
    "onset_persistence_asymmetry",
]


def activity_arrays(
    day: pd.Timestamp,
    pair_bars: dict[str, pd.DataFrame],
) -> dict[str, dict[str, np.ndarray]] | None:
    if not {"UPRO", "SPXU"}.issubset(pair_bars):
        return None
    result: dict[str, dict[str, np.ndarray]] = {}
    for symbol in ["UPRO", "SPXU"]:
        window = base.between(pair_bars[symbol], "09:30", "10:59")
        if window.empty:
            return None
        origin = base.clock_timestamp(day, pd.Timestamp("09:30").time(), window.index.tz)
        offsets = ((window.index - origin).total_seconds() / 60.0).astype(int)
        valid = (offsets >= 0) & (offsets <= 89)
        offsets = offsets[valid]
        volume_values = window.volume.astype(float).to_numpy()[valid]
        active = np.zeros(90, dtype=bool)
        volume = np.zeros(90, dtype=float)
        active[offsets] = True
        volume[offsets] += volume_values
        if float(volume.sum()) <= 0:
            return None
        result[symbol] = {"active": active, "volume": volume}
    return result


def runs(mask: np.ndarray, value: bool) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    start: int | None = None
    for idx, item in enumerate(mask):
        if bool(item) == value and start is None:
            start = idx
        if bool(item) != value and start is not None:
            found.append((start, idx - 1))
            start = None
    if start is not None:
        found.append((start, len(mask) - 1))
    return found


def transition_charge(data: dict[str, dict[str, np.ndarray]]) -> float:
    u_active = data["UPRO"]["active"]
    s_active = data["SPXU"]["active"]
    joint = u_active & s_active
    onsets = joint & ~np.r_[joint[0], joint[:-1]]
    onsets[0] = False
    if not onsets.any():
        return math.nan
    normalized: dict[str, np.ndarray] = {}
    for symbol in ["UPRO", "SPXU"]:
        volume = data[symbol]["volume"]
        median = float(np.median(volume[volume > 0]))
        if median <= 0:
            return math.nan
        normalized[symbol] = volume / median
    return float((normalized["UPRO"][onsets] - normalized["SPXU"][onsets]).sum())


def release_energy(mask: np.ndarray, volume: np.ndarray) -> float:
    median = float(np.median(volume[volume > 0]))
    debt = 0
    energy = 0.0
    for idx in range(90):
        if not mask[idx]:
            debt += 1
        elif debt:
            energy += debt * volume[idx] / median
            debt = 0
    return energy


def silence_debt(data: dict[str, dict[str, np.ndarray]]) -> float:
    values = {
        symbol: release_energy(data[symbol]["active"], data[symbol]["volume"])
        for symbol in ["UPRO", "SPXU"]
    }
    return values["UPRO"] - values["SPXU"]


def lead_lag_braid(data: dict[str, dict[str, np.ndarray]]) -> float:
    u = data["UPRO"]["active"]
    s = data["SPXU"]["active"]
    score = 0
    for lag in range(1, 6):
        score += int((u[:-lag] & s[lag:]).sum())
        score -= int((s[:-lag] & u[lag:]).sum())
    return float(score)


def longest_run_state(mask: np.ndarray) -> float:
    active_runs = runs(mask, True)
    if not active_runs:
        return math.nan
    start, end = max(active_runs, key=lambda item: (item[1] - item[0] + 1, item[1]))
    length = end - start + 1
    return length / int(mask.sum()) * end / 89.0


def longest_run_recency(data: dict[str, dict[str, np.ndarray]]) -> float:
    return longest_run_state(data["UPRO"]["active"]) - longest_run_state(
        data["SPXU"]["active"]
    )


def normalized_silence_entropy(mask: np.ndarray) -> float:
    lengths = np.array(
        [end - start + 1 for start, end in runs(mask, False)],
        dtype=float,
    )
    if len(lengths) <= 1:
        return 0.0
    probabilities = lengths / lengths.sum()
    return float(-(probabilities * np.log(probabilities)).sum() / np.log(len(lengths)))


def silence_entropy(data: dict[str, dict[str, np.ndarray]]) -> float:
    u = normalized_silence_entropy(data["UPRO"]["active"])
    s = normalized_silence_entropy(data["SPXU"]["active"])
    return s - u


def event_centroid(mask: np.ndarray) -> float:
    return float(np.dot(np.arange(90, dtype=float), mask.astype(float)) / mask.sum())


def binary_clock(data: dict[str, dict[str, np.ndarray]]) -> float:
    return event_centroid(data["UPRO"]["active"]) - event_centroid(
        data["SPXU"]["active"]
    )


def onset_persistence(mask: np.ndarray) -> float:
    values = [
        (end - start + 1) * (start + 1)
        for start, end in runs(mask, True)
        if start > 0
    ]
    return float(np.mean(values)) if values else math.nan


def onset_asymmetry(data: dict[str, dict[str, np.ndarray]]) -> float:
    return onset_persistence(data["UPRO"]["active"]) - onset_persistence(
        data["SPXU"]["active"]
    )


SCORERS = {
    "synchronization_transition_charge": transition_charge,
    "silence_debt_release": silence_debt,
    "activity_lead_lag_braid": lead_lag_braid,
    "longest_run_recency": longest_run_recency,
    "silence_entropy_order": silence_entropy,
    "binary_event_clock_braid": binary_clock,
    "onset_persistence_asymmetry": onset_asymmetry,
}


def make_signal(
    hypothesis: str,
    day: pd.Timestamp,
    pair_bars: dict[str, pd.DataFrame],
) -> dict[str, Any] | None:
    data = activity_arrays(day, pair_bars)
    if data is None:
        return None
    score = SCORERS[hypothesis](data)
    if not math.isfinite(score):
        return None
    signal_direction = int(score > 0) - int(score < 0)
    if signal_direction == 0:
        return None
    return {
        "hypothesis": hypothesis,
        "date": day,
        "direction": signal_direction,
        "score": score,
    }


def run_period(
    hypothesis: str,
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
        signal = make_signal(hypothesis, day, pair_bars)
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


def stress_table(
    hypothesis: str,
    trades: pd.DataFrame,
    sample: str,
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    pair_sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    feed_sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    years: range,
) -> dict[str, Any]:
    delayed_one = run_period(
        hypothesis,
        spy_sessions,
        pair_sessions,
        feed_sessions,
        excluded,
        years,
        1,
    )
    delayed_five = run_period(
        hypothesis,
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
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    spy_sessions, feeds = base.load_inputs()
    pair_sessions = geo.load_pair_bars()
    excluded = base.degraded_dates()
    development_hurdle = inventory.spy_price_hurdle(
        spy_sessions,
        excluded,
        range(2021, 2024),
    )
    results: dict[str, Any] = {
        "specification": "research_scout/upro_spxu_activity_topology_prereg_v5.json",
        "status": "development_screen_complete",
        "development_spy_price_hurdle": development_hurdle,
        "candidates": {},
    }
    for hypothesis in HYPOTHESES:
        development = run_period(
            hypothesis,
            spy_sessions,
            pair_sessions,
            feeds["arca"],
            excluded,
            range(2021, 2024),
        )
        development_stress = stress_table(
            hypothesis,
            development,
            "development",
            spy_sessions,
            pair_sessions,
            feeds["arca"],
            excluded,
            range(2021, 2024),
        )
        passed, failures = inventory.development_gate(
            development_stress,
            development_hurdle,
        )
        candidate: dict[str, Any] = {
            "development": development_stress,
            "gate_passed": passed,
            "gate_failures": failures,
            "secondary_holdout": "not_evaluated",
        }
        if passed:
            holdout = run_period(
                hypothesis,
                spy_sessions,
                pair_sessions,
                feeds["arca"],
                excluded,
                range(2024, 2026),
            )
            holdout_stress = stress_table(
                hypothesis,
                holdout,
                "holdout",
                spy_sessions,
                pair_sessions,
                feeds["arca"],
                excluded,
                range(2024, 2026),
            )
            consolidated = run_period(
                hypothesis,
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
            full = run_period(
                hypothesis,
                spy_sessions,
                pair_sessions,
                feeds["arca"],
                excluded,
                range(2021, 2026),
            )
            holdout_stress["five_year_comparison"] = {
                "strategy_cash_account": inventory.full_cash_path(full),
                "spy_price_only": inventory.spy_price_hurdle(
                    spy_sessions,
                    excluded,
                    range(2021, 2026),
                ),
            }
            candidate["secondary_holdout"] = holdout_stress
        results["candidates"][hypothesis] = candidate
    args.output.write_text(
        json.dumps(results, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    compact = {
        name: {
            "trades_per_week": row["development"]["observed_bbo"].get(
                "trades_per_week"
            ),
            "ending_cash_usd": row["development"]["observed_bbo"]
            .get("cash_account", {})
            .get("ending_equity_usd"),
            "net_pnl_usd": row["development"]["observed_bbo"].get("net_pnl_usd"),
            "profit_factor": row["development"]["observed_bbo"].get(
                "profit_factor"
            ),
            "gate_passed": row["gate_passed"],
            "gate_failures": row["gate_failures"],
        }
        for name, row in results["candidates"].items()
    }
    print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
