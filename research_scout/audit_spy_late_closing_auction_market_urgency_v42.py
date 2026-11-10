"""Returns-blind feasibility for late Closing-auction market urgency v42."""

from __future__ import annotations

import calendar
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_spy_auction_absorption_failure_v35 as shared

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "research_scout" / "spy_late_closing_auction_snapshots_v42.json"
QUOTES = ROOT / "research_scout" / "spy_sh_late_closing_target_quotes_v42.json"
OUTPUT = ROOT / "research_scout" / "spy_late_closing_auction_market_urgency_returns_blind_audit_v42.json"
PRIMARY = ("15:50:00", "15:55:00")
ADJACENT = [("15:49:50", "15:54:50"), ("15:50:10", "15:55:10")]
ENTRY_TARGETS = ["15:55:01", "15:55:05", "15:56:00"]
PRIMARY_ENTRY = "15:56:00"
EXIT_TARGET = "15:59:00"
BREAK_DATE = "2025-11-13"


def weeks(start: str, end: str) -> float:
    return ((pd.Timestamp(end) - pd.Timestamp(start)).days + 1) / 7.0


def regular_close(row: dict[str, Any] | None) -> bool:
    if row is None or row.get("auction_type") != "C" or not row.get("auction_time"):
        return False
    return pd.Timestamp(row["auction_time"]).time() == pd.Timestamp("16:00:00").time()


def baseline_eligible(early: dict[str, Any] | None, late: dict[str, Any] | None) -> bool:
    if not regular_close(early) or not regular_close(late):
        return False
    assert early is not None and late is not None
    if early.get("side") not in {"A", "B"} or early.get("side") != late.get("side"):
        return False
    return float(early.get("market_imbalance_qty") or 0) > 0 and float(late.get("market_imbalance_qty") or 0) > 0


def action(early: dict[str, Any] | None, late: dict[str, Any] | None) -> dict[str, Any] | None:
    if not baseline_eligible(early, late):
        return None
    assert early is not None and late is not None
    early_qty = int(early["market_imbalance_qty"])
    late_qty = int(late["market_imbalance_qty"])
    if late_qty <= early_qty:
        return None
    side = str(late["side"])
    return {
        "side": side,
        "symbol": "SPY" if side == "B" else "SH",
        "early_market_imbalance_qty": early_qty,
        "late_market_imbalance_qty": late_qty,
        "growth_qty": late_qty - early_qty,
        "late_total_imbalance_qty": int(late["total_imbalance_qty"]),
        "signal_ts_event": late["ts_event"],
        "signal_ts_recv": late["ts_recv"],
    }


def compare(primary: dict[str, dict[str, Any]], alternative: dict[str, dict[str, Any]]) -> dict[str, Any]:
    joint = set(primary) & set(alternative)
    union = set(primary) | set(alternative)
    return {
        "signals": len(alternative),
        "joint_signal_days": len(joint),
        "direction_agreement_on_joint_pct": 100.0 * sum(primary[d]["side"] == alternative[d]["side"] for d in joint) / max(len(joint), 1),
        "identical_action_including_cash_pct": 100.0 * sum((primary.get(d) or {}).get("side") == (alternative.get(d) or {}).get("side") for d in union) / max(len(union), 1),
    }


def before_clock(value: str, clock: str) -> bool:
    return pd.Timestamp(value).tz_convert("America/New_York").time() < pd.Timestamp(clock).time()


def calendar_flags(days: list[str]) -> set[str]:
    ordered = sorted(days)
    last_of_month = {
        day for index, day in enumerate(ordered)
        if index == len(ordered) - 1 or pd.Timestamp(ordered[index + 1]).month != pd.Timestamp(day).month
    }
    third_fridays = {
        day for day in ordered
        if pd.Timestamp(day).weekday() == calendar.FRIDAY and 15 <= pd.Timestamp(day).day <= 21
    }
    return last_of_month | third_fridays


