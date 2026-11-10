"""Returns-blind feasibility audit for VX fresh-position risk transfer v55."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_spy_vx_curve_confirmation_failure_v46 as v46
from research_scout import test_spy_vx_forward_stress_persistence_v47 as v47_test
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "research_scout" / "spy_vx_fresh_position_risk_transfer_prereg_v55.json"
OUTPUT = (
    ROOT
    / "research_scout"
    / "spy_vx_fresh_position_risk_transfer_returns_blind_audit_v55.json"
)
START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")
EQUS_START = pd.Timestamp("2023-03-28")


def load_contract_rows() -> dict[pd.Timestamp, dict[pd.Timestamp, dict[str, float]]]:
    manifest = json.loads(v46.MANIFEST.read_text(encoding="utf-8"))
    by_date: dict[pd.Timestamp, dict[pd.Timestamp, dict[str, float]]] = defaultdict(dict)
    for item in manifest["files"]:
        expiration = pd.Timestamp(item["expiration"])
        with (ROOT / item["path"]).open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                settle = float(row["Settle"])
                open_interest = float(row["Open Interest"])
                if settle <= 0 or open_interest < 0:
                    continue
                day = pd.Timestamp(row["Trade Date"]).normalize()
                by_date[day][expiration] = {
                    "settle": settle,
                    "open_interest_start": open_interest,
                }
    return dict(by_date)


def front_contract(
    contracts: dict[pd.Timestamp, dict[pd.Timestamp, dict[str, float]]],
    day: pd.Timestamp,
) -> tuple[pd.Timestamp, dict[str, float]] | None:
    available = sorted(
        (expiration, values)
        for expiration, values in contracts.get(day, {}).items()
        if expiration > day and values["settle"] > 0
    )
    return available[0] if available else None


def build_states(
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    contracts: dict[pd.Timestamp, dict[pd.Timestamp, dict[str, float]]],
    excluded: set[pd.Timestamp],
) -> tuple[dict[pd.Timestamp, dict[str, Any]], dict[str, int]]:
    ordered = sorted(day for day in spy_sessions if day not in excluded)
    adjacent = list(zip(ordered, ordered[1:], strict=False))
    next_session = dict(adjacent)
    previous_session = {right: left for left, right in adjacent}
    states: dict[pd.Timestamp, dict[str, Any]] = {}
    reasons: Counter[str] = Counter()
    for signal_day in ordered:
        prior_day = previous_session.get(signal_day)
        trade_day = next_session.get(signal_day)
        if prior_day is None or trade_day is None:
            reasons["missing_adjacent_spy_session"] += 1
            continue
        prior_front = front_contract(contracts, prior_day)
        current_front = front_contract(contracts, signal_day)
        if prior_front is None or current_front is None:
            reasons["missing_front_contract"] += 1
            continue
        expiration, current = current_front
        if prior_front[0] != expiration:
            reasons["front_contract_roll_transition"] += 1
            continue
        trade_day_contract = contracts.get(trade_day, {}).get(expiration)
        if trade_day_contract is None:
            reasons["missing_trade_day_start_open_interest"] += 1
            continue
        prior = prior_front[1]
        settlement_change = current["settle"] / prior["settle"] - 1.0
        open_interest_change = (
            trade_day_contract["open_interest_start"]
            - current["open_interest_start"]
        )
        direction = 0
        if open_interest_change > 0 and settlement_change > 0:
            direction = -1
        elif open_interest_change > 0 and settlement_change < 0:
            direction = 1
        states[signal_day] = {
            "signal_day": signal_day,
            "trade_day": trade_day,
            "expiration": expiration,
            "settlement_change": settlement_change,
            "open_interest_change": open_interest_change,
            "direction": direction,
        }
    return states, dict(reasons)


def main() -> None:
    if not PREREG.exists():
        raise FileNotFoundError("V55 preregistration is required before audit")
    v47_test._repair_vendor_version_metadata()
    contracts = load_contract_rows()
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    states, exclusions = build_states(spy, contracts, arca_excluded)
    eligible = [
        day for day in sorted(spy) if START <= day <= END and day not in arca_excluded
    ]
    scoped = [state for day, state in states.items() if START <= day <= END]
    candidates = [state for state in scoped if state["direction"] != 0]
    executable = []
    for state in candidates:
        symbol = "UPRO" if state["direction"] > 0 else "SPXU"
        if (
            state["trade_day"] not in arca_excluded
            and v46.execution_available(arca, state["trade_day"], symbol)
        ):
            executable.append(state)

    weeks = (END - START).days / 7.0
    coverage = len(scoped) / max(len(eligible) - 2, 1)
    cadence = len(executable) / weeks
    year_counts = {
        str(year): sum(state["trade_day"].year == year for state in executable)
        for year in [2021, 2022, 2023]
    }
    direction_counts = Counter(
        "UPRO" if state["direction"] > 0 else "SPXU" for state in executable
    )
    minority = min(
        direction_counts.get("UPRO", 0), direction_counts.get("SPXU", 0)
    ) / max(len(executable), 1)
    primary_coverage = len(executable) / max(len(candidates), 1)

    independent_candidates = [
        state
        for state in candidates
        if EQUS_START <= state["trade_day"] <= END
    ]
    independent_executable = []
    for state in independent_candidates:
        symbol = "UPRO" if state["direction"] > 0 else "SPXU"
        if (
            state["trade_day"] not in equs_excluded
            and v46.execution_available(equs, state["trade_day"], symbol)
        ):
            independent_executable.append(state)
    independent_coverage = len(independent_executable) / max(
        len(independent_candidates), 1
    )
    causality = all(
        state["signal_day"] < state["trade_day"] for state in candidates
    )
    gates = {
        "state_coverage_at_least_95_percent": coverage >= 0.95,
        "at_least_two_executable_trades_per_calendar_week": cadence >= 2.0,
        "at_least_100_executable_trades_each_development_year": all(
            count >= 100 for count in year_counts.values()
        ),
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "primary_execution_coverage_at_least_95_percent": primary_coverage >= 0.95,
        "independent_execution_coverage_at_least_95_percent": (
            independent_coverage >= 0.95
        ),
        "strict_signal_before_trade_causality": causality,
    }
    payload = {
        "status": "returns_blind_no_post_entry_return_or_pnl_computed",
        "eligible_development_signal_sessions": len(eligible),
        "complete_same_contract_states": len(scoped),
        "state_coverage": coverage,
        "state_exclusion_reasons_full_history": exclusions,
        "candidate_signals": len(candidates),
        "executable_trades": len(executable),
        "executable_trades_per_calendar_week": cadence,
        "primary_execution_coverage": primary_coverage,
        "year_counts": year_counts,
        "direction_counts": dict(direction_counts),
        "minority_direction_fraction": minority,
        "independent_candidate_signals": len(independent_candidates),
        "independent_executable_signals": len(independent_executable),
        "independent_execution_coverage": independent_coverage,
        "predeclared_feasibility_gates": gates,
        "feasibility_passed": all(gates.values()),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
