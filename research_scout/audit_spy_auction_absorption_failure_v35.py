"""Returns-blind feasibility gate for SPY auction absorption-failure v35.

This script reads only pre-order auction states, quote availability/quality, and
pre-open controls. It never calculates a post-entry return or P&L.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "research_scout" / "spy_auction_snapshots_v34.json"
TARGET_QUOTES = ROOT / "research_scout" / "cash_etf_tbbo_target_quotes_v34.json"
AUDIT = ROOT / "research_scout" / "new_data_technical_audit_v34.json"
OUTPUT = ROOT / "research_scout" / "spy_auction_absorption_failure_returns_blind_audit_v35.json"
OLD_SPY = ROOT / "external_artifacts" / "databento_fractional_etf" / "ARCX.PILLAR" / "bars" / "spy_sh_ohlcv_1m_2021-01-01_2026-01-01.dbn.zst"
NEW_SPY = ROOT / "external_artifacts" / "databento_forward_2026" / "ARCX.PILLAR" / "bars" / "spy_upro_spxu_ohlcv_1m_2026-01-02_2026-07-25.dbn.zst"
ENTRY_TARGETS = {1: "09:30:01", 5: "09:30:05", 60: "09:31:00"}
EXIT_TARGET = "09:35:00"
EARLY = "09:28:00"
LATE = "09:29:50"
ADJACENT_LATES = ["09:29:30", "09:29:59"]
SYMBOLS = ["SPY", "SSO", "UPRO", "SH", "SDS", "SPXU"]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_map(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(row["session_date"], row["cutoff"]): row for row in payload["snapshots"]}


def action(early: dict[str, Any] | None, late: dict[str, Any] | None) -> dict[str, Any] | None:
    if early is None or late is None:
        return None
    if early["side"] not in {"A", "B"} or early["side"] != late["side"]:
        return None
    required = [
        early.get("paired_qty"), early.get("total_imbalance_qty"), early.get("ref_price"), early.get("ind_match_price"),
        late.get("paired_qty"), late.get("total_imbalance_qty"), late.get("ref_price"), late.get("ind_match_price"),
    ]
    if any(value is None or float(value) <= 0 for value in required):
        return None
    early_share = float(early["total_imbalance_qty"]) / (float(early["paired_qty"]) + float(early["total_imbalance_qty"]))
    late_share = float(late["total_imbalance_qty"]) / (float(late["paired_qty"]) + float(late["total_imbalance_qty"]))
    sign = 1.0 if late["side"] == "B" else -1.0
    early_displacement = sign * (float(early["ind_match_price"]) / float(early["ref_price"]) - 1.0)
    late_displacement = sign * (float(late["ind_match_price"]) / float(late["ref_price"]) - 1.0)
    triggered = late_share > early_share and late_displacement > early_displacement and late_displacement > 0
    if not triggered:
        return None
    return {
        "side": late["side"],
        "symbol": "UPRO" if late["side"] == "B" else "SPXU",
        "early_pressure_share": early_share,
        "late_pressure_share": late_share,
        "early_signed_displacement": early_displacement,
        "late_signed_displacement": late_displacement,
        "early_ref_price": float(early["ref_price"]),
        "late_ref_price": float(late["ref_price"]),
        "early_paired_qty": int(early["paired_qty"]),
        "late_paired_qty": int(late["paired_qty"]),
        "late_total_imbalance_qty": int(late["total_imbalance_qty"]),
        "signal_ts_event": late["ts_event"],
    }


def previous_close_map() -> dict[str, float]:
    frames = [base.load_dbn(OLD_SPY, "SPY"), base.load_dbn(NEW_SPY, "SPY")]
    combined = pd.concat(frames).sort_index()
    sessions = base.split_sessions(combined)
    closes: dict[str, float] = {}
    prior: float | None = None
    for day, frame in sorted(sessions.items()):
        key = pd.Timestamp(day).strftime("%Y-%m-%d")
        if prior is not None:
            closes[key] = prior
        rth = frame.between_time("09:30", "15:59")
        if not rth.empty:
            value = float(rth.iloc[-1].close)
            if value > 0:
                prior = value
    return closes


def quote_map(payload: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {(row["session_date"], row["symbol"], row["target"]): row for row in payload["quotes"]}


def span_weeks(dates: list[str]) -> float:
    if not dates:
        return 1.0
    parsed = pd.to_datetime(dates)
    return max((parsed.max() - parsed.min()).days / 7.0, 1.0)


def main() -> int:
    snapshot_payload = load_json(SNAPSHOTS)
    quote_payload = load_json(TARGET_QUOTES)
    audit = load_json(AUDIT)
    if snapshot_payload.get("returns_read") is not False or quote_payload.get("returns_read") is not False or audit.get("returns_read") is not False:
        raise RuntimeError("Returns-blind source artifact is not marked clean")
    snapshots = snapshot_map(snapshot_payload)
    quotes = quote_map(quote_payload)
    prior_closes = previous_close_map()
    excluded = set(audit["degraded_dates"]["ARCX.PILLAR"]) | set(audit["degraded_dates"]["EQUS.MINI"])
    days = sorted({day for day, cutoff in snapshots if cutoff == LATE})
    signals: dict[str, dict[str, Any]] = {}
    for day in days:
        if day in excluded:
            continue
        value = action(snapshots.get((day, EARLY)), snapshots.get((day, LATE)))
        if value is None:
            continue
        close = prior_closes.get(day)
        value["opening_gap"] = value["early_ref_price"] / close - 1.0 if close else None
        value["recent_reference_return"] = value["late_ref_price"] / value["early_ref_price"] - 1.0
        value["paired_qty_change"] = value["late_paired_qty"] / value["early_paired_qty"] - 1.0
        signals[day] = value
    adjacent: dict[str, dict[str, dict[str, Any]]] = {}
    for cutoff in ADJACENT_LATES:
        adjacent[cutoff] = {}
        for day in days:
            if day in excluded:
                continue
            value = action(snapshots.get((day, EARLY)), snapshots.get((day, cutoff)))
            if value is not None:
                adjacent[cutoff][day] = value
    executable: dict[str, dict[str, Any]] = {}
    quote_missing: Counter[str] = Counter()
    cross_ladder_days = 0
    for day, signal in signals.items():
        if day < "2023-03-28" or day > "2026-07-24":
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
        five_second = row["quotes"][ENTRY_TARGETS[5]]
        row["entry_spread_bps"] = (five_second["ask"] - five_second["bid"]) / ((five_second["ask"] + five_second["bid"]) / 2.0) * 10_000.0
        executable[day] = row
        if all((day, symbol_name, ENTRY_TARGETS[5]) in quotes for symbol_name in SYMBOLS):
            cross_ladder_days += 1
    feature_dev_days = [day for day in signals if "2021-01-01" <= day <= "2023-12-31"]
    executable_dev_days = [day for day in executable if "2023-03-28" <= day <= "2023-12-31"]
    side_counts = Counter(signals[day]["side"] for day in feature_dev_days)
    executable_side_counts = Counter(executable[day]["side"] for day in executable_dev_days)
    minority_share = min(side_counts.values()) / max(sum(side_counts.values()), 1) if len(side_counts) == 2 else 0.0
    executable_minority_share = min(executable_side_counts.values()) / max(sum(executable_side_counts.values()), 1) if len(executable_side_counts) == 2 else 0.0
    stability: dict[str, Any] = {}
    for cutoff, mapping in adjacent.items():
        joint = sorted(set(signals) & set(mapping))
        agreement = sum(signals[day]["side"] == mapping[day]["side"] for day in joint)
        union = sorted(set(signals) | set(mapping))
        same_action = sum(
            (signals.get(day) or {}).get("side") == (mapping.get(day) or {}).get("side")
            for day in union
        )
        stability[cutoff] = {
            "joint_signal_days": len(joint),
            "direction_agreement_on_joint_pct": 100.0 * agreement / max(len(joint), 1),
            "identical_action_including_cash_pct": 100.0 * same_action / max(len(union), 1),
            "signals": len(mapping),
        }
    controls = {
        "opening_gap_same_direction_pct": 100.0 * sum(
            signal["opening_gap"] is not None
            and ((signal["opening_gap"] > 0 and signal["side"] == "B") or (signal["opening_gap"] < 0 and signal["side"] == "A"))
            for signal in signals.values()
        ) / max(sum(signal["opening_gap"] is not None and signal["opening_gap"] != 0 for signal in signals.values()), 1),
        "recent_reference_momentum_same_direction_pct": 100.0 * sum(
            (signal["recent_reference_return"] > 0 and signal["side"] == "B")
            or (signal["recent_reference_return"] < 0 and signal["side"] == "A")
            for signal in signals.values()
        ) / max(sum(signal["recent_reference_return"] != 0 for signal in signals.values()), 1),
        "paired_quantity_declined_pct": 100.0 * sum(signal["paired_qty_change"] < 0 for signal in signals.values()) / max(len(signals), 1),
    }
    quote_coverage = len(executable) / max(sum(day >= "2023-03-28" for day in signals), 1)
    by_year = {
        str(year): {
            "signals": sum(day.startswith(str(year)) for day in signals),
            "executable_signals": sum(day.startswith(str(year)) for day in executable),
            "side_counts": dict(Counter(signal["side"] for day, signal in signals.items() if day.startswith(str(year)))),
        }
        for year in range(2021, 2027)
    }
    gates = {
        "feature_frequency_at_least_two_per_week_2021_2023": len(feature_dev_days) / span_weeks(feature_dev_days) >= 2.0,
        "executable_frequency_at_least_two_per_week_2023_overlap": len(executable_dev_days) / span_weeks(executable_dev_days) >= 2.0,
        "prefer_100_feature_signals_each_full_development_year": all(by_year[str(year)]["signals"] >= 100 for year in [2021, 2022, 2023]),
        "minority_feature_side_at_least_20pct": minority_share >= 0.20,
        "minority_executable_side_at_least_20pct": executable_minority_share >= 0.20,
        "upro_and_spxu_each_present_in_executable_development": len(executable_side_counts) == 2 and all(value > 0 for value in executable_side_counts.values()),
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
            "early_cutoff": EARLY,
            "late_cutoff": LATE,
            "conditions": "same side; pressure share rises; side-signed indicative displacement rises and ends positive",
            "actuator": "B->UPRO, A->SPXU",
            "entry_targets": ENTRY_TARGETS,
            "exit_target": EXIT_TARGET,
            "maximum_event_wait_seconds": 60,
        },
        "degraded_dates_excluded_union": sorted(excluded),
        "feature_development_2021_2023": {
            "signals": len(feature_dev_days),
            "trades_per_calendar_week": len(feature_dev_days) / span_weeks(feature_dev_days),
            "side_counts": dict(side_counts),
            "minority_side_share": minority_share,
        },
        "executable_development_overlap_2023_03_28_2023_12_31": {
            "signals": len(executable_dev_days),
            "trades_per_calendar_week": len(executable_dev_days) / span_weeks(executable_dev_days),
            "side_counts": dict(executable_side_counts),
            "minority_side_share": executable_minority_share,
        },
        "all_overlap": {
            "signals": sum(day >= "2023-03-28" for day in signals),
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
        "feature_signals": len(feature_dev_days),
        "feature_trades_per_week": payload["feature_development_2021_2023"]["trades_per_calendar_week"],
        "executable_development_signals": len(executable_dev_days),
        "failed_gates": [name for name, passed in gates.items() if not passed],
        "output": str(OUTPUT.relative_to(ROOT)),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
