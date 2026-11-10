"""Returns-blind feasibility gate for SPY late market-order urgency v39."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_spy_auction_absorption_failure_v35 as shared

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "spy_late_market_order_urgency_returns_blind_audit_v39.json"
EARLY = "09:28:00"
LATE = "09:29:50"
ADJACENT = ["09:29:30", "09:29:59"]
PRIMARY_ENTRY = "09:30:05"
DELAY_TARGETS = ["09:30:01", "09:31:00"]
EXIT_TARGET = "09:35:00"
POSITIVE_LADDER = ["SPY", "SSO", "UPRO"]
NEGATIVE_LADDER = ["SH", "SDS", "SPXU"]
BREAK_DATE = "2025-11-13"


def declared_weeks(start: str, end: str) -> float:
    return ((pd.Timestamp(end) - pd.Timestamp(start)).days + 1) / 7.0


def eligible_stable_side(early: dict[str, Any] | None, late: dict[str, Any] | None) -> bool:
    if early is None or late is None or early.get("side") not in {"A", "B"} or early.get("side") != late.get("side"):
        return False
    required = [early.get("total_imbalance_qty"), late.get("total_imbalance_qty")]
    market = [early.get("market_imbalance_qty"), late.get("market_imbalance_qty")]
    return not any(value is None or float(value) <= 0 for value in required) and not any(value is None or float(value) < 0 for value in market)


def action(early: dict[str, Any] | None, late: dict[str, Any] | None) -> dict[str, Any] | None:
    if not eligible_stable_side(early, late):
        return None
    assert early is not None and late is not None
    early_market = float(early["market_imbalance_qty"])
    late_market = float(late["market_imbalance_qty"])
    early_total = float(early["total_imbalance_qty"])
    late_total = float(late["total_imbalance_qty"])
    early_share = early_market / early_total
    late_share = late_market / late_total
    if late_market <= 0 or late_share <= early_share:
        return None
    side = str(late["side"])
    reference_return = float(late["ref_price"]) / float(early["ref_price"]) - 1.0 if min(float(early["ref_price"]), float(late["ref_price"])) > 0 else None
    indicative_return = float(late["ind_match_price"]) / float(early["ind_match_price"]) - 1.0 if min(float(early["ind_match_price"]), float(late["ind_match_price"])) > 0 else None
    return {
        "side": side,
        "symbol": "UPRO" if side == "B" else "SPXU",
        "early_market_imbalance_qty": int(early_market),
        "late_market_imbalance_qty": int(late_market),
        "early_total_imbalance_qty": int(early_total),
        "late_total_imbalance_qty": int(late_total),
        "early_market_share": early_share,
        "late_market_share": late_share,
        "reference_return": reference_return,
        "indicative_return": indicative_return,
        "signal_ts_event": late["ts_event"],
        "signal_ts_recv": late["ts_recv"],
    }


def compare_actions(primary: dict[str, dict[str, Any]], alternative: dict[str, dict[str, Any]]) -> dict[str, Any]:
    joint = set(primary) & set(alternative)
    union = set(primary) | set(alternative)
    return {
        "signals": len(alternative),
        "joint_signal_days": len(joint),
        "direction_agreement_on_joint_pct": 100.0 * sum(primary[day]["side"] == alternative[day]["side"] for day in joint) / max(len(joint), 1),
        "identical_action_including_cash_pct": 100.0 * sum((primary.get(day) or {}).get("side") == (alternative.get(day) or {}).get("side") for day in union) / max(len(union), 1),
    }


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
    stable_side_days = 0
    for day in days:
        if day in excluded:
            continue
        early = snapshots.get((day, EARLY))
        late = snapshots.get((day, LATE))
        stable_side_days += int(eligible_stable_side(early, late))
        value = action(early, late)
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
    delay_available: Counter[str] = Counter()
    relevant_ladder_days = 0
    relevant_ladder_missing: Counter[str] = Counter()
    for day, signal in signals.items():
        if not "2023-03-28" <= day <= "2026-07-24":
            continue
        symbol = signal["symbol"]
        required = [(day, symbol, PRIMARY_ENTRY), (day, symbol, EXIT_TARGET)]
        if not all(key in quotes and not quotes[key]["equs_degraded"] for key in required):
            for key in required:
                if key not in quotes:
                    quote_missing[f"{symbol}:{key[2]}"] += 1
            continue
        row = dict(signal)
        row["quotes"] = {target: quotes[(day, symbol, target)] for target in [PRIMARY_ENTRY, EXIT_TARGET]}
        primary = row["quotes"][PRIMARY_ENTRY]
        row["entry_spread_bps"] = (primary["ask"] - primary["bid"]) / ((primary["ask"] + primary["bid"]) / 2.0) * 10_000.0
        executable[day] = row
        for target in DELAY_TARGETS:
            if (day, symbol, target) in quotes:
                delay_available[target] += 1
        ladder = POSITIVE_LADDER if signal["side"] == "B" else NEGATIVE_LADDER
        ladder_keys = [(day, ladder_symbol, PRIMARY_ENTRY) for ladder_symbol in ladder]
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

    stability = {cutoff: compare_actions(signals, mapping) for cutoff, mapping in adjacent.items()}
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
    selection_share = len(signals) / max(stable_side_days, 1)
    post_break_signals = sum(day >= BREAK_DATE for day in signals)
    cutoff = pd.Timestamp("09:29:50").time()
    order = pd.Timestamp(PRIMARY_ENTRY).time()
    timestamp_clean = all(
        pd.Timestamp(signal["signal_ts_event"]).tz_convert("America/New_York").time() < cutoff
        and pd.Timestamp(signal["signal_ts_recv"]).tz_convert("America/New_York").time() < cutoff
        and pd.Timestamp(signal["signal_ts_recv"]).tz_convert("America/New_York").time() < order
        for signal in signals.values()
    )

    gates = {
        "feature_frequency_at_least_two_per_declared_week_2021_2023": len(feature_dev) / declared_weeks("2021-01-01", "2023-12-31") >= 2.0,
        "executable_frequency_at_least_two_per_declared_week_2023_overlap": len(executable_dev) / declared_weeks("2023-03-28", "2023-12-31") >= 2.0,
        "at_least_100_feature_signals_each_development_year": all(by_year[str(year)]["signals"] >= 100 for year in [2021, 2022, 2023]),
        "at_least_20_feature_signals_2026_extension": by_year["2026"]["signals"] >= 20,
        "minority_side_at_least_20pct_feature_and_executable_development": minority_feature >= 0.20 and minority_executable >= 0.20,
        "upro_and_spxu_each_executable_in_development": len(executable_sides) == 2 and all(value > 0 for value in executable_sides.values()),
        "primary_entry_exit_quote_coverage_at_least_90pct": quote_coverage >= 0.90,
        "relevant_side_ladder_09_30_05_availability_at_least_80pct": ladder_coverage >= 0.80,
        "adjacent_09_29_30_identical_action_at_least_60pct": stability["09:29:30"]["identical_action_including_cash_pct"] >= 60.0,
        "adjacent_09_29_59_identical_action_at_least_60pct": stability["09:29:59"]["identical_action_including_cash_pct"] >= 60.0,
        "market_order_condition_selects_between_10_and_80pct_stable_side_days": 0.10 <= selection_share <= 0.80,
        "at_least_20_signals_after_quantity_definition_break": post_break_signals >= 20,
        "ts_event_and_ts_recv_before_cutoff_and_primary_order": timestamp_clean,
    }

    payload = {
        "status": "passed_returns_blind_feasibility" if all(gates.values()) else "failed_returns_blind_feasibility_no_pnl_opened",
        "returns_read": False,
        "rule": {
            "early_cutoff": EARLY,
            "late_cutoff": LATE,
            "condition": "stable A/B side; late market imbalance positive; market/total imbalance share rises",
            "direction": "stable published imbalance side",
            "actuator": "B -> UPRO; A -> SPXU",
            "primary_entry_target": PRIMARY_ENTRY,
            "delay_diagnostics": DELAY_TARGETS,
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
            "primary_quote_coverage_pct": 100.0 * quote_coverage,
            "relevant_side_ladder_available_days": relevant_ladder_days,
            "relevant_side_ladder_coverage_pct": 100.0 * ladder_coverage,
            "delay_target_available_counts": dict(delay_available),
            "quote_missing": dict(quote_missing),
            "relevant_ladder_missing": dict(relevant_ladder_missing),
        },
        "market_order_condition": {
            "eligible_stable_side_days": stable_side_days,
            "selected_signal_days": len(signals),
            "selection_share_pct": 100.0 * selection_share,
            "post_2025_11_13_break_signals": post_break_signals,
        },
        "by_year": by_year,
        "adjacent_cutoff_stability": stability,
        "timestamp_observability": {"all_signal_event_and_receive_times_before_cutoff_and_primary_order": timestamp_clean},
        "gates": gates,
        "gate_passed": all(gates.values()),
        "signals": signals,
        "executable_signal_dates": sorted(executable),
        "warning": "No post-entry bid, return, P&L, profit factor, benchmark, or placebo outcome was calculated.",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "feature_signals": len(feature_dev),
        "feature_trades_per_week": payload["feature_development_2021_2023"]["trades_per_declared_calendar_week"],
        "executable_development_signals": len(executable_dev),
        "failed_gates": [name for name, passed in gates.items() if not passed],
        "output": str(OUTPUT.relative_to(ROOT)),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
