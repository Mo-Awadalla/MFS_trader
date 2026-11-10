"""Evaluate the preregistered SPY/IEF joint macro impulse hypothesis v56.

The 2024-2025 partition is read only if every frozen 2021-2023 development
gate passes. This module intentionally contains no parameter search.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_spy_ief_joint_macro_impulse_v56 as audit
from research_scout import audit_spy_vx_curve_confirmation_failure_v46 as v46
from research_scout import test_spy_vx_forward_stress_persistence_v47 as v47
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "spy_ief_joint_macro_impulse_results_v56.json"
REPORT = ROOT / "research_scout" / "SPY_IEF_JOINT_MACRO_IMPULSE_REPORT_V56.md"
DEVELOPMENT_START = pd.Timestamp("2021-01-01")
DEVELOPMENT_END = pd.Timestamp("2023-12-31")
HOLDOUT_START = pd.Timestamp("2024-01-01")
HOLDOUT_END = pd.Timestamp("2025-12-31")


def build_trade_directions(
    states: dict[pd.Timestamp, dict[str, Any]],
    next_session: dict[pd.Timestamp, pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, dict[pd.Timestamp, int]]:
    variants: dict[str, dict[pd.Timestamp, int]] = {
        "actual": {},
        "prior_spy_continuation": {},
        "prior_ief_continuation": {},
        "one_session_lagged_ief_confirmation": {},
        "sign_flipped": {},
    }
    ordered = sorted(states)
    previous = {
        day: states[ordered[index - 1]]
        for index, day in enumerate(ordered)
        if index
    }
    for signal_day in ordered:
        trade_day = next_session.get(signal_day)
        if trade_day is None or not start <= trade_day <= end:
            continue
        state = states[signal_day]
        actual = int(state["direction"])
        spy_direction = int(state["spy_direction"])
        ief_direction = int(state["ief_direction"])
        prior = previous.get(signal_day)
        lagged_confirmation = 0
        if prior is not None and int(prior["ief_direction"]) == spy_direction:
            lagged_confirmation = spy_direction
        variants["actual"][trade_day] = actual
        variants["prior_spy_continuation"][trade_day] = spy_direction
        variants["prior_ief_continuation"][trade_day] = ief_direction
        variants["one_session_lagged_ief_confirmation"][
            trade_day
        ] = lagged_confirmation
        variants["sign_flipped"][trade_day] = -actual
    return variants


def development_gates(
    result: dict[str, Any],
    independent: dict[str, Any],
) -> dict[str, bool]:
    observed = result["observed_bbo"]
    years = observed.get("year_pnl_usd", {})
    instruments = observed.get("instrument_pnl_usd", {})
    controls = result["controls"]
    mean_pnl = float(observed["mean_session_pnl_usd"])
    return {
        "minimum_two_trades_per_week": observed["trades_per_week"] >= 2.0,
        "profit_factor_at_least_1_05": observed["profit_factor"] >= 1.05,
        "positive_fixed_notional_pnl": observed["fixed_notional_pnl_usd"] > 0,
        "each_development_year_positive": all(
            years.get(str(year), 0.0) > 0 for year in [2021, 2022, 2023]
        ),
        "both_upro_and_spxu_positive": all(
            instruments.get(symbol, 0.0) > 0 for symbol in ["UPRO", "SPXU"]
        ),
        "ending_cash_above_spy_total_return": (
            observed["ending_cash_usd"]
            > result["spy_total_return_hurdle"]["ending_cash_usd"]
        ),
        "positive_after_extra_cent_each_fill": (
            result["extra_cent_each_fill"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_five_minute_entry_delay": (
            result["five_minute_entry_delay"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_deleting_ten_best_trades": (
            observed["pnl_without_best_10_sessions_usd"] > 0
        ),
        "positive_independent_overlap": (
            independent["observed_bbo"]["fixed_notional_pnl_usd"] > 0
        ),
        "mean_trade_pnl_above_prior_spy_continuation": (
            mean_pnl
            > controls["prior_spy_continuation"]["mean_session_pnl_usd"]
        ),
        "mean_trade_pnl_above_prior_ief_continuation": (
            mean_pnl
            > controls["prior_ief_continuation"]["mean_session_pnl_usd"]
        ),
        "mean_trade_pnl_above_lagged_ief_confirmation": (
            mean_pnl
            > controls["one_session_lagged_ief_confirmation"][
                "mean_session_pnl_usd"
            ]
        ),
        "mean_trade_pnl_above_sign_flipped": (
            mean_pnl > controls["sign_flipped"]["mean_session_pnl_usd"]
        ),
    }


def render(payload: dict[str, Any]) -> str:
    development = payload["development"]
    observed = development["observed_bbo"]
    failures = [
        name for name, passed in payload["development_gates"].items() if not passed
    ]
    if payload["development_passed"] and payload.get("holdout_passed", False):
        verdict = "**Development and holdout passed.**"
    elif payload["development_passed"]:
        verdict = "**Rejected in the 2024-2025 holdout after passing development.**"
    else:
        verdict = (
            "**Rejected in development; the 2024-2025 return holdout remains locked.**"
        )
    lines = [
        "# SPY / IEF Joint Macro-Impulse Persistence v56",
        "",
        "## Verdict",
        "",
        verdict,
        "",
        "## Development: 2021-2023",
        "",
        f"- Trades: {observed['sessions']} ({observed['trades_per_week']:.3f}/week)",
        f"- Compounded cash: {v47.money(observed['ending_cash_usd'])}",
        f"- Fixed-$100 P&L: {v47.money(observed['fixed_notional_pnl_usd'])}",
        f"- Profit factor: {observed['profit_factor']:.3f}",
        (
            "- Split/dividend-adjusted SPY hurdle: "
            f"{v47.money(development['spy_total_return_hurdle']['ending_cash_usd'])}"
        ),
        (
            "- P&L after deleting ten best trades: "
            f"{v47.money(observed['pnl_without_best_10_sessions_usd'])}"
        ),
        (
            "- Extra-cent stress P&L: "
            f"{v47.money(development['extra_cent_each_fill']['fixed_notional_pnl_usd'])}"
        ),
        (
            "- Five-minute delay P&L: "
            f"{v47.money(development['five_minute_entry_delay']['fixed_notional_pnl_usd'])}"
        ),
        "",
        "Failed development gates: "
        + (", ".join(failures) if failures else "none"),
        "",
    ]
    if payload["development_passed"]:
        holdout = payload["holdout"]["observed_bbo"]
        lines.extend(
            [
                "## Holdout: 2024-2025",
                "",
                f"- Trades: {holdout['sessions']} ({holdout['trades_per_week']:.3f}/week)",
                f"- Compounded cash: {v47.money(holdout['ending_cash_usd'])}",
                f"- Fixed-$100 P&L: {v47.money(holdout['fixed_notional_pnl_usd'])}",
                f"- Profit factor: {holdout['profit_factor']:.3f}",
                "",
            ]
        )
    lines.extend(
        [
            "## Integrity boundary",
            "",
            "The sensor, direction map, clocks, controls, and gates were frozen "
            "before target-return inspection. No return threshold, alternate "
            "duration ETF, regime filter, sign change, or timing repair was made.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    feasibility = json.loads(audit.OUTPUT.read_text(encoding="utf-8"))
    if not feasibility.get("feasibility_passed"):
        raise RuntimeError("V56 returns-blind feasibility audit must pass before returns")

    v47._repair_vendor_version_metadata()
    states = audit.build_states(
        audit.load_daily(audit.YAHOO / "SPY_1d.parquet"),
        audit.load_daily(audit.YAHOO / "IEF_1d.parquet"),
    )
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    next_session = v46.next_session_map(spy)
    development_variants = build_trade_directions(
        states, next_session, DEVELOPMENT_START, DEVELOPMENT_END
    )
    development = v47.evaluate(
        arca,
        spy,
        arca_excluded,
        development_variants,
        DEVELOPMENT_START,
        DEVELOPMENT_END,
        10,
    )
    independent = v47.evaluate(
        equs,
        spy,
        equs_excluded,
        development_variants,
        audit.EQUS_START,
        DEVELOPMENT_END,
        5,
    )
    gates = development_gates(development, independent)
    passed = all(gates.values())
    payload: dict[str, Any] = {
        "specification_id": "spy_ief_joint_macro_impulse_persistence_v56",
        "returns_blind_feasibility": feasibility,
        "development": development,
        "independent_overlap": independent,
        "development_gates": gates,
        "development_passed": passed,
        "holdout_status": "unlocked" if passed else "locked_not_read",
    }
    if passed:
        holdout_variants = build_trade_directions(
            states, next_session, HOLDOUT_START, HOLDOUT_END
        )
        holdout = v47.evaluate(
            arca,
            spy,
            arca_excluded,
            holdout_variants,
            HOLDOUT_START,
            HOLDOUT_END,
            5,
        )
        holdout_gates = v47.holdout_gates(holdout)
        payload["holdout"] = holdout
        payload["holdout_gates"] = holdout_gates
        payload["holdout_passed"] = all(holdout_gates.values())

    safe = v47.json_safe(payload)
    OUTPUT.write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render(safe), encoding="utf-8")
    print(json.dumps(safe, indent=2))


if __name__ == "__main__":
    main()
