"""Returns-blind feasibility audit for VX forward-stress persistence v47."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd

from research_scout import audit_spy_official_macro_release_v45 as macro_audit
from research_scout import audit_spy_vx_curve_confirmation_failure_v46 as v46
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay_audit
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "research_scout" / "spy_vx_forward_stress_persistence_prereg_v47.json"
OUTPUT = ROOT / "research_scout" / "spy_vx_forward_stress_persistence_returns_blind_audit_v47.json"
START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")
EQUS_START = pd.Timestamp("2023-03-28")


def curve_action(state: dict) -> int:
    change = float(state["curve_change"])
    return int(change > 0) - int(change < 0)


def main() -> None:
    if not PREREG.exists():
        raise FileNotFoundError("V47 preregistration is required before audit")
    contracts = v46.load_contracts()
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    next_spy = v46.next_session_map(spy)
    states = v46.build_states(spy, contracts, arca_excluded)
    early_states = v46.build_states(spy, contracts, arca_excluded, early_roll=True)
    eligible = [day for day in sorted(spy) if START <= day <= END and day not in arca_excluded]

    rows = []
    for signal_day in eligible:
        state = states.get(signal_day)
        if state is None:
            continue
        direction = curve_action(state)
        if direction == 0:
            continue
        trade_day = next_spy.get(signal_day)
        if trade_day is None or not START <= trade_day <= END:
            continue
        symbol = "UPRO" if direction > 0 else "SPXU"
        available = (
            trade_day not in arca_excluded
            and v46.execution_available(arca, trade_day, symbol)
        )
        rows.append(
            {
                "signal_day": signal_day,
                "trade_day": trade_day,
                "symbol": symbol,
                "direction": direction,
                "execution_available": available,
            }
        )
    frame = pd.DataFrame(rows)
    executable = frame[frame.execution_available].copy() if len(frame) else frame
    coverage = sum(day in states for day in eligible) / max(len(eligible), 1)
    execution_coverage = len(executable) / max(len(frame), 1)
    weeks = (END - START).days / 7.0
    cadence = len(executable) / weeks
    years = {
        str(year): int((executable.trade_day.dt.year == year).sum()) if len(executable) else 0
        for year in [2021, 2022, 2023]
    }
    directions = Counter(executable.symbol) if len(executable) else Counter()
    minority = min(directions.get("UPRO", 0), directions.get("SPXU", 0)) / max(len(executable), 1)

    roll_comparisons = roll_agreements = 0
    for day in eligible:
        left = states.get(day)
        right = early_states.get(day)
        if left is None or right is None:
            continue
        roll_comparisons += 1
        roll_agreements += int(curve_action(left) == curve_action(right))
    roll_agreement = roll_agreements / max(roll_comparisons, 1)

    independent_candidates = independent_executable = 0
    for signal_day in eligible:
        if signal_day < EQUS_START:
            continue
        state = states.get(signal_day)
        if state is None:
            continue
        direction = curve_action(state)
        if direction == 0:
            continue
        trade_day = next_spy.get(signal_day)
        if trade_day is None or trade_day > END:
            continue
        independent_candidates += 1
        symbol = "UPRO" if direction > 0 else "SPXU"
        if trade_day not in equs_excluded and v46.execution_available(equs, trade_day, symbol):
            independent_executable += 1
    independent_coverage = independent_executable / max(independent_candidates, 1)
    causality = all(row["signal_day"] < row["trade_day"] for row in rows)

    gates = {
        "curve_state_coverage_at_least_98_percent": coverage >= 0.98,
        "at_least_two_executable_trades_per_calendar_week": cadence >= 2.0,
        "at_least_200_executable_trades_each_development_year": all(
            count >= 200 for count in years.values()
        ),
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "primary_execution_coverage_at_least_95_percent": execution_coverage >= 0.95,
        "independent_execution_coverage_at_least_95_percent": independent_coverage >= 0.95,
        "early_roll_action_agreement_at_least_80_percent": roll_agreement >= 0.80,
        "strict_signal_before_trade_causality": causality,
    }
    payload = {
        "status": "returns_blind_no_post_entry_return_or_pnl_computed",
        "eligible_development_sessions": len(eligible),
        "complete_curve_states": sum(day in states for day in eligible),
        "curve_state_coverage": coverage,
        "candidate_signals": len(frame),
        "executable_trades": len(executable),
        "executable_trades_per_calendar_week": cadence,
        "primary_execution_coverage": execution_coverage,
        "year_counts": years,
        "direction_counts": dict(directions),
        "minority_direction_fraction": minority,
        "roll_policy_comparisons": roll_comparisons,
        "early_roll_action_agreement_including_cash": roll_agreement,
        "independent_candidate_signals": independent_candidates,
        "independent_executable_signals": independent_executable,
        "independent_execution_coverage": independent_coverage,
        "predeclared_feasibility_gates": gates,
        "feasibility_passed": all(gates.values()),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
