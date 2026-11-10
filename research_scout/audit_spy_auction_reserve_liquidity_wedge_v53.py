"""Returns-blind feasibility for SPY auction reserve-liquidity wedge v53."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_scout import audit_spy_auction_absorption_failure_v35 as shared
from research_scout import audit_leveraged_etf_official_open_basis_v48 as v48

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "spy_auction_reserve_liquidity_wedge_returns_blind_audit_v53.json"
PRIMARY = ("09:29:00", "09:29:50")
VARIANTS = {
    "early_start": ("09:28:00", "09:29:50"),
    "late_end": ("09:29:00", "09:29:59"),
}
ENTRY_TARGETS = ["09:30:01", "09:30:05", "09:31:00"]
PRIMARY_ENTRY = "09:30:05"
EXIT_TARGET = "09:35:00"
MAX_EVENT_WAIT = 60.0


def declared_weeks(start: str, end: str) -> float:
    return ((pd.Timestamp(end) - pd.Timestamp(start)).days + 1) / 7.0


def snapshot_maps(payload: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for row in payload["snapshots"]:
        result.setdefault(str(row["cutoff"]), {})[str(row["session_date"])] = row
    return result


def wedge(row: dict[str, Any]) -> float | None:
    indicative = float(row["ind_match_price"])
    auction_only = float(row["auct_interest_clr_price"])
    if indicative <= 0 or auction_only <= 0:
        return None
    return indicative - auction_only


def build_actions(
    maps: dict[str, dict[str, dict[str, Any]]],
    excluded: set[str],
    clocks: tuple[str, str],
) -> tuple[dict[str, dict[str, Any]], int]:
    early_map = maps[clocks[0]]
    late_map = maps[clocks[1]]
    actions: dict[str, dict[str, Any]] = {}
    valid = 0
    for day in sorted(set(early_map) & set(late_map)):
        if day in excluded:
            continue
        early = early_map[day]
        late = late_map[day]
        early_wedge = wedge(early)
        late_wedge = wedge(late)
        if early_wedge in {None, 0} or late_wedge in {None, 0}:
            continue
        valid += 1
        same_sign = (early_wedge > 0) == (late_wedge > 0)
        widening = abs(late_wedge) > abs(early_wedge)
        if not (same_sign and widening):
            continue
        side = "B" if late_wedge > 0 else "A"
        actions[day] = {
            "side": side,
            "symbol": "UPRO" if side == "B" else "SPXU",
            "early_cutoff": clocks[0],
            "late_cutoff": clocks[1],
            "early_wedge": early_wedge,
            "late_wedge": late_wedge,
            "wedge_growth": abs(late_wedge) - abs(early_wedge),
            "late_opening_side": late["side"],
            "late_reference_displacement": float(late["ind_match_price"])
            - float(late["ref_price"]),
            "recent_indicative_move": float(late["ind_match_price"])
            - float(early["ind_match_price"]),
            "signal_ts_event": late["ts_event"],
            "signal_ts_recv": late["ts_recv"],
        }
    return actions, valid


def compare(primary: dict[str, dict[str, Any]], alternative: dict[str, dict[str, Any]]) -> dict[str, Any]:
    joint = set(primary) & set(alternative)
    union = set(primary) | set(alternative)
    return {
        "signals": len(alternative),
        "joint": len(joint),
        "direction_agreement_on_joint_pct": 100.0
        * sum(primary[day]["side"] == alternative[day]["side"] for day in joint)
        / max(len(joint), 1),
        "identical_action_including_cash_pct": 100.0
        * sum((primary.get(day) or {}).get("side") == (alternative.get(day) or {}).get("side") for day in union)
        / max(len(union), 1),
    }


def agreement_with_signed_value(
    actions: dict[str, dict[str, Any]], key: str
) -> tuple[int, float]:
    joint = [
        day for day, row in actions.items() if row[key] not in {None, 0}
    ]
    agree = sum(
        actions[day]["side"] == ("B" if actions[day][key] > 0 else "A")
        for day in joint
    )
    return len(joint), 100.0 * agree / max(len(joint), 1)


def percentile(values: list[float], q: float) -> float | None:
    return float(np.percentile(values, q)) if values else None


def main() -> int:
    audit = shared.load_json(shared.AUDIT)
    quote_payload = shared.load_json(shared.TARGET_QUOTES)
    snapshots = shared.load_json(shared.SNAPSHOTS)
    if any(
        payload.get("returns_read") is not False
        for payload in [audit, quote_payload, snapshots]
    ):
        raise RuntimeError("Returns-blind source artifact is invalid")
    excluded = set(audit["degraded_dates"]["ARCX.PILLAR"]) | set(
        audit["degraded_dates"]["EQUS.MINI"]
    )
    maps = snapshot_maps(snapshots)
    primary, valid = build_actions(maps, excluded, PRIMARY)
    variants = {
        name: build_actions(maps, excluded, clocks)[0]
        for name, clocks in VARIANTS.items()
    }
    stability = {
        name: compare(primary, actions) for name, actions in variants.items()
    }

    quotes = shared.quote_map(quote_payload)
    executable: dict[str, dict[str, Any]] = {}
    waits: list[float] = []
    entries_after_signal = True
    for day, signal in primary.items():
        if not "2023-03-28" <= day <= "2026-07-24":
            continue
        symbol = signal["symbol"]
        required = [(day, symbol, target) for target in ENTRY_TARGETS + [EXIT_TARGET]]
        if not all(
            key in quotes and not quotes[key]["equs_degraded"] for key in required
        ):
            continue
        selected = {
            target: quotes[(day, symbol, target)]
            for target in ENTRY_TARGETS + [EXIT_TARGET]
        }
        if any(
            float(row["event_wait_seconds"]) > MAX_EVENT_WAIT
            for row in selected.values()
        ):
            continue
        if any(
            pd.Timestamp(selected[target]["ts_recv"])
            <= pd.Timestamp(signal["signal_ts_recv"])
            for target in ENTRY_TARGETS
        ):
            entries_after_signal = False
            continue
        waits.append(float(selected[PRIMARY_ENTRY]["event_wait_seconds"]))
        executable[day] = {
            "symbol": symbol,
            "quote_times": {
                target: {
                    "ts_event": selected[target]["ts_event"],
                    "ts_recv": selected[target]["ts_recv"],
                    "event_wait_seconds": selected[target][
                        "event_wait_seconds"
                    ],
                }
                for target in selected
            },
        }

    development = {
        day: row
        for day, row in primary.items()
        if "2021-01-01" <= day <= "2023-12-31"
    }
    executable_development = {
        day: row
        for day, row in executable.items()
        if "2023-03-28" <= day <= "2023-12-31"
    }
    dev_sides = Counter(row["side"] for row in development.values())
    exec_sides = Counter(primary[day]["side"] for day in executable_development)
    minority_dev = (
        min(dev_sides.values()) / max(sum(dev_sides.values()), 1)
        if len(dev_sides) == 2
        else 0.0
    )
    minority_exec = (
        min(exec_sides.values()) / max(sum(exec_sides.values()), 1)
        if len(exec_sides) == 2
        else 0.0
    )
    by_year = {
        str(year): sum(day.startswith(str(year)) for day in primary)
        for year in range(2021, 2027)
    }
    overlap_signals = sum(
        "2023-03-28" <= day <= "2026-07-24" for day in primary
    )
    execution_coverage = len(executable) / max(overlap_signals, 1)
    selection_share = len(primary) / max(valid, 1)
    wait_p95 = percentile(waits, 95)

    final_side_joint = [
        day
        for day, row in primary.items()
        if row["late_opening_side"] in {"A", "B"}
    ]
    final_side_agreement = 100.0 * sum(
        primary[day]["side"] == primary[day]["late_opening_side"]
        for day in final_side_joint
    ) / max(len(final_side_joint), 1)
    displacement_joint, displacement_agreement = agreement_with_signed_value(
        primary, "late_reference_displacement"
    )
    momentum_joint, momentum_agreement = agreement_with_signed_value(
        primary, "recent_indicative_move"
    )

    openings, previous_closes, _ = v48.load_statistics()
    gap_joint = 0
    gap_agree = 0
    for day, signal in primary.items():
        if day in openings and day in previous_closes and "SPY" in openings[day]:
            gap = (
                float(openings[day]["SPY"]["price"])
                / float(previous_closes[day]["SPY"])
                - 1.0
            )
            if gap != 0:
                gap_joint += 1
                gap_agree += signal["side"] == ("B" if gap > 0 else "A")
    gap_agreement = 100.0 * gap_agree / max(gap_joint, 1)
    signals_before_boundary = all(
        pd.Timestamp(row["signal_ts_recv"])
        .tz_convert("America/New_York")
        .time()
        < pd.Timestamp("09:30:00").time()
        for row in primary.values()
    )

    gates = {
        "development_frequency_at_least_two_per_week": len(development)
        / declared_weeks("2021-01-01", "2023-12-31")
        >= 2.0,
        "at_least_100_signals_each_development_year": all(
            by_year[str(year)] >= 100 for year in [2021, 2022, 2023]
        ),
        "at_least_20_signals_in_2026": by_year["2026"] >= 20,
        "both_directions_and_minority_at_least_20pct": len(dev_sides) == 2
        and minority_dev >= 0.20,
        "executable_development_frequency_at_least_two_per_week": len(
            executable_development
        )
        / declared_weeks("2023-03-28", "2023-12-31")
        >= 2.0,
        "executable_both_directions_and_minority_at_least_20pct": len(exec_sides)
        == 2
        and minority_exec >= 0.20,
        "execution_coverage_at_least_90pct": execution_coverage >= 0.90,
        "primary_entry_wait_p95_no_more_than_30s": wait_p95 is not None
        and wait_p95 <= 30.0,
        "early_start_identical_action_including_cash_at_least_60pct": stability[
            "early_start"
        ]["identical_action_including_cash_pct"]
        >= 60.0,
        "late_end_identical_action_including_cash_at_least_60pct": stability[
            "late_end"
        ]["identical_action_including_cash_pct"]
        >= 60.0,
        "opening_gap_direction_agreement_below_80pct": gap_agreement < 80.0,
        "final_side_agreement_below_80pct": final_side_agreement < 80.0,
        "final_displacement_agreement_below_80pct": displacement_agreement
        < 80.0,
        "recent_indicative_move_agreement_below_80pct": momentum_agreement < 80.0,
        "selection_share_between_20_and_80pct": 0.20 <= selection_share <= 0.80,
        "causal_timestamps": signals_before_boundary and entries_after_signal,
    }
    passed = all(gates.values())
    payload = {
        "status": "pass_returns_blind_feasibility_authorize_preregistration"
        if passed
        else "fail_returns_blind_feasibility_no_pnl",
        "returns_read": False,
        "pnl_calculated": False,
        "rule": {
            "primary_clocks": PRIMARY,
            "wedge": "ind_match_price - auct_interest_clr_price",
            "condition": "same nonzero sign and strictly widening absolute wedge",
            "actuators": "positive -> UPRO; negative -> SPXU",
            "signal_boundary": "09:30:00",
            "entry_targets": ENTRY_TARGETS,
            "primary_entry": PRIMARY_ENTRY,
            "exit_target": EXIT_TARGET,
        },
        "degraded_dates_excluded_union": sorted(excluded),
        "development_2021_2023": {
            "signals": len(development),
            "signals_per_week": len(development)
            / declared_weeks("2021-01-01", "2023-12-31"),
            "side_counts": dict(dev_sides),
            "minority_share": minority_dev,
        },
        "by_year": by_year,
        "stability": stability,
        "all_overlap_execution": {
            "feature_signals": overlap_signals,
            "executable_signals": len(executable),
            "coverage": execution_coverage,
            "primary_entry_wait_p95_seconds": wait_p95,
        },
        "executable_development_2023_overlap": {
            "signals": len(executable_development),
            "signals_per_week": len(executable_development)
            / declared_weeks("2023-03-28", "2023-12-31"),
            "side_counts": dict(exec_sides),
            "minority_share": minority_exec,
        },
        "returns_blind_controls": {
            "valid_two_snapshot_sessions": valid,
            "selection_share": selection_share,
            "opening_gap_joint": gap_joint,
            "opening_gap_direction_agreement_pct": gap_agreement,
            "final_side_joint": len(final_side_joint),
            "final_side_direction_agreement_pct": final_side_agreement,
            "final_displacement_joint": displacement_joint,
            "final_displacement_direction_agreement_pct": displacement_agreement,
            "recent_indicative_move_joint": momentum_joint,
            "recent_indicative_move_direction_agreement_pct": momentum_agreement,
        },
        "timestamp_observability": {
            "all_signals_received_before_09_30": signals_before_boundary,
            "all_entries_after_signal": entries_after_signal,
        },
        "gates": gates,
        "gate_passed": passed,
        "signals": primary,
        "executable_signal_dates": sorted(executable),
        "warning": "No post-entry return, P&L, benchmark, or placebo outcome was calculated.",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "development_signals": len(development),
                "development_per_week": payload["development_2021_2023"][
                    "signals_per_week"
                ],
                "failed_gates": [
                    name for name, value in gates.items() if not value
                ],
                "output": str(OUTPUT.relative_to(ROOT)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