def main() -> int:
    snapshot_payload = shared.load_json(SNAPSHOTS)
    quote_payload = shared.load_json(QUOTES)
    audit = shared.load_json(shared.AUDIT)
    if any(payload.get("returns_read") is not False for payload in [snapshot_payload, quote_payload, audit]):
        raise RuntimeError("Returns-blind source artifact is not marked clean")
    if not quote_payload.get("prefix_boundary_seen_and_stopped"):
        raise RuntimeError("Unsafe partial-prefix consumption")
    snapshots = shared.snapshot_map(snapshot_payload)
    quotes = shared.quote_map(quote_payload)
    excluded = set(audit["degraded_dates"]["ARCX.PILLAR"]) | set(audit["degraded_dates"]["EQUS.MINI"])
    all_days = sorted({day for day, cutoff in snapshots if cutoff == PRIMARY[1]})

    signals: dict[str, dict[str, Any]] = {}
    baseline_days = 0
    for day in all_days:
        if day in excluded:
            continue
        early = snapshots.get((day, PRIMARY[0]))
        late = snapshots.get((day, PRIMARY[1]))
        baseline_days += int(baseline_eligible(early, late))
        value = action(early, late)
        if value is not None:
            signals[day] = value

    alternatives: dict[str, dict[str, dict[str, Any]]] = {}
    for early_cutoff, late_cutoff in ADJACENT:
        mapping: dict[str, dict[str, Any]] = {}
        for day in all_days:
            if day in excluded:
                continue
            value = action(snapshots.get((day, early_cutoff)), snapshots.get((day, late_cutoff)))
            if value is not None:
                mapping[day] = value
        alternatives[f"{early_cutoff}_{late_cutoff}"] = mapping

    overlap_signals = {day: signal for day, signal in signals.items() if "2023-03-28" <= day <= "2026-07-24"}
    executable: dict[str, dict[str, Any]] = {}
    missing: Counter[str] = Counter()
    entry_after_signal = True
    exits_before_close = True
    for day, signal in overlap_signals.items():
        symbol = signal["symbol"]
        keys = [(day, symbol, target) for target in ENTRY_TARGETS + [EXIT_TARGET]]
        if not all(key in quotes for key in keys):
            for key in keys:
                if key not in quotes:
                    missing[f"{symbol}:{key[2]}"] += 1
            continue
        selected = {target: quotes[(day, symbol, target)] for target in ENTRY_TARGETS + [EXIT_TARGET]}
        signal_recv = pd.Timestamp(signal["signal_ts_recv"])
        if any(pd.Timestamp(selected[target]["ts_recv"]) <= signal_recv for target in ENTRY_TARGETS):
            entry_after_signal = False
            continue
        if not before_clock(selected[EXIT_TARGET]["ts_event"], "16:00:00") or not before_clock(selected[EXIT_TARGET]["ts_recv"], "16:00:00"):
            continue
        row = dict(signal)
        row["quote_observations"] = selected
        executable[day] = row
    exits_before_close = all(
        before_clock(row["quote_observations"][EXIT_TARGET]["ts_event"], "16:00:00")
        and before_clock(row["quote_observations"][EXIT_TARGET]["ts_recv"], "16:00:00")
        for row in executable.values()
    )

    momentum_available = 0
    momentum_agree = 0
    momentum_details: dict[str, Any] = {}
    for day, signal in signals.items():
        keys = [(day, "SPY", "15:50:00"), (day, "SPY", "15:54:50")]
        if not all(key in quotes for key in keys):
            continue
        first, second = (quotes[key] for key in keys)
        if not before_clock(second["ts_event"], "15:55:00") or not before_clock(second["ts_recv"], "15:55:00"):
            continue
        first_mid = (first["bid"] + first["ask"]) / 2.0
        second_mid = (second["bid"] + second["ask"]) / 2.0
        change = second_mid - first_mid
        if change == 0:
            continue
        momentum_available += 1
        agrees = (change > 0 and signal["side"] == "B") or (change < 0 and signal["side"] == "A")
        momentum_agree += int(agrees)
        momentum_details[day] = {"mid_change": change, "agrees": agrees}

    feature_dev = [day for day in signals if "2021-01-01" <= day <= "2023-12-31"]
    executable_dev = [day for day in executable if "2023-03-28" <= day <= "2023-12-31"]
    feature_sides = Counter(signals[day]["side"] for day in feature_dev)
    executable_sides = Counter(executable[day]["side"] for day in executable_dev)
    minority_feature = min(feature_sides.values()) / max(sum(feature_sides.values()), 1) if len(feature_sides) == 2 else 0.0
    minority_exec = min(executable_sides.values()) / max(sum(executable_sides.values()), 1) if len(executable_sides) == 2 else 0.0
    by_year = {
        str(year): {
            "signals": sum(day.startswith(str(year)) for day in signals),
            "signals_per_declared_week": sum(day.startswith(str(year)) for day in signals) / weeks(f"{year}-01-01", f"{year}-12-31" if year < 2026 else "2026-07-24"),
            "side_counts": dict(Counter(signal["side"] for day, signal in signals.items() if day.startswith(str(year)))),
        }
        for year in range(2021, 2027)
    }
    quote_coverage = len(executable) / max(len(overlap_signals), 1)
    stability = {name: compare(signals, mapping) for name, mapping in alternatives.items()}
    post_break = [day for day in signals if day >= BREAK_DATE]
    post_break_sides = Counter(signals[day]["side"] for day in post_break)
    selected_share = len(signals) / max(baseline_days, 1)
    concentration_days = calendar_flags(all_days)
    concentrated = [day for day in signals if day in concentration_days]
    concentration_share = len(concentrated) / max(len(signals), 1)
    cutoff_clean = all(before_clock(signal["signal_ts_event"], "15:55:00") and before_clock(signal["signal_ts_recv"], "15:55:00") for signal in signals.values())
    momentum_coverage = momentum_available / max(len(signals), 1)
    momentum_agreement = momentum_agree / max(momentum_available, 1)

    gates = {
        "at_least_two_feature_signals_per_week_overall_and_each_full_development_year": len(feature_dev) / weeks("2021-01-01", "2023-12-31") >= 2.0 and all(by_year[str(year)]["signals_per_declared_week"] >= 2.0 for year in [2021, 2022, 2023]),
        "at_least_two_executable_primary_signals_per_week_2023_overlap": len(executable_dev) / weeks("2023-03-28", "2023-12-31") >= 2.0,
        "at_least_100_feature_signals_each_development_year": all(by_year[str(year)]["signals"] >= 100 for year in [2021, 2022, 2023]),
        "at_least_20_feature_signals_2026": by_year["2026"]["signals"] >= 20,
        "minority_side_at_least_20pct_feature_and_executable_development_and_both_actuators": minority_feature >= 0.20 and minority_exec >= 0.20 and len(executable_sides) == 2,
        "all_delay_plus_preclose_exit_quote_coverage_at_least_90pct": quote_coverage >= 0.90,
        "shifted_window_minus_10s_identical_action_at_least_60pct": stability["15:49:50_15:54:50"]["identical_action_including_cash_pct"] >= 60.0,
        "shifted_window_plus_10s_identical_action_at_least_60pct": stability["15:50:10_15:55:10"]["identical_action_including_cash_pct"] >= 60.0,
        "at_least_20_postbreak_signals_with_both_directions": len(post_break) >= 20 and len(post_break_sides) == 2,
        "presignal_spy_momentum_coverage_at_least_80pct_and_agreement_below_80pct": momentum_coverage >= 0.80 and momentum_agreement < 0.80,
        "growth_condition_selects_no_more_than_80pct_baseline_days": selected_share <= 0.80,
        "signals_select_between_10_and_80pct_baseline_days": 0.10 <= selected_share <= 0.80,
        "monthend_or_third_friday_concentration_no_more_than_25pct": concentration_share <= 0.25,
        "signal_before_cutoff_entries_after_receipt_exits_before_close": cutoff_clean and entry_after_signal and exits_before_close,
        "tbbo_prefix_tail_dedup_and_fixed_degraded_dates": quote_payload["prefix_boundary_seen_and_stopped"] and bool(excluded),
    }

    payload = {
        "status": "passed_returns_blind_feasibility" if all(gates.values()) else "failed_returns_blind_feasibility_no_pnl_opened",
        "returns_read": False,
        "rule": {
            "auction_type": "C", "early_cutoff": PRIMARY[0], "late_cutoff": PRIMARY[1],
            "condition": "same regular-close side; positive market imbalance at both snapshots; late quantity strictly larger",
            "actuator": "B -> SPY; A -> SH", "entry_targets": ENTRY_TARGETS,
            "primary_entry": PRIMARY_ENTRY, "exit_target": EXIT_TARGET, "flat_before_16_00": True,
        },
        "chronology": "Independent recommendation dispatched before V41 feasibility was read; no V37-V41 P&L existed.",
        "degraded_dates_excluded_union": sorted(excluded),
        "feature_development_2021_2023": {"signals": len(feature_dev), "signals_per_declared_week": len(feature_dev) / weeks("2021-01-01", "2023-12-31"), "side_counts": dict(feature_sides), "minority_share": minority_feature},
        "executable_development_2023_overlap": {"signals": len(executable_dev), "signals_per_declared_week": len(executable_dev) / weeks("2023-03-28", "2023-12-31"), "side_counts": dict(executable_sides), "minority_share": minority_exec},
        "all_overlap": {"feature_signals": len(overlap_signals), "executable_signals": len(executable), "complete_quote_coverage_pct": 100.0 * quote_coverage, "missing": dict(missing)},
        "by_year": by_year,
        "adjacent_window_stability": stability,
        "quantity_break": {"postbreak_signals": len(post_break), "side_counts": dict(post_break_sides)},
        "returns_blind_controls": {
            "baseline_eligible_days": baseline_days, "selected_signal_days": len(signals), "selection_share_pct": 100.0 * selected_share,
            "presignal_spy_momentum_available": momentum_available, "presignal_spy_momentum_coverage_pct": 100.0 * momentum_coverage,
            "presignal_spy_momentum_direction_agreement_pct": 100.0 * momentum_agreement,
            "monthend_or_third_friday_signals": len(concentrated), "calendar_concentration_pct": 100.0 * concentration_share,
        },
        "timestamp_observability": {"signals_before_cutoff": cutoff_clean, "entries_after_signal": entry_after_signal, "retained_exits_before_close": exits_before_close},
        "gates": gates,
        "gate_passed": all(gates.values()),
        "signals": signals,
        "executable_signal_dates": sorted(executable),
        "warning": "No post-entry return, P&L, benchmark, profit factor, or placebo was calculated.",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "feature_development": len(feature_dev), "executable_development": len(executable_dev), "failed_gates": [name for name, value in gates.items() if not value], "output": str(OUTPUT.relative_to(ROOT))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
