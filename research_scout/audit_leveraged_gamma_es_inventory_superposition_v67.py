"""Returns-blind audit of leveraged-fund / ES inventory superposition v67.

The audit may inspect prices only through the completed 15:29 signal bar.
Later ETF quotes are inspected only for existence and validity. It never
calculates an entry-to-exit return, P&L, or a 2024-2025 strategy outcome.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay
from research_scout import audit_upro_spxu_premarket_wrapper_premium as v19
from research_scout import test_upro_spxu_creative_hypotheses as base

ROOT = Path(__file__).resolve().parents[1]
V63_AUDIT = (
    ROOT
    / "research_scout"
    / "leveraged_fund_rebalance_capacity_returns_blind_audit_v63.json"
)
ES_FEATURES = (
    ROOT
    / "external_artifacts"
    / "databento_es_close"
    / "GLBX.MDP3"
    / "es_close_flow_features_2021_2025.parquet"
)
OUTPUT = (
    ROOT
    / "research_scout"
    / "leveraged_gamma_es_inventory_superposition_returns_blind_audit_v67.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "LEVERAGED_GAMMA_ES_INVENTORY_SUPERPOSITION_AUDIT_V67.md"
)

START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")
PRIMARY_SIGNAL_CLOCK = "15:29"
ADJACENT_SIGNAL_CLOCK = "15:28"
ENTRY_CLOCK = "15:31"
EXIT_CLOCK = "15:59"
ES_MULTIPLIER = 50.0


def sign(value: float) -> int:
    return int(value > 0) - int(value < 0)


def clock_stamp(day: pd.Timestamp, clock: str, timezone: Any) -> pd.Timestamp:
    hour, minute = (int(part) for part in clock.split(":"))
    return day.tz_localize(timezone) + pd.Timedelta(hours=hour, minutes=minute)


def exact_close(
    sessions: dict[pd.Timestamp, pd.DataFrame],
    day: pd.Timestamp,
    clock: str,
) -> float | None:
    frame = sessions.get(day)
    if frame is None:
        return None
    row = base.exact_row(frame, clock_stamp(day, clock, frame.index.tz))
    if row is None:
        return None
    value = float(row["close"])
    return value if math.isfinite(value) and value > 0 else None


def load_v63_states() -> dict[pd.Timestamp, dict[str, Any]]:
    payload = json.loads(V63_AUDIT.read_text(encoding="utf-8"))
    if payload.get("gate_passed") is not False:
        raise RuntimeError("Expected terminal returns-blind v63 audit")
    return {
        pd.Timestamp(row["session_date"]).normalize(): row
        for row in payload["states"]
        if START <= pd.Timestamp(row["session_date"]).normalize() <= END
    }


def load_es() -> dict[pd.Timestamp, dict[str, Any]]:
    frame = pd.read_parquet(ES_FEATURES)
    frame["day"] = pd.to_datetime(frame["date"]).dt.normalize()
    frame = frame[frame["day"].between(START, END)].copy()
    valid = (
        (frame["rth_bar_count"] == 390)
        & ~frame["short_session"].astype(bool)
        & ~frame["degraded"].astype(bool)
        & frame["mechanically_eligible"].astype(bool)
        & frame["es_roll_match"].astype(bool)
        & (frame["trade_rows"] > 0)
        & frame["signed_volume"].notna()
        & frame["preclose_price"].notna()
        & (frame["preclose_price"] > 0)
    )
    frame = frame.loc[valid].copy()
    if frame["day"].duplicated().any():
        raise RuntimeError("Duplicate ES session rows")
    return {
        pd.Timestamp(row["day"]).normalize(): row
        for row in frame.to_dict(orient="records")
    }


def build_states(
    v63_states: dict[pd.Timestamp, dict[str, Any]],
    es: dict[pd.Timestamp, dict[str, Any]],
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
    signal_clock: str,
) -> dict[pd.Timestamp, dict[str, Any]]:
    rows: dict[pd.Timestamp, dict[str, Any]] = {}
    for day in sorted(set(v63_states).intersection(es)):
        if day in excluded:
            continue
        source = v63_states[day]
        spy_now = exact_close(spy_sessions, day, signal_clock)
        if spy_now is None:
            continue
        late_price = float(source["spy_signal_price"])
        late_return = float(source["spy_return_to_signal"])
        prior_close = late_price / (1.0 + late_return)
        if not math.isfinite(prior_close) or prior_close <= 0:
            continue
        spy_return = spy_now / prior_close - 1.0
        if not math.isfinite(spy_return) or abs(spy_return) > 0.25:
            continue
        coefficient = float(source["coefficient_aum_dollars"])
        fund_pressure = coefficient * spy_return
        es_row = es[day]
        es_pressure = (
            float(es_row["signed_volume"])
            * float(es_row["preclose_price"])
            * ES_MULTIPLIER
        )
        net_pressure = fund_pressure + es_pressure
        direction = sign(net_pressure)
        action = "UPRO" if direction > 0 else "SPXU" if direction < 0 else "CASH"
        rows[day] = {
            "session_date": day.strftime("%Y-%m-%d"),
            "source_date": source["source_date"],
            "signal_clock": signal_clock,
            "action": action,
            "direction": direction,
            "spy_signal_price": spy_now,
            "prior_official_close": prior_close,
            "spy_return_to_signal": spy_return,
            "coefficient_aum_dollars": coefficient,
            "fund_pressure_dollars": fund_pressure,
            "es_signed_contracts": float(es_row["signed_volume"]),
            "es_reference_price": float(es_row["preclose_price"]),
            "es_inventory_transfer_dollars": es_pressure,
            "net_pressure_dollars": net_pressure,
            "fund_only_action": (
                "UPRO"
                if sign(fund_pressure) > 0
                else "SPXU"
                if sign(fund_pressure) < 0
                else "CASH"
            ),
            "es_only_action": (
                "UPRO"
                if sign(es_pressure) > 0
                else "SPXU"
                if sign(es_pressure) < 0
                else "CASH"
            ),
        }
    return rows


def action_agreement(
    first: dict[pd.Timestamp, dict[str, Any]],
    second: dict[pd.Timestamp, dict[str, Any]],
) -> dict[str, Any]:
    joint = sorted(set(first).intersection(second))
    return {
        "joint_sessions": len(joint),
        "identical_action_including_cash": sum(
            first[day]["action"] == second[day]["action"] for day in joint
        )
        / max(len(joint), 1),
    }


def component_agreement(
    states: dict[pd.Timestamp, dict[str, Any]], key: str
) -> float:
    return sum(row["action"] == row[key] for row in states.values()) / max(
        len(states), 1
    )


def fixed_coefficient_actions(
    states: dict[pd.Timestamp, dict[str, Any]]
) -> dict[pd.Timestamp, str]:
    first_day = min(states)
    coefficient = float(states[first_day]["coefficient_aum_dollars"])
    result: dict[pd.Timestamp, str] = {}
    for day, row in states.items():
        pressure = (
            coefficient * float(row["spy_return_to_signal"])
            + float(row["es_inventory_transfer_dollars"])
        )
        result[day] = (
            "UPRO" if pressure > 0 else "SPXU" if pressure < 0 else "CASH"
        )
    return result


def shifted_es_actions(
    states: dict[pd.Timestamp, dict[str, Any]]
) -> dict[pd.Timestamp, str]:
    days = sorted(states)
    result: dict[pd.Timestamp, str] = {}
    for prior_day, day in zip(days, days[1:]):
        pressure = float(states[day]["fund_pressure_dollars"]) + float(
            states[prior_day]["es_inventory_transfer_dollars"]
        )
        result[day] = (
            "UPRO" if pressure > 0 else "SPXU" if pressure < 0 else "CASH"
        )
    return result


def quote_coverage(
    states: dict[pd.Timestamp, dict[str, Any]],
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
) -> dict[str, Any]:
    signals = {
        day: row
        for day, row in states.items()
        if row["action"] != "CASH" and day not in excluded
    }
    entry_valid = 0
    exit_valid = 0
    both_valid = 0
    for day, row in signals.items():
        frame = sessions.get(day, {}).get(row["action"])
        if frame is None:
            continue
        entry = base.exact_row(
            frame, clock_stamp(day, ENTRY_CLOCK, frame.index.tz)
        )
        exit_quote = base.exact_row(
            frame, clock_stamp(day, EXIT_CLOCK, frame.index.tz)
        )
        entry_ok = base.valid_quote(entry)
        exit_ok = base.valid_quote(exit_quote)
        entry_valid += int(entry_ok)
        exit_valid += int(exit_ok)
        both_valid += int(entry_ok and exit_ok)
    return {
        "signals": len(signals),
        "entry_valid": entry_valid,
        "exit_valid": exit_valid,
        "entry_exit_valid": both_valid,
        "entry_coverage": entry_valid / max(len(signals), 1),
        "exit_coverage": exit_valid / max(len(signals), 1),
        "entry_exit_coverage": both_valid / max(len(signals), 1),
    }


def switches_by_year(
    states: dict[pd.Timestamp, dict[str, Any]]
) -> dict[str, int]:
    result: dict[str, int] = {}
    for year in (2021, 2022, 2023):
        actions = [
            states[day]["action"]
            for day in sorted(states)
            if day.year == year and states[day]["action"] != "CASH"
        ]
        result[str(year)] = sum(a != b for a, b in zip(actions, actions[1:]))
    return result


def compare_action_map(
    states: dict[pd.Timestamp, dict[str, Any]],
    action_map: dict[pd.Timestamp, str],
) -> dict[str, Any]:
    joint = sorted(set(states).intersection(action_map))
    return {
        "joint_sessions": len(joint),
        "identical_action_including_cash": sum(
            states[day]["action"] == action_map[day] for day in joint
        )
        / max(len(joint), 1),
    }


def render(payload: dict[str, Any]) -> str:
    development = payload["development_2021_2023"]
    failures = [name for name, passed in payload["gates"].items() if not passed]
    lines = [
        "# Leveraged-Fund Gamma / ES Inventory Superposition Audit v67",
        "",
        "## Verdict",
        "",
        (
            "**Every returns-blind gate passed. The frozen 2021–2023 P&L "
            "test is authorized; recent years remain locked.**"
            if payload["gate_passed"]
            else "**Rejected returns-blind before P&L.**"
        ),
        "",
        "## Frozen construction",
        "",
        "- Add first-order four-fund rebalance demand through SPY 15:29 to "
        "completed 15:00–15:30 ES aggressor inventory transfer.",
        "- Both terms are signed S&P-dollar exposure.",
        "- Positive net pressure selects UPRO; negative selects SPXU.",
        "- Planned execution is 15:31 ask to 15:59 bid.",
        "",
        "## Reachability and balance",
        "",
        f"- Eligible states: {development['eligible_states']} "
        f"({development['eligible_coverage']:.3%})",
        f"- Signals: {development['signals']} "
        f"({development['signals_per_week']:.3f}/week)",
        f"- UPRO / SPXU: {development['upro_signals']} / "
        f"{development['spxu_signals']}",
        "- By year: "
        + ", ".join(
            f"{year}={count}"
            for year, count in development["signals_by_year"].items()
        ),
        "- Direction switches: "
        + ", ".join(
            f"{year}={count}"
            for year, count in development["switches_by_year"].items()
        ),
        "",
        "## Stability and distinctness",
        "",
        f"- 15:28 neighboring action agreement: "
        f"{payload['adjacent_clock_stability']['identical_action_including_cash']:.3%}",
        f"- Agreement with fund-only action: "
        f"{payload['distinctness']['fund_only_action_agreement']:.3%}",
        f"- Agreement with ES-only action: "
        f"{payload['distinctness']['es_only_action_agreement']:.3%}",
        f"- Agreement with first-2021 fixed AUM coefficient: "
        f"{payload['distinctness']['fixed_coefficient']['identical_action_including_cash']:.3%}",
        f"- Agreement with one-session-shifted ES term: "
        f"{payload['distinctness']['shifted_es']['identical_action_including_cash']:.3%}",
        "",
        "## Quote evidence",
        "",
        f"- Primary entry+exit coverage: "
        f"{payload['quote_evidence']['primary']['entry_exit_coverage']:.3%}",
        f"- Independent-overlap entry+exit coverage: "
        f"{payload['quote_evidence']['independent']['entry_exit_coverage']:.3%}",
        "",
        "## Gates",
        "",
    ]
    lines.extend(
        f"- {name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in payload["gates"].items()
    )
    lines.extend(
        [
            "",
            "Failed gates: " + (", ".join(failures) if failures else "none"),
            "",
            "No entry-to-exit return, P&L, or 2024–2025 strategy outcome was "
            "calculated.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    v63_states = load_v63_states()
    es = load_es()

    spy_arca = v19.spy_sessions(v19.ARCA_SPY)
    excluded_arca = relay.degraded(relay.ARCA_CONDITIONS)
    primary = build_states(
        v63_states,
        es,
        spy_arca,
        excluded_arca,
        PRIMARY_SIGNAL_CLOCK,
    )
    adjacent = build_states(
        v63_states,
        es,
        spy_arca,
        excluded_arca,
        ADJACENT_SIGNAL_CLOCK,
    )

    spy_equs = v19.spy_sessions(v19.EQUS_SPY)
    excluded_equs = relay.degraded(relay.EQUS_CONDITIONS)
    independent = build_states(
        v63_states,
        es,
        spy_equs,
        excluded_equs,
        PRIMARY_SIGNAL_CLOCK,
    )

    counts = Counter(
        row["action"] for row in primary.values() if row["action"] != "CASH"
    )
    signals_by_year = {
        str(year): sum(
            day.year == year and row["action"] != "CASH"
            for day, row in primary.items()
        )
        for year in (2021, 2022, 2023)
    }
    switches = switches_by_year(primary)
    expected_sessions = 753
    signal_count = sum(counts.values())
    development = {
        "expected_sessions": expected_sessions,
        "eligible_states": len(primary),
        "eligible_coverage": len(primary) / expected_sessions,
        "signals": signal_count,
        "signals_per_week": signal_count / (expected_sessions / 5.0),
        "upro_signals": counts["UPRO"],
        "spxu_signals": counts["SPXU"],
        "minority_share": min(counts.values()) / max(signal_count, 1),
        "signals_by_year": signals_by_year,
        "switches_by_year": switches,
    }

    adjacent_stability = action_agreement(primary, adjacent)
    fixed_actions = fixed_coefficient_actions(primary)
    shifted_actions = shifted_es_actions(primary)
    distinctness = {
        "fund_only_action_agreement": component_agreement(
            primary, "fund_only_action"
        ),
        "es_only_action_agreement": component_agreement(
            primary, "es_only_action"
        ),
        "fixed_coefficient": compare_action_map(primary, fixed_actions),
        "shifted_es": compare_action_map(primary, shifted_actions),
    }

    arca_pair = relay.sessions(relay.ARCA_PATH)
    equs_pair = relay.sessions(relay.EQUS_PATH)
    quote_evidence = {
        "primary": quote_coverage(primary, arca_pair, excluded_arca),
        "independent": quote_coverage(
            independent, equs_pair, excluded_equs
        ),
    }

    source_dates_causal = all(
        pd.Timestamp(row["source_date"]).normalize() < day
        for day, row in primary.items()
    )
    gates = {
        "eligible_coverage_at_least_95_percent": development[
            "eligible_coverage"
        ]
        >= 0.95,
        "signal_frequency_at_least_2_per_week": development[
            "signals_per_week"
        ]
        >= 2.0,
        "at_least_100_signals_each_year": min(signals_by_year.values())
        >= 100,
        "both_sleeves_and_minority_at_least_35_percent": len(counts) == 2
        and development["minority_share"] >= 0.35,
        "at_least_20_action_switches_each_year": min(switches.values())
        >= 20,
        "adjacent_15_28_action_stability_at_least_85_percent": adjacent_stability[
            "identical_action_including_cash"
        ]
        >= 0.85,
        "combined_distinct_from_fund_only_below_90_percent": distinctness[
            "fund_only_action_agreement"
        ]
        <= 0.90,
        "combined_distinct_from_es_only_below_90_percent": distinctness[
            "es_only_action_agreement"
        ]
        <= 0.90,
        "primary_entry_exit_quote_coverage_at_least_95_percent": quote_evidence[
            "primary"
        ]["entry_exit_coverage"]
        >= 0.95,
        "independent_entry_exit_quote_coverage_at_least_90_percent": quote_evidence[
            "independent"
        ]["entry_exit_coverage"]
        >= 0.90,
        "all_aum_source_dates_strictly_before_signal_dates": source_dates_causal,
        "no_fitted_threshold_or_rescaling": True,
        "no_post_entry_return_or_recent_outcome_read": True,
    }

    payload = {
        "status": "returns_blind_v67_audit",
        "sources": {
            "aum_and_formula": str(V63_AUDIT.relative_to(ROOT)),
            "es_flow": str(ES_FEATURES.relative_to(ROOT)),
            "new_databento_calls_or_purchases": False,
        },
        "rule": {
            "fund_pressure": (
                "sum L*(L-1)*prior official AUM times SPY return through "
                "completed 15:29 bar"
            ),
            "es_inventory_transfer": (
                "15:00-15:30 ES signed aggressor contracts times ES price "
                "times 50"
            ),
            "net_pressure": "fund pressure plus ES inventory transfer",
            "action": "positive UPRO, negative SPXU, exact zero cash",
            "planned_entry": ENTRY_CLOCK,
            "planned_exit": EXIT_CLOCK,
        },
        "development_2021_2023": development,
        "adjacent_clock_stability": adjacent_stability,
        "independent_feature_overlap_2023": action_agreement(
            primary, independent
        ),
        "distinctness": distinctness,
        "quote_evidence": quote_evidence,
        "gates": gates,
        "gate_passed": all(gates.values()),
        "decision": (
            "authorize_frozen_development_pnl_only"
            if all(gates.values())
            else "reject_before_pnl"
        ),
        "states": [row for _, row in sorted(primary.items())],
        "independent_states_2023": [
            row for _, row in sorted(independent.items())
        ],
        "control_actions": {
            "fixed_coefficient": [
                {
                    "session_date": day.strftime("%Y-%m-%d"),
                    "action": action,
                }
                for day, action in sorted(fixed_actions.items())
            ],
            "shifted_es": [
                {
                    "session_date": day.strftime("%Y-%m-%d"),
                    "action": action,
                }
                for day, action in sorted(shifted_actions.items())
            ],
        },
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    REPORT.write_text(render(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                key: value
                for key, value in payload.items()
                if key
                not in {
                    "states",
                    "independent_states_2023",
                    "control_actions",
                }
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
