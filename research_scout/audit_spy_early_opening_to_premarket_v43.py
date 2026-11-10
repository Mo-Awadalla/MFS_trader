"""Returns-blind feasibility for SPY Early Opening to premarket handoff v43."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_scout import audit_spy_auction_absorption_failure_v35 as shared

ROOT = Path(__file__).resolve().parents[1]
EARLY = ROOT / "research_scout" / "spy_early_opening_snapshots_v43.json"
CORE = ROOT / "research_scout" / "spy_auction_snapshots_v34.json"
QUOTES = ROOT / "research_scout" / "upro_spxu_premarket_target_quotes_v43.json"
OUTPUT = ROOT / "research_scout" / "spy_early_opening_to_premarket_returns_blind_audit_v43.json"
PRIMARY_CUTOFF = "03:59:50"
ADJACENT_CUTOFFS = ["03:59:30", "03:59:59"]
ENTRY_TARGETS = ["07:00:01", "07:01:00", "07:05:00"]
PRIMARY_ENTRY = "07:01:00"
EXIT_TARGET = "09:20:00"
BREAK_DATE = "2025-11-13"


def weeks(start: str, end: str) -> float:
    return ((pd.Timestamp(end) - pd.Timestamp(start)).days + 1) / 7.0


def action(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None or row.get("auction_type") != "O" or row.get("projected_auction_clock") != "04:00:00":
        return None
    side = str(row.get("side"))
    if side not in {"A", "B"}:
        return None
    if float(row.get("ind_match_price") or 0) <= 0 or int(row.get("total_imbalance_qty") or 0) <= 0:
        return None
    return {
        "side": side,
        "symbol": "UPRO" if side == "B" else "SPXU",
        "signal_ts_event": row["ts_event"],
        "signal_ts_recv": row["ts_recv"],
    }


def compare(primary: dict[str, dict[str, Any]], alternative: dict[str, dict[str, Any]]) -> dict[str, Any]:
    joint = set(primary) & set(alternative)
    union = set(primary) | set(alternative)
    identical = sum((primary.get(day) or {}).get("side") == (alternative.get(day) or {}).get("side") for day in union)
    return {
        "signals": len(alternative),
        "joint_signal_days": len(joint),
        "direction_agreement_on_joint_pct": 100.0 * sum(primary[day]["side"] == alternative[day]["side"] for day in joint) / max(len(joint), 1),
        "identical_action_including_cash_pct": 100.0 * identical / max(len(union), 1),
    }


def quote_spread_bps(row: dict[str, Any]) -> float:
    midpoint = (float(row["bid"]) + float(row["ask"])) / 2.0
    return 10_000.0 * (float(row["ask"]) - float(row["bid"])) / midpoint


def ny_time(value: str) -> pd.Timestamp:
    return pd.Timestamp(value).tz_convert("America/New_York")


def main() -> int:
    early_payload = shared.load_json(EARLY)
    core_payload = shared.load_json(CORE)
    quote_payload = shared.load_json(QUOTES)
    audit = shared.load_json(shared.AUDIT)
    if any(payload.get("returns_read") is not False for payload in [early_payload, core_payload, quote_payload, audit]):
        raise RuntimeError("Returns-blind source artifact is not marked clean")

    early_by_cutoff: dict[str, dict[str, dict[str, Any]]] = {}
    for row in early_payload["snapshots"]:
        early_by_cutoff.setdefault(row["cutoff"], {})[row["session_date"]] = row
    actions_by_cutoff: dict[str, dict[str, dict[str, Any]]] = {}
    for cutoff, rows in early_by_cutoff.items():
        actions_by_cutoff[cutoff] = {
            day: candidate
            for day, row in rows.items()
            if not row["arcx_degraded"] and (candidate := action(row)) is not None
        }
    primary = actions_by_cutoff.get(PRIMARY_CUTOFF, {})

    core_sides = {
        row["session_date"]: str(row["side"])
        for row in core_payload["snapshots"]
        if row["cutoff"] == "09:29:50" and not row["arcx_degraded"] and str(row["side"]) in {"A", "B"}
    }
    quote_index = {
        (row["session_date"], row["symbol"], row["target"]): row
        for row in quote_payload["quotes"]
        if not row["equs_degraded"]
    }
    equs_degraded = set(audit["inventory"]["quality_conditions"]["EQUS.MINI"]["degraded_dates"])

    development = {day: signal for day, signal in primary.items() if "2021-01-01" <= day <= "2023-12-31"}
    feature_by_year: dict[str, Any] = {}
    for year in range(2021, 2027):
        subset = {day: signal for day, signal in primary.items() if day.startswith(str(year))}
        feature_by_year[str(year)] = {
            "signals": len(subset),
            "side_counts": dict(Counter(signal["side"] for signal in subset.values())),
        }

    overlap = {
        day: signal
        for day, signal in primary.items()
        if "2023-03-28" <= day <= "2026-07-24" and day not in equs_degraded
    }
    coverage: dict[str, Any] = {}
    for target in ENTRY_TARGETS:
        complete_days = []
        spreads = []
        for day, signal in overlap.items():
            entry = quote_index.get((day, signal["symbol"], target))
            exit_row = quote_index.get((day, signal["symbol"], EXIT_TARGET))
            if entry is not None:
                spreads.append(quote_spread_bps(entry))
            if entry is not None and exit_row is not None and ny_time(exit_row["ts_event"]).time() < pd.Timestamp("09:30:00").time():
                complete_days.append(day)
        coverage[target] = {
            "complete_entry_exit_days": len(complete_days),
            "complete_entry_exit_coverage_pct": 100.0 * len(complete_days) / max(len(overlap), 1),
            "median_entry_spread_bps": float(np.median(spreads)) if spreads else None,
            "p95_entry_spread_bps": float(np.quantile(spreads, 0.95)) if spreads else None,
        }

    executable = {}
    causal_failures = []
    for day, signal in overlap.items():
        entry = quote_index.get((day, signal["symbol"], PRIMARY_ENTRY))
        exit_row = quote_index.get((day, signal["symbol"], EXIT_TARGET))
        if entry is None or exit_row is None:
            continue
        signal_recv = pd.Timestamp(signal["signal_ts_recv"])
        entry_recv = pd.Timestamp(entry["ts_recv"])
        if signal_recv >= entry_recv or ny_time(exit_row["ts_event"]).time() >= pd.Timestamp("09:30:00").time():
            causal_failures.append(day)
            continue
        executable[day] = signal

    executable_development = {
        day: signal for day, signal in executable.items() if "2023-03-28" <= day <= "2023-12-31"
    }
    dev_weeks = weeks("2021-01-01", "2023-12-31")
    exec_dev_weeks = weeks("2023-03-28", "2023-12-31")
    dev_side_counts = Counter(signal["side"] for signal in development.values())
    exec_dev_side_counts = Counter(signal["side"] for signal in executable_development.values())

    joint_core = sorted(set(primary) & set(core_sides))
    core_agreement = 100.0 * sum(primary[day]["side"] == core_sides[day] for day in joint_core) / max(len(joint_core), 1)
    all_signal_recv_before_order = all(
        ny_time(signal["signal_ts_recv"]).time() < pd.Timestamp("07:00:01").time()
        for signal in primary.values()
    )

    primary_cov = coverage[PRIMARY_ENTRY]
    diagnostic_coverage_pass = all(coverage[target]["complete_entry_exit_coverage_pct"] >= 85.0 for target in ["07:00:01", "07:05:00"])
    spread_pass = all(
        coverage[target]["median_entry_spread_bps"] is not None
        and coverage[target]["median_entry_spread_bps"] <= 15.0
        and coverage[target]["p95_entry_spread_bps"] <= 50.0
        for target in ENTRY_TARGETS
    )
    adjacent = {cutoff: compare(primary, actions_by_cutoff.get(cutoff, {})) for cutoff in ADJACENT_CUTOFFS}

    gates = {
        "development_feature_cadence_at_least_2_per_week": len(development) / dev_weeks >= 2.0,
        "each_full_development_year_at_least_100": all(feature_by_year[str(year)]["signals"] >= 100 for year in [2021, 2022, 2023]),
        "development_minority_side_at_least_20": min(dev_side_counts.values(), default=0) >= 20,
        "executable_development_cadence_at_least_2_per_week": len(executable_development) / exec_dev_weeks >= 2.0,
        "executable_development_minority_side_at_least_20": min(exec_dev_side_counts.values(), default=0) >= 20,
        "primary_complete_entry_exit_coverage_at_least_90pct": primary_cov["complete_entry_exit_coverage_pct"] >= 90.0,
        "diagnostic_complete_entry_exit_coverage_at_least_85pct": diagnostic_coverage_pass,
        "entry_spread_median_at_most_15bps_and_p95_at_most_50bps": spread_pass,
        "adjacent_cutoff_identical_action_including_cash_at_least_80pct": all(row["identical_action_including_cash_pct"] >= 80.0 for row in adjacent.values()),
        "temporal_extension_and_postbreak_at_least_20_each": feature_by_year["2026"]["signals"] >= 20 and sum(day >= BREAK_DATE for day in primary) >= 20,
        "core_side_agreement_below_80pct": core_agreement < 80.0,
        "signal_received_before_earliest_order": all_signal_recv_before_order,
        "causal_entry_and_pre_core_exit": not causal_failures,
        "degraded_dates_excluded": not any(day in equs_degraded for day in overlap),
    }
    status = "pass_returns_blind_feasibility" if all(gates.values()) else "fail_returns_blind_no_pnl"
    payload = {
        "created_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "returns_read": False,
        "pnl_calculated": False,
        "hypothesis": "Final regular 04:00 SPY Early Opening residual side persists from 07:01 through 09:20 via UPRO/SPXU.",
        "status": status,
        "feature_development_2021_2023": {
            "signals": len(development),
            "declared_weeks": dev_weeks,
            "signals_per_declared_week": len(development) / dev_weeks,
            "side_counts": dict(dev_side_counts),
        },
        "executable_development_overlap_2023": {
            "signals": len(executable_development),
            "declared_weeks": exec_dev_weeks,
            "signals_per_declared_week": len(executable_development) / exec_dev_weeks,
            "side_counts": dict(exec_dev_side_counts),
        },
        "all_overlap": {
            "feature_signals": len(overlap),
            "primary_executable_signals": len(executable),
            "side_counts": dict(Counter(signal["side"] for signal in executable.values())),
        },
        "by_year": feature_by_year,
        "quote_coverage_and_spreads": coverage,
        "adjacent_cutoff_stability": adjacent,
        "core_side_novelty_control": {
            "joint_days": len(joint_core),
            "direction_agreement_pct": core_agreement,
        },
        "quantity_break": {
            "break_date": BREAK_DATE,
            "postbreak_signals": sum(day >= BREAK_DATE for day in primary),
            "quantity_usage": "positive-value validity check only; no level comparison",
        },
        "timestamp_observability": {
            "all_signal_receive_before_07_00_01": all_signal_recv_before_order,
            "causal_failures": causal_failures,
        },
        "gates": gates,
        "terminal_decision": "authorize_preregistration_without_return_inspection" if all(gates.values()) else "terminate_without_pnl_do_not_repair",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "status": status, "failed_gates": [name for name, passed in gates.items() if not passed]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
