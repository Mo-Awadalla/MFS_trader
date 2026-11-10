"""Returns-blind feasibility audit for IEF/SHY duration impulse v58."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_spy_ief_joint_macro_impulse_v56 as v56
from research_scout import audit_spy_vx_curve_confirmation_failure_v46 as v46
from research_scout import test_spy_vx_forward_stress_persistence_v47 as v47_test
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "research_scout" / "spy_ief_shy_duration_impulse_prereg_v58.json"
OUTPUT = (
    ROOT
    / "research_scout"
    / "spy_ief_shy_duration_impulse_returns_blind_audit_v58.json"
)
YAHOO = ROOT / "data" / "parquet" / "equity" / "yahoo_chart"
ALPACA = ROOT / "data" / "parquet" / "equity" / "alpaca"
START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")
EQUS_START = pd.Timestamp("2023-03-28")


def build_states(
    ief_close: pd.Series, shy_close: pd.Series
) -> dict[pd.Timestamp, dict[str, Any]]:
    panel = pd.concat(
        [ief_close.rename("ief"), shy_close.rename("shy")],
        axis=1,
        join="inner",
    ).dropna()
    returns = panel.pct_change(fill_method=None)
    states: dict[pd.Timestamp, dict[str, Any]] = {}
    for day, row in returns.iloc[1:].iterrows():
        ief_return = float(row.ief)
        shy_return = float(row.shy)
        relative_return = ief_return - shy_return
        direction = int(relative_return > 0) - int(relative_return < 0)
        states[pd.Timestamp(day)] = {
            "ief_return": ief_return,
            "shy_return": shy_return,
            "relative_return": relative_return,
            "ief_direction": int(ief_return > 0) - int(ief_return < 0),
            "shy_direction": int(shy_return > 0) - int(shy_return < 0),
            "direction": direction,
        }
    return states


def main() -> None:
    if not PREREG.exists():
        raise FileNotFoundError("V58 preregistration is required before audit")
    v47_test._repair_vendor_version_metadata()
    primary = build_states(
        v56.load_daily(YAHOO / "IEF_1d.parquet"),
        v56.load_daily(YAHOO / "SHY_1d.parquet"),
    )
    alternate = build_states(
        v56.load_daily(ALPACA / "IEF_1d.parquet"),
        v56.load_daily(ALPACA / "SHY_1d.parquet"),
    )
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    next_session = v46.next_session_map(spy)
    eligible = [
        day for day in sorted(spy) if START <= day <= END and day not in arca_excluded
    ]
    complete = [day for day in eligible if day in primary]
    candidate_rows: list[dict[str, Any]] = []
    for signal_day in complete:
        direction = int(primary[signal_day]["direction"])
        if direction == 0:
            continue
        trade_day = next_session.get(signal_day)
        if trade_day is None or not START <= trade_day <= END:
            continue
        symbol = "UPRO" if direction > 0 else "SPXU"
        candidate_rows.append(
            {
                "signal_day": signal_day,
                "trade_day": trade_day,
                "direction": direction,
                "symbol": symbol,
                "execution_available": (
                    trade_day not in arca_excluded
                    and v46.execution_available(arca, trade_day, symbol)
                ),
            }
        )
    executable = [row for row in candidate_rows if row["execution_available"]]
    weeks = (END - START).days / 7.0
    coverage = len(complete) / max(len(eligible), 1)
    cadence = len(executable) / weeks
    year_counts = {
        str(year): sum(row["trade_day"].year == year for row in executable)
        for year in [2021, 2022, 2023]
    }
    directions = Counter(row["symbol"] for row in executable)
    minority = min(directions.get("UPRO", 0), directions.get("SPXU", 0)) / max(
        len(executable), 1
    )
    primary_execution_coverage = len(executable) / max(len(candidate_rows), 1)

    independent_candidates = [
        row for row in candidate_rows if EQUS_START <= row["trade_day"] <= END
    ]
    independent_executable = [
        row
        for row in independent_candidates
        if (
            row["trade_day"] not in equs_excluded
            and v46.execution_available(equs, row["trade_day"], row["symbol"])
        )
    ]
    independent_coverage = len(independent_executable) / max(
        len(independent_candidates), 1
    )

    comparison_days = sorted(
        day for day in set(primary).intersection(alternate) if START <= day <= END
    )
    agreement = sum(
        int(primary[day]["direction"] == alternate[day]["direction"])
        for day in comparison_days
    ) / max(len(comparison_days), 1)
    causality = all(row["signal_day"] < row["trade_day"] for row in candidate_rows)
    gates = {
        "common_signal_coverage_at_least_98_percent": coverage >= 0.98,
        "at_least_two_executable_trades_per_calendar_week": cadence >= 2.0,
        "at_least_100_executable_trades_each_development_year": all(
            count >= 100 for count in year_counts.values()
        ),
        "minority_direction_at_least_20_percent": minority >= 0.20,
        "primary_execution_coverage_at_least_95_percent": (
            primary_execution_coverage >= 0.95
        ),
        "independent_execution_coverage_at_least_95_percent": (
            independent_coverage >= 0.95
        ),
        "primary_alternate_action_agreement_at_least_95_percent": agreement >= 0.95,
        "strict_signal_before_trade_causality": causality,
    }
    payload = {
        "status": "returns_blind_no_post_entry_return_or_pnl_computed",
        "eligible_development_signal_sessions": len(eligible),
        "complete_primary_signal_states": len(complete),
        "common_signal_coverage": coverage,
        "candidate_signals": len(candidate_rows),
        "executable_trades": len(executable),
        "executable_trades_per_calendar_week": cadence,
        "primary_execution_coverage": primary_execution_coverage,
        "year_counts": year_counts,
        "direction_counts": dict(directions),
        "minority_direction_fraction": minority,
        "independent_candidate_signals": len(independent_candidates),
        "independent_executable_signals": len(independent_executable),
        "independent_execution_coverage": independent_coverage,
        "source_action_comparisons": len(comparison_days),
        "primary_alternate_action_agreement_including_cash": agreement,
        "predeclared_feasibility_gates": gates,
        "feasibility_passed": all(gates.values()),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
