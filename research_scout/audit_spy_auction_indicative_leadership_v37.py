"""Returns-blind feasibility gate for SPY auction indicative leadership v37.

This script reads only pre-order auction states and quote availability/quality.
It never calculates a post-entry return or P&L.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_spy_auction_absorption_failure_v35 as shared

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "spy_auction_indicative_leadership_returns_blind_audit_v37.json"
EARLY = "09:28:00"
LATE = "09:29:50"
ADJACENT = ["09:29:30", "09:29:59"]
ENTRY_TARGETS = shared.ENTRY_TARGETS
EXIT_TARGET = shared.EXIT_TARGET
POSITIVE_LADDER = ["SPY", "SSO", "UPRO"]
NEGATIVE_LADDER = ["SH", "SDS", "SPXU"]


def action(early: dict[str, Any] | None, late: dict[str, Any] | None) -> dict[str, Any] | None:
    if early is None or late is None:
        return None
    required = [
        early.get("ref_price"),
        early.get("ind_match_price"),
        late.get("ref_price"),
        late.get("ind_match_price"),
    ]
    if any(value is None or float(value) <= 0 for value in required):
        return None
    reference_return = float(late["ref_price"]) / float(early["ref_price"]) - 1.0
    indicative_return = float(late["ind_match_price"]) / float(early["ind_match_price"]) - 1.0
    leadership = indicative_return - reference_return
    if indicative_return == 0.0 or leadership == 0.0 or indicative_return * leadership <= 0.0:
        return None
    side = "B" if leadership > 0 else "A"
    final_displacement = float(late["ind_match_price"]) / float(late["ref_price"]) - 1.0
    return {
        "side": side,
        "symbol": "UPRO" if side == "B" else "SPXU",
        "early_ref_price": float(early["ref_price"]),
        "late_ref_price": float(late["ref_price"]),
        "early_ind_match_price": float(early["ind_match_price"]),
        "late_ind_match_price": float(late["ind_match_price"]),
        "reference_return": reference_return,
        "indicative_return": indicative_return,
        "indicative_leadership": leadership,
        "final_indicative_displacement": final_displacement,
        "final_imbalance_side": late.get("side"),
        "signal_ts_event": late["ts_event"],
        "signal_ts_recv": late["ts_recv"],
    }


def declared_weeks(start: str, end: str) -> float:
    return ((pd.Timestamp(end) - pd.Timestamp(start)).days + 1) / 7.0


def same_direction(value: float | None, side: str) -> bool:
    return value is not None and ((value > 0 and side == "B") or (value < 0 and side == "A"))


def main() -> int:
    snapshot_payload = shared.load_json(shared.SNAPSHOTS)
    quote_payload = shared.load_json(shared.TARGET_QUOTES)
    audit = shared.load_json(shared.AUDIT)
    if any(payload.get("returns_read") is not False for payload in [snapshot_payload, quote_payload, audit]):
        raise RuntimeError("Returns-blind source artifact is not marked clean")
    snapshots = shared.snapshot_map(snapshot_payload)
    quotes = shared.quote_map(quote_payload)
    excluded = set(audit["degraded_dates"]["ARCX.PILLAR"]) | set(audit["degraded_dates"]["EQUS.MINI"])
    days = sorted({day for day, cutoff in snapshots if cutoff == LATE})

    signals: dict[str, dict[str, Any]] = {}
    for day in days:
        if day in excluded:
            continue
        value = action(snapshots.get((day, EARLY)), snapshots.get((day, LATE)))
        if value is not None:
            signals[day] = value

    adjacent: dict[str, dict[str, dict[str, Any]]] = {}
    for cutoff in ADJACENT:
        adjacent[cutoff] = {
            day: value
            for day in days
            if day not in excluded
            and (value := action(snapshots.get((day, EARLY)), snapshots.get((day, cutoff)))) is not None
        }

    executable: dict[str, dict[str, Any]] = {}
    quote_missing: Counter[str] = Counter()
    relevant_ladder_days = 0
    relevant_ladder_missing: Counter[str] = Counter()
    for day, signal in signals.items():
        if not "2023-03-28" <= day <= "2026-07-24":
            continue
        symbol = signal["symbol"]
        required = [(day, symbol, target) for target in [*ENTRY_TARGETS.values(), EXIT_TARGET]]
        if not all(key in quotes and not quotes[key]["equs_degraded"] for key in required):
            for key in required:
                if key not in quotes:
                    quote_missing[f"{symbol}:{key[2]}"] += 1
            continue
        row = dict(signal)
        row["quotes"] = {target: quotes[(day, symbol, target)] for target in [*ENTRY_TARGETS.values(), EXIT_TARGET]}
        five = row["quotes"][ENTRY_TARGETS[5]]
        row["entry_spread_bps"] = (five["ask"] - five["bid"]) / ((five["ask"] + five["bid"]) / 2.0) * 10_000.0
        executable[day] = row
        ladder = POSITIVE_LADDER if signal["side"] == "B" else NEGATIVE_LADDER
        ladder_keys = [(day, ladder_symbol, ENTRY_TARGETS[5]) for ladder_symbol in ladder]
        if all(key in quotes and not quotes[key]["equs_degraded"] for key in ladder_keys):
            relevant_ladder_days += 1
        else:
            for key in ladder_keys:
                if key not in quotes:
                    relevant_ladder_missing[f"{key[1]}:{key[2]}"] += 1

    feature_dev = [day for day in signals if "2021-01-01" <= day <= "2023-12-31"]
    executable_dev = [day for day in executable if "2023-03-28" <= day <= "2023-12-31"]
    feature_sides = Counter(signals[day]["side"] for day in feature_dev)
    executable_sides = Counter(executable[day]["side"] for day in executable_dev)
    minority_feature = min(feature_sides.values()) / max(sum(feature_sides.values()), 1) if len(feature_sides) == 2 else 0.0
    minority_executable = min(executable_sides.values()) / max(sum(executable_sides.values()), 1) if len(executable_sides) == 2 else 0.0

    stability: dict[str, Any] = {}
    for cutoff, mapping in adjacent.items():
        joint = set(signals) & set(mapping)
        union = set(signals) | set(mapping)
        stability[cutoff] = {
            "signals": len(mapping),
            "joint_signal_days": len(joint),
            "direction_agreement_on_joint_pct": 100.0 * sum(signals[day]["side"] == mapping[day]["side"] for day in joint) / max(len(joint), 1),
            "identical_action_including_cash_pct": 100.0 * sum((signals.get(day) or {}).get("side") == (mapping.get(day) or {}).get("side") for day in union) / max(len(union), 1),
        }

    controls = {
        "recent_reference_return_same_direction_pct": 100.0 * sum(
            same_direction(signal["reference_return"], signal["side"])
            for signal in signals.values()
        ) / max(sum(signal["reference_return"] != 0 for signal in signals.values()), 1),
        "final_indicative_displacement_same_direction_pct": 100.0 * sum(
            same_direction(signal["final_indicative_displacement"], signal["side"])
            for signal in signals.values()
        ) / max(sum(signal["final_indicative_displacement"] != 0 for signal in signals.values()), 1),
        "final_imbalance_side_same_direction_pct": 100.0 * sum(
            signal["final_imbalance_side"] == signal["side"]
            for signal in signals.values()
            if signal["final_imbalance_side"] in {"A", "B"}
        ) / max(sum(signal["final_imbalance_side"] in {"A", "B"} for signal in signals.values()), 1),
    }

    by_year = {
        str(year): {
            "signals": sum(day.startswith(str(year)) for day in signals),
            "executable_signals": sum(day.startswith(str(year)) for day in executable),
            "side_counts": dict(Counter(signal["side"] for day, signal in signals.items() if day.startswith(str(year)))),
        }
        for year in range(2021, 2027)
    }
    overlap_signals = sum("2023-03-28" <= day <= "2026-07-24" for day in signals)
    quote_coverage = len(executable) / max(overlap_signals, 1)
    ladder_coverage = relevant_ladder_days / max(len(executable), 1)

    cutoff_time = pd.Timestamp("09:29:50").time()
    earliest_order_time = pd.Timestamp("09:30:01").time()
    event_before_cutoff = all(pd.Timestamp(signal["signal_ts_event"]).tz_convert("America/New_York").time() < cutoff_time for signal in signals.values())
    recv_before_cutoff = all(pd.Timestamp(signal["signal_ts_recv"]).tz_convert("America/New_York").time() < cutoff_time for signal in signals.values())
    recv_before_order = all(pd.Timestamp(signal["signal_ts_recv"]).tz_convert("America/New_York").time() < earliest_order_time for signal in signals.values())

    gates = {
        "feature_frequency_at_least_two_per_declared_week_2021_2023": len(feature_dev) / declared_weeks("2021-01-01", "2023-12-31") >= 2.0,
        "executable_frequency_at_least_two_per_declared_week_2023_overlap": len(executable_dev) / declared_weeks("2023-03-28", "2023-12-31") >= 2.0,
        "at_least_100_feature_signals_each_development_year": all(by_year[str(year)]["signals"] >= 100 for year in [2021, 2022, 2023]),
        "at_least_20_feature_signals_2026_extension": by_year["2026"]["signals"] >= 20,
        "minority_feature_side_at_least_20pct": minority_feature >= 0.20,
        "minority_executable_side_at_least_20pct": minority_executable >= 0.20,
        "upro_and_spxu_each_present_in_executable_development": len(executable_sides) == 2 and all(value > 0 for value in executable_sides.values()),
        "actuator_quote_coverage_at_least_90pct": quote_coverage >= 0.90,
        "relevant_side_ladder_5s_availability_at_least_80pct": ladder_coverage >= 0.80,
        "adjacent_09_29_30_identical_action_at_least_60pct": stability["09:29:30"]["identical_action_including_cash_pct"] >= 60.0,
        "adjacent_09_29_59_identical_action_at_least_60pct": stability["09:29:59"]["identical_action_including_cash_pct"] >= 60.0,
        "not_redundant_to_recent_reference_momentum_below_80pct": controls["recent_reference_return_same_direction_pct"] < 80.0,
        "not_redundant_to_final_displacement_below_80pct": controls["final_indicative_displacement_same_direction_pct"] < 80.0,
        "not_redundant_to_final_imbalance_side_below_80pct": controls["final_imbalance_side_same_direction_pct"] < 80.0,
        "ts_event_and_ts_recv_before_cutoff_and_order": event_before_cutoff and recv_before_cutoff and recv_before_order,
    }

    payload = {
        "status": "passed_returns_blind_feasibility" if all(gates.values()) else "failed_returns_blind_feasibility_no_pnl_opened",
        "returns_read": False,
        "rule": {
            "early_cutoff": EARLY,
            "late_cutoff": LATE,
            "condition": "indicative return is nonzero and has the same sign as indicative return minus reference return",
            "direction": "sign of indicative leadership",
            "actuator": "positive -> UPRO; negative -> SPXU",
            "entry_targets": ENTRY_TARGETS,
            "exit_target": EXIT_TARGET,
            "maximum_event_wait_seconds": 60,
        },
        "degraded_dates_excluded_union": sorted(excluded),
        "feature_development_2021_2023": {
            "signals": len(feature_dev),
            "trades_per_declared_calendar_week": len(feature_dev) / declared_weeks("2021-01-01", "2023-12-31"),
            "side_counts": dict(feature_sides),
            "minority_side_share": minority_feature,
        },
        "executable_development_overlap_2023_03_28_2023_12_31": {
            "signals": len(executable_dev),
            "trades_per_declared_calendar_week": len(executable_dev) / declared_weeks("2023-03-28", "2023-12-31"),
            "side_counts": dict(executable_sides),
            "minority_side_share": minority_executable,
        },
        "all_overlap": {
            "signals": overlap_signals,
            "executable_signals": len(executable),
            "actuator_quote_coverage_pct": 100.0 * quote_coverage,
            "relevant_side_ladder_5s_available_days": relevant_ladder_days,
            "relevant_side_ladder_coverage_pct": 100.0 * ladder_coverage,
            "quote_missing": dict(quote_missing),
            "relevant_ladder_missing": dict(relevant_ladder_missing),
        },
        "by_year": by_year,
        "adjacent_cutoff_stability": stability,
        "returns_blind_control_distinctness": controls,
        "timestamp_observability": {
            "ts_event_before_cutoff": event_before_cutoff,
            "ts_recv_before_cutoff": recv_before_cutoff,
            "ts_recv_before_earliest_order": recv_before_order,
        },
        "gates": gates,
        "gate_passed": all(gates.values()),
        "signals": signals,
        "executable_signal_dates": sorted(executable),
        "warning": "No post-entry bid, exit return, P&L, profit factor, or benchmark outcome was calculated.",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "feature_signals": len(feature_dev),
        "feature_trades_per_week": payload["feature_development_2021_2023"]["trades_per_declared_calendar_week"],
        "executable_development_signals": len(executable_dev),
        "executable_trades_per_week": payload["executable_development_overlap_2023_03_28_2023_12_31"]["trades_per_declared_calendar_week"],
        "failed_gates": [name for name, passed in gates.items() if not passed],
        "output": str(OUTPUT.relative_to(ROOT)),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
