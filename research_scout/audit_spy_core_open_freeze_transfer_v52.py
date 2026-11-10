"""Returns-blind audit for SPY Core-Open freeze transfer v52."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_scout import audit_cash_etf_new_data_v34 as technical
from research_scout import audit_spy_auction_absorption_failure_v35 as shared
from research_scout import audit_leveraged_etf_official_open_basis_v48 as v48

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "spy_core_open_freeze_transfer_returns_blind_audit_v52.json"
ENTRY_TARGETS = ["09:30:01", "09:30:05", "09:31:00"]
PRIMARY_ENTRY = "09:30:05"
EXIT_TARGET = "09:35:00"
MAX_EVENT_WAIT = 60.0
START_SECOND = 9 * 3600 + 29 * 60 + 30
END_SECOND = 9 * 3600 + 30 * 60


def declared_weeks(start: str, end: str) -> float:
    return ((pd.Timestamp(end) - pd.Timestamp(start)).days + 1) / 7.0


def collect_transitions() -> tuple[dict[str, dict[str, Any]], int]:
    states: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"last_nonfreeze": None, "freeze": [], "prefreeze": []}
    )
    rows_scanned = 0
    for chunk_number, frame in enumerate(
        technical.db.read_dbn(technical.IMBALANCE).to_df(
            count=1_000_000, map_symbols=True, tz="UTC"
        ),
        start=1,
    ):
        frame = frame.reset_index()
        rows_scanned += len(frame)
        event = pd.to_datetime(frame["ts_event"], utc=True).dt.tz_convert(
            "America/New_York"
        )
        receive = pd.to_datetime(frame["ts_recv"], utc=True).dt.tz_convert(
            "America/New_York"
        )
        seconds = (
            event.dt.hour * 3600
            + event.dt.minute * 60
            + event.dt.second
            + event.dt.microsecond / 1_000_000
        )
        mask = (
            frame["auction_type"].astype(str).eq("M")
            & seconds.ge(START_SECOND)
            & seconds.lt(END_SECOND)
        )
        selected = frame.loc[mask].copy()
        if not selected.empty:
            selected["event_ny"] = event.loc[mask]
            selected["receive_ny"] = receive.loc[mask]
            selected["session_date"] = selected["event_ny"].dt.strftime(
                "%Y-%m-%d"
            )
            for row in selected.itertuples(index=False):
                price = float(row.ind_match_price)
                if not np.isfinite(price) or price <= 0:
                    continue
                day = str(row.session_date)
                payload = {
                    "price": price,
                    "side": str(row.side),
                    "freeze_status": int(row.freeze_status),
                    "ts_event": pd.Timestamp(row.ts_event).isoformat(),
                    "ts_recv": pd.Timestamp(row.ts_recv).isoformat(),
                }
                if int(row.freeze_status) == 0:
                    states[day]["last_nonfreeze"] = payload
                    states[day]["prefreeze"].append(payload)
                elif int(row.freeze_status) == 1:
                    states[day]["freeze"].append(payload)
        if chunk_number % 10 == 0:
            print(f"v52 chunks={chunk_number} rows={rows_scanned}", flush=True)
    return dict(states), rows_scanned


def action(
    start: dict[str, Any] | None, end: dict[str, Any] | None
) -> tuple[str | None, float | None]:
    if start is None or end is None:
        return None, None
    move = float(end["price"]) - float(start["price"])
    if move > 0:
        return "B", move
    if move < 0:
        return "A", move
    return None, move


def build_actions(
    states: dict[str, dict[str, Any]], excluded: set[str], variant: str
) -> tuple[dict[str, dict[str, Any]], int]:
    actions: dict[str, dict[str, Any]] = {}
    valid_freeze_sessions = 0
    for day, state in sorted(states.items()):
        if day in excluded or state["last_nonfreeze"] is None or not state["freeze"]:
            continue
        valid_freeze_sessions += 1
        if variant == "primary":
            start = state["last_nonfreeze"]
            end = state["freeze"][-1]
        elif variant == "transition_only":
            start = state["freeze"][0]
            end = state["freeze"][-1]
        elif variant == "penultimate_endpoint":
            start = state["last_nonfreeze"]
            end = state["freeze"][-2] if len(state["freeze"]) >= 2 else None
        else:
            raise ValueError(variant)
        side, move = action(start, end)
        if side is None or start is None or end is None:
            continue
        prefreeze_move = None
        if len(state["prefreeze"]) >= 2:
            prefreeze_move = (
                float(state["prefreeze"][-1]["price"])
                - float(state["prefreeze"][0]["price"])
            )
        actions[day] = {
            "side": side,
            "symbol": "UPRO" if side == "B" else "SPXU",
            "freeze_move": move,
            "prefreeze_move": prefreeze_move,
            "first_freeze_ts_event": state["freeze"][0]["ts_event"],
            "first_freeze_ts_recv": state["freeze"][0]["ts_recv"],
            "last_nonfreeze_ts_event": state["last_nonfreeze"]["ts_event"],
            "last_nonfreeze_ts_recv": state["last_nonfreeze"]["ts_recv"],
            "signal_ts_event": end["ts_event"],
            "signal_ts_recv": end["ts_recv"],
            "final_freeze_side": state["freeze"][-1]["side"],
            "freeze_message_count": len(state["freeze"]),
            "variant": variant,
        }
    return actions, valid_freeze_sessions


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
    snapshots = shared.load_json(shared.SNAPSHOTS)
    if any(
        payload.get("returns_read") is not False
        for payload in [audit, quote_payload, snapshots]
    ):
        raise RuntimeError("Returns-blind source artifact is invalid")
    excluded = set(audit["degraded_dates"]["ARCX.PILLAR"]) | set(
        audit["degraded_dates"]["EQUS.MINI"]
    )
    states, rows_scanned = collect_transitions()
    primary, valid_freeze_sessions = build_actions(states, excluded, "primary")
    transition_only, _ = build_actions(
        states, excluded, "transition_only"
    )
    penultimate, _ = build_actions(
        states, excluded, "penultimate_endpoint"
    )
    stability = {
        "transition_only": compare(primary, transition_only),
        "penultimate_endpoint": compare(primary, penultimate),
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
    selection_share = len(primary) / max(valid_freeze_sessions, 1)
    wait_p95 = percentile(waits, 95)

    final_map = {
        row["session_date"]: row
        for row in snapshots["snapshots"]
        if row["cutoff"] == "09:29:59"
    }
    final_joint = [
        day
        for day in primary
        if day in final_map and final_map[day]["side"] in {"A", "B"}
    ]
    final_agreement = 100.0 * sum(
        primary[day]["side"] == final_map[day]["side"] for day in final_joint
    ) / max(len(final_joint), 1)
    prefreeze_joint = [
        day
        for day, row in primary.items()
        if row["prefreeze_move"] not in {None, 0}
    ]
    prefreeze_agreement = 100.0 * sum(
        primary[day]["side"]
        == ("B" if primary[day]["prefreeze_move"] > 0 else "A")
        for day in prefreeze_joint
    ) / max(len(prefreeze_joint), 1)

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
        "transition_only_identical_action_including_cash_at_least_60pct": stability[
            "transition_only"
        ]["identical_action_including_cash_pct"]
        >= 60.0,
        "penultimate_identical_action_including_cash_at_least_60pct": stability[
            "penultimate_endpoint"
        ]["identical_action_including_cash_pct"]
        >= 60.0,
        "opening_gap_direction_agreement_below_80pct": gap_agreement < 80.0,
        "final_side_agreement_below_80pct": final_agreement < 80.0,
        "prefreeze_move_direction_agreement_below_80pct": prefreeze_agreement
        < 80.0,
        "selection_share_between_20_and_80pct": 0.20 <= selection_share <= 0.80,
        "valid_transition_and_causal_timestamps": valid_freeze_sessions > 0
        and signals_before_boundary
        and entries_after_signal,
    }
    passed = all(gates.values())
    payload = {
        "status": "pass_returns_blind_feasibility_authorize_preregistration"
        if passed
        else "fail_returns_blind_feasibility_no_pnl",
        "returns_read": False,
        "pnl_calculated": False,
        "rows_scanned": rows_scanned,
        "rule": {
            "feature": "last nonfrozen to final frozen ind_match_price move",
            "actuators": "positive -> UPRO; negative -> SPXU",
            "signal_boundary": "09:30:00",
            "entry_targets": ENTRY_TARGETS,
            "primary_entry": PRIMARY_ENTRY,
            "exit_target": EXIT_TARGET,
        },
        "degraded_dates_excluded_union": sorted(excluded),
        "freeze_session_evidence": {
            "valid_freeze_sessions": valid_freeze_sessions,
            "feature_signals": len(primary),
            "selection_share": selection_share,
        },
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
            "opening_gap_joint": gap_joint,
            "opening_gap_direction_agreement_pct": gap_agreement,
            "final_side_joint": len(final_joint),
            "final_side_direction_agreement_pct": final_agreement,
            "prefreeze_move_joint": len(prefreeze_joint),
            "prefreeze_move_direction_agreement_pct": prefreeze_agreement,
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
