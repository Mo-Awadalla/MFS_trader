"""Returns-blind feasibility for SPY cross-auction inventory persistence v51."""

from __future__ import annotations

import bisect
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_scout import audit_spy_auction_absorption_failure_v35 as shared
from research_scout import audit_leveraged_etf_official_open_basis_v48 as v48

ROOT = Path(__file__).resolve().parents[1]
CLOSING = ROOT / "research_scout" / "spy_closing_auction_snapshots_v41.json"
OUTPUT = ROOT / "research_scout" / "spy_cross_auction_inventory_persistence_returns_blind_audit_v51.json"
PRIMARY_OPEN = "09:29:50"
ADJACENT_OPENS = ["09:29:30", "09:29:59"]
PRIMARY_CLOSE = "15:20:00"
CLOSE_STABILITY = "15:29:50"
ENTRY_TARGETS = ["09:30:01", "09:30:05", "09:31:00"]
PRIMARY_ENTRY = "09:30:05"
EXIT_TARGET = "09:35:00"
MAX_EVENT_WAIT = 60.0


def declared_weeks(start: str, end: str) -> float:
    return ((pd.Timestamp(end) - pd.Timestamp(start)).days + 1) / 7.0


def maps(payload: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for row in payload["snapshots"]:
        result.setdefault(str(row["cutoff"]), {})[str(row["session_date"])] = row
    return result


def prior_day_map(close_days: list[str], open_days: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for day in sorted(open_days):
        index = bisect.bisect_left(close_days, day) - 1
        if index >= 0:
            result[day] = close_days[index]
    return result


def build_actions(
    closing_maps: dict[str, dict[str, dict[str, Any]]],
    opening_maps: dict[str, dict[str, dict[str, Any]]],
    excluded: set[str],
    open_cutoff: str,
) -> tuple[dict[str, dict[str, Any]], int]:
    closes = closing_maps[PRIMARY_CLOSE]
    opens = opening_maps[open_cutoff]
    previous = prior_day_map(sorted(closes), sorted(opens))
    actions: dict[str, dict[str, Any]] = {}
    eligible = 0
    for day in sorted(opens):
        prior_day = previous.get(day)
        if prior_day is None or day in excluded or prior_day in excluded:
            continue
        close = closes.get(prior_day)
        opening = opens[day]
        if (
            close is None
            or close["side"] not in {"A", "B"}
            or float(close["market_imbalance_qty"]) <= 0
            or float(opening["ref_price"]) <= 0
            or float(opening["ind_match_price"]) <= 0
        ):
            continue
        displacement = float(opening["ind_match_price"]) - float(opening["ref_price"])
        if displacement == 0:
            continue
        eligible += 1
        direction = "B" if displacement > 0 else "A"
        if close["side"] != direction:
            continue
        actions[day] = {
            "side": direction,
            "symbol": "SPY" if direction == "B" else "SH",
            "prior_session": prior_day,
            "prior_closing_side": close["side"],
            "prior_market_imbalance_qty": float(close["market_imbalance_qty"]),
            "prior_close_ts_event": close["ts_event"],
            "prior_close_ts_recv": close["ts_recv"],
            "current_displacement": displacement,
            "current_opening_side": opening["side"],
            "current_ref_price": float(opening["ref_price"]),
            "current_ind_match_price": float(opening["ind_match_price"]),
            "signal_ts_event": opening["ts_event"],
            "signal_ts_recv": opening["ts_recv"],
            "open_cutoff": open_cutoff,
        }
    return actions, eligible


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


def percentile(values: list[float], q: float) -> float | None:
    return float(np.percentile(values, q)) if values else None


def main() -> int:
    audit = shared.load_json(shared.AUDIT)
    quote_payload = shared.load_json(shared.TARGET_QUOTES)
    opening_payload = shared.load_json(shared.SNAPSHOTS)
    closing_payload = shared.load_json(CLOSING)
    if any(
        payload.get("returns_read") is not False
        for payload in [audit, quote_payload, opening_payload, closing_payload]
    ):
        raise RuntimeError("Returns-blind source artifact is invalid")
    excluded = set(audit["degraded_dates"]["ARCX.PILLAR"]) | set(
        audit["degraded_dates"]["EQUS.MINI"]
    )
    opening_maps = maps(opening_payload)
    closing_maps = maps(closing_payload)
    primary, eligible = build_actions(
        closing_maps, opening_maps, excluded, PRIMARY_OPEN
    )
    adjacent = {
        cutoff: build_actions(closing_maps, opening_maps, excluded, cutoff)[0]
        for cutoff in ADJACENT_OPENS
    }
    stability = {
        cutoff: compare(primary, actions) for cutoff, actions in adjacent.items()
    }

    closes_late = closing_maps[CLOSE_STABILITY]
    prior_close_side_joint = 0
    prior_close_side_agree = 0
    for signal in primary.values():
        late = closes_late.get(signal["prior_session"])
        if late and late["side"] in {"A", "B"}:
            prior_close_side_joint += 1
            prior_close_side_agree += late["side"] == signal["prior_closing_side"]
    prior_close_stability = (
        100.0 * prior_close_side_agree / max(prior_close_side_joint, 1)
    )

    quotes = shared.quote_map(quote_payload)
    executable: dict[str, dict[str, Any]] = {}
    waits: list[float] = []
    entries_after_signal = True
    for day, signal in primary.items():
        if not "2023-03-28" <= day <= "2026-07-24":
            continue
        symbol = signal["symbol"]
        required = [(day, symbol, target) for target in ENTRY_TARGETS + [EXIT_TARGET]]
        if not all(key in quotes and not quotes[key]["equs_degraded"] for key in required):
            continue
        selected = {
            target: quotes[(day, symbol, target)]
            for target in ENTRY_TARGETS + [EXIT_TARGET]
        }
        if any(float(row["event_wait_seconds"]) > MAX_EVENT_WAIT for row in selected.values()):
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
                    "event_wait_seconds": selected[target]["event_wait_seconds"],
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
    selection_share = len(primary) / max(eligible, 1)

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
    current_side_joint = sum(
        row["current_opening_side"] in {"A", "B"} for row in primary.values()
    )
    current_side_agreement = 100.0 * sum(
        row["current_opening_side"] == row["side"] for row in primary.values()
        if row["current_opening_side"] in {"A", "B"}
    ) / max(current_side_joint, 1)
    signals_before_boundary = all(
        pd.Timestamp(row["signal_ts_recv"])
        .tz_convert("America/New_York")
        .time()
        < pd.Timestamp("09:30:00").time()
        for row in primary.values()
    )
    wait_p95 = percentile(waits, 95)

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
        "primary_entry_wait_p95_no_more_than_20s": wait_p95 is not None
        and wait_p95 <= 20.0,
        "open_09_29_30_identical_action_including_cash_at_least_60pct": stability[
            "09:29:30"
        ]["identical_action_including_cash_pct"]
        >= 60.0,
        "open_09_29_59_identical_action_including_cash_at_least_60pct": stability[
            "09:29:59"
        ]["identical_action_including_cash_pct"]
        >= 60.0,
        "prior_closing_side_stability_at_least_70pct": prior_close_stability
        >= 70.0,
        "opening_gap_direction_agreement_below_80pct": gap_agreement < 80.0,
        "current_final_side_agreement_below_80pct": current_side_agreement < 80.0,
        "selection_share_between_20_and_80pct": 0.20 <= selection_share <= 0.80,
        "signals_before_boundary_and_entries_after_signal": signals_before_boundary
        and entries_after_signal,
    }
    passed = all(gates.values())
    payload = {
        "status": "pass_returns_blind_feasibility_authorize_preregistration"
        if passed
        else "fail_returns_blind_feasibility_no_pnl",
        "returns_read": False,
        "pnl_calculated": False,
        "rule": {
            "prior_closing_cutoff": PRIMARY_CLOSE,
            "prior_condition": "positive market_imbalance_qty and nonneutral side",
            "current_opening_cutoff": PRIMARY_OPEN,
            "current_direction": "sign(ind_match_price - ref_price)",
            "interaction": "prior Closing side agrees with current displacement",
            "actuators": "positive -> SPY; negative -> SH",
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
        "stability": {
            "current_opening_cutoffs": stability,
            "prior_closing_side_joint": prior_close_side_joint,
            "prior_closing_side_agreement_pct": prior_close_stability,
        },
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
            "eligible_cross_auction_sessions": eligible,
            "selection_share": selection_share,
            "opening_gap_joint": gap_joint,
            "opening_gap_direction_agreement_pct": gap_agreement,
            "current_final_side_joint": current_side_joint,
            "current_final_side_agreement_pct": current_side_agreement,
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
