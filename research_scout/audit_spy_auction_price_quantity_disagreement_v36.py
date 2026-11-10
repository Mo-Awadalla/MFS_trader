"""Returns-blind feasibility gate for auction price/quantity disagreement v36."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_spy_auction_absorption_failure_v35 as shared

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "spy_auction_price_quantity_disagreement_returns_blind_audit_v36.json"
LATE = "09:29:50"
ADJACENT = ["09:29:30", "09:29:59"]
ENTRY_TARGETS = shared.ENTRY_TARGETS
EXIT_TARGET = shared.EXIT_TARGET
SYMBOLS = shared.SYMBOLS


def action(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None or row["side"] not in {"A", "B"}:
        return None
    required = [row.get("ref_price"), row.get("ind_match_price"), row.get("paired_qty"), row.get("total_imbalance_qty")]
    if any(value is None or float(value) <= 0 for value in required):
        return None
    displacement = float(row["ind_match_price"]) / float(row["ref_price"]) - 1.0
    disagreement = (row["side"] == "B" and displacement < 0) or (row["side"] == "A" and displacement > 0)
    if not disagreement:
        return None
    direction = "A" if row["side"] == "B" else "B"
    return {
        "imbalance_side": row["side"],
        "side": direction,
        "symbol": "UPRO" if direction == "B" else "SPXU",
        "ref_price": float(row["ref_price"]),
        "ind_match_price": float(row["ind_match_price"]),
        "indicative_displacement": displacement,
        "paired_qty": int(row["paired_qty"]),
        "total_imbalance_qty": int(row["total_imbalance_qty"]),
        "signal_ts_event": row["ts_event"],
    }


def main() -> int:
    snapshot_payload = shared.load_json(shared.SNAPSHOTS)
    quote_payload = shared.load_json(shared.TARGET_QUOTES)
    audit = shared.load_json(shared.AUDIT)
    if any(payload.get("returns_read") is not False for payload in [snapshot_payload, quote_payload, audit]):
        raise RuntimeError("Returns-blind source artifact is not marked clean")
    snapshots = shared.snapshot_map(snapshot_payload)
    quotes = shared.quote_map(quote_payload)
    prior_closes = shared.previous_close_map()
    excluded = set(audit["degraded_dates"]["ARCX.PILLAR"]) | set(audit["degraded_dates"]["EQUS.MINI"])
    days = sorted({day for day, cutoff in snapshots if cutoff == LATE})
    signals: dict[str, dict[str, Any]] = {}
    for day in days:
        if day in excluded:
            continue
        value = action(snapshots.get((day, LATE)))
        if value is None:
            continue
        early = snapshots.get((day, shared.EARLY))
        close = prior_closes.get(day)
        value["opening_gap"] = float(early["ref_price"]) / close - 1.0 if early and close and float(early["ref_price"]) > 0 else None
        value["recent_reference_return"] = value["ref_price"] / float(early["ref_price"]) - 1.0 if early and float(early["ref_price"]) > 0 else None
        value["paired_qty_change"] = value["paired_qty"] / float(early["paired_qty"]) - 1.0 if early and float(early["paired_qty"]) > 0 else None
        signals[day] = value
    adjacent: dict[str, dict[str, dict[str, Any]]] = {}
    for cutoff in ADJACENT:
        adjacent[cutoff] = {
            day: value
            for day in days
            if day not in excluded
            and (value := action(snapshots.get((day, cutoff)))) is not None
        }
    executable: dict[str, dict[str, Any]] = {}
    quote_missing: Counter[str] = Counter()
    cross_ladder_days = 0
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
        if all((day, symbol_name, ENTRY_TARGETS[5]) in quotes for symbol_name in SYMBOLS):
            cross_ladder_days += 1
    feature_dev = [day for day in signals if "2021-01-01" <= day <= "2023-12-31"]
    executable_dev = [day for day in executable if "2023-03-28" <= day <= "2023-12-31"]
    side_counts = Counter(signals[day]["side"] for day in feature_dev)
    executable_sides = Counter(executable[day]["side"] for day in executable_dev)
    minority = min(side_counts.values()) / max(sum(side_counts.values()), 1) if len(side_counts) == 2 else 0.0
    executable_minority = min(executable_sides.values()) / max(sum(executable_sides.values()), 1) if len(executable_sides) == 2 else 0.0
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
        "opening_gap_same_direction_pct": 100.0 * sum(
            signal["opening_gap"] is not None and ((signal["opening_gap"] > 0 and signal["side"] == "B") or (signal["opening_gap"] < 0 and signal["side"] == "A"))
            for signal in signals.values()
        ) / max(sum(signal["opening_gap"] not in {None, 0} for signal in signals.values()), 1),
        "recent_reference_momentum_same_direction_pct": 100.0 * sum(
            signal["recent_reference_return"] is not None and ((signal["recent_reference_return"] > 0 and signal["side"] == "B") or (signal["recent_reference_return"] < 0 and signal["side"] == "A"))
            for signal in signals.values()
        ) / max(sum(signal["recent_reference_return"] not in {None, 0} for signal in signals.values()), 1),
        "paired_quantity_declined_pct": 100.0 * sum(signal["paired_qty_change"] is not None and signal["paired_qty_change"] < 0 for signal in signals.values()) / max(len(signals), 1),
    }
    by_year = {
        str(year): {
            "signals": sum(day.startswith(str(year)) for day in signals),
            "executable_signals": sum(day.startswith(str(year)) for day in executable),
            "side_counts": dict(Counter(signal["side"] for day, signal in signals.items() if day.startswith(str(year)))),
        }
        for year in range(2021, 2027)
    }
    overlap_signals = sum(day >= "2023-03-28" for day in signals)
    quote_coverage = len(executable) / max(overlap_signals, 1)
    gates = {
        "feature_frequency_at_least_two_per_week_2021_2023": len(feature_dev) / shared.span_weeks(feature_dev) >= 2.0,
        "executable_frequency_at_least_two_per_week_2023_overlap": len(executable_dev) / shared.span_weeks(executable_dev) >= 2.0,
        "at_least_100_feature_signals_each_development_year": all(by_year[str(year)]["signals"] >= 100 for year in [2021, 2022, 2023]),
        "minority_feature_side_at_least_20pct": minority >= 0.20,
        "minority_executable_side_at_least_20pct": executable_minority >= 0.20,
        "upro_and_spxu_each_present_in_executable_development": len(executable_sides) == 2 and all(value > 0 for value in executable_sides.values()),
        "quote_coverage_at_least_90pct": quote_coverage >= 0.90,
        "cross_ladder_5s_availability_at_least_80pct": cross_ladder_days / max(len(executable), 1) >= 0.80,
        "adjacent_09_29_30_identical_action_at_least_60pct": stability["09:29:30"]["identical_action_including_cash_pct"] >= 60.0,
        "adjacent_09_29_59_identical_action_at_least_60pct": stability["09:29:59"]["identical_action_including_cash_pct"] >= 60.0,
        "not_redundant_to_gap_below_80pct": controls["opening_gap_same_direction_pct"] < 80.0,
        "not_redundant_to_recent_momentum_below_80pct": controls["recent_reference_momentum_same_direction_pct"] < 80.0,
        "no_timestamp_lookahead": all(pd.Timestamp(signal["signal_ts_event"]).tz_convert("America/New_York").time() < pd.Timestamp("09:29:50").time() for signal in signals.values()),
    }
    payload = {
        "status": "passed_returns_blind_feasibility" if all(gates.values()) else "failed_returns_blind_feasibility_no_pnl_opened",
        "returns_read": False,
        "rule": {
            "cutoff": LATE,
            "condition": "B with negative indicative displacement or A with positive indicative displacement",
            "direction": "price-setting direction opposite imbalance side",
            "actuator": "B price direction -> UPRO; A price direction -> SPXU",
            "entry_targets": ENTRY_TARGETS,
            "exit_target": EXIT_TARGET,
            "maximum_event_wait_seconds": 60,
        },
        "degraded_dates_excluded_union": sorted(excluded),
        "feature_development_2021_2023": {
            "signals": len(feature_dev),
            "trades_per_calendar_week": len(feature_dev) / shared.span_weeks(feature_dev),
            "side_counts": dict(side_counts),
            "minority_side_share": minority,
        },
        "executable_development_overlap_2023_03_28_2023_12_31": {
            "signals": len(executable_dev),
            "trades_per_calendar_week": len(executable_dev) / shared.span_weeks(executable_dev),
            "side_counts": dict(executable_sides),
            "minority_side_share": executable_minority,
        },
        "all_overlap": {
            "signals": overlap_signals,
            "executable_signals": len(executable),
            "quote_coverage_pct": 100.0 * quote_coverage,
            "cross_ladder_5s_available_days": cross_ladder_days,
            "quote_missing": dict(quote_missing),
        },
        "by_year": by_year,
        "adjacent_cutoff_stability": stability,
        "returns_blind_control_distinctness": controls,
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
        "feature_trades_per_week": payload["feature_development_2021_2023"]["trades_per_calendar_week"],
        "executable_development_signals": len(executable_dev),
        "failed_gates": [name for name, passed in gates.items() if not passed],
        "output": str(OUTPUT.relative_to(ROOT)),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
