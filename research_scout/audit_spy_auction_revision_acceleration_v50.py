"""Returns-blind audit for SPY opening-auction revision-intensity acceleration v50."""

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
OUTPUT = ROOT / "research_scout" / "spy_auction_revision_acceleration_returns_blind_audit_v50.json"
SIGNAL_BOUNDARY_SECOND = 9 * 3600 + 30 * 60
ENTRY_TARGETS = ["09:30:01", "09:30:05", "09:31:00"]
PRIMARY_ENTRY = "09:30:05"
EXIT_TARGET = "09:35:00"
MAX_EVENT_WAIT = 60.0
PRIMARY = ((9 * 3600 + 28 * 60, 9 * 3600 + 29 * 60), (9 * 3600 + 29 * 60, 9 * 3600 + 29 * 60 + 50))
LEFT = ((9 * 3600 + 27 * 60 + 50, 9 * 3600 + 28 * 60 + 50), (9 * 3600 + 28 * 60 + 50, 9 * 3600 + 29 * 60 + 40))
RIGHT = ((9 * 3600 + 28 * 60 + 10, 9 * 3600 + 29 * 60 + 10), (9 * 3600 + 29 * 60 + 10, 9 * 3600 + 29 * 60 + 59))


def declared_weeks(start: str, end: str) -> float:
    return ((pd.Timestamp(end) - pd.Timestamp(start)).days + 1) / 7.0


def collect_events() -> tuple[dict[str, list[dict[str, Any]]], int]:
    events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows_scanned = 0
    minimum_second = LEFT[0][0]
    for chunk_number, frame in enumerate(
        technical.db.read_dbn(technical.IMBALANCE).to_df(
            count=1_000_000, map_symbols=True, tz="UTC"
        ),
        start=1,
    ):
        frame = frame.reset_index()
        rows_scanned += len(frame)
        event = pd.to_datetime(frame["ts_event"], utc=True).dt.tz_convert("America/New_York")
        receive = pd.to_datetime(frame["ts_recv"], utc=True).dt.tz_convert("America/New_York")
        seconds = event.dt.hour * 3600 + event.dt.minute * 60 + event.dt.second + event.dt.microsecond / 1_000_000
        mask = (
            frame["auction_type"].astype(str).eq("M")
            & seconds.ge(minimum_second)
            & seconds.lt(SIGNAL_BOUNDARY_SECOND)
        )
        selected = frame.loc[mask].copy()
        if not selected.empty:
            selected["event_ny"] = event.loc[mask]
            selected["receive_ny"] = receive.loc[mask]
            selected["second"] = seconds.loc[mask]
            selected["session_date"] = selected["event_ny"].dt.strftime("%Y-%m-%d")
            for row in selected.itertuples(index=False):
                price = float(row.ind_match_price)
                if np.isfinite(price) and price > 0:
                    events[str(row.session_date)].append(
                        {
                            "second": float(row.second),
                            "price": price,
                            "side": str(row.side),
                            "ts_event": pd.Timestamp(row.ts_event).isoformat(),
                            "ts_recv": pd.Timestamp(row.ts_recv).isoformat(),
                            "receive_ny": pd.Timestamp(row.receive_ny).isoformat(),
                        }
                    )
        if chunk_number % 10 == 0:
            print(f"v50 chunks={chunk_number} rows={rows_scanned}", flush=True)
    for day in events:
        events[day].sort(key=lambda row: row["ts_event"])
    return dict(events), rows_scanned


def window_metrics(rows: list[dict[str, Any]], start: float, end: float) -> dict[str, Any] | None:
    selected = [row for row in rows if start <= row["second"] < end]
    if len(selected) < 2:
        return None
    prices = [row["price"] for row in selected]
    changes = sum(right != left for left, right in zip(prices, prices[1:]))
    return {
        "start": start,
        "end": end,
        "duration_seconds": end - start,
        "records": len(selected),
        "price_revision_count": changes,
        "first_price": prices[0],
        "last_price": prices[-1],
        "net_move": prices[-1] - prices[0],
        "last_side": selected[-1]["side"],
        "last_ts_event": selected[-1]["ts_event"],
        "last_ts_recv": selected[-1]["ts_recv"],
        "last_receive_ny": selected[-1]["receive_ny"],
    }


def build_actions(
    events: dict[str, list[dict[str, Any]]],
    excluded: set[str],
    windows: tuple[tuple[float, float], tuple[float, float]],
) -> tuple[dict[str, dict[str, Any]], int]:
    actions: dict[str, dict[str, Any]] = {}
    nonzero_late_sessions = 0
    for day, rows in sorted(events.items()):
        if day in excluded:
            continue
        early = window_metrics(rows, *windows[0])
        late = window_metrics(rows, *windows[1])
        if early is None or late is None or late["net_move"] == 0:
            continue
        nonzero_late_sessions += 1
        accelerated = (
            late["price_revision_count"] * early["duration_seconds"]
            > early["price_revision_count"] * late["duration_seconds"]
        )
        if not accelerated:
            continue
        side = "B" if late["net_move"] > 0 else "A"
        actions[day] = {
            "side": side,
            "symbol": "UPRO" if side == "B" else "SPXU",
            "early": early,
            "late": late,
            "signal_ts_event": late["last_ts_event"],
            "signal_ts_recv": late["last_ts_recv"],
        }
    return actions, nonzero_late_sessions


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
    if any(payload.get("returns_read") is not False for payload in [audit, quote_payload, snapshots]):
        raise RuntimeError("Returns-blind source artifact is invalid")
    excluded = set(audit["degraded_dates"]["ARCX.PILLAR"]) | set(audit["degraded_dates"]["EQUS.MINI"])
    events, rows_scanned = collect_events()
    primary, nonzero_late_sessions = build_actions(events, excluded, PRIMARY)
    left, _ = build_actions(events, excluded, LEFT)
    right, _ = build_actions(events, excluded, RIGHT)
    stability = {"left": compare(primary, left), "right": compare(primary, right)}

    quotes = shared.quote_map(quote_payload)
    executable: dict[str, dict[str, Any]] = {}
    waits: list[float] = []
    entry_after_signal = True
    for day, signal in primary.items():
        if not "2023-03-28" <= day <= "2026-07-24":
            continue
        symbol = signal["symbol"]
        required = [(day, symbol, target) for target in ENTRY_TARGETS + [EXIT_TARGET]]
        if not all(key in quotes and not quotes[key]["equs_degraded"] for key in required):
            continue
        selected = {target: quotes[(day, symbol, target)] for target in ENTRY_TARGETS + [EXIT_TARGET]}
        if any(float(row["event_wait_seconds"]) > MAX_EVENT_WAIT for row in selected.values()):
            continue
        if any(pd.Timestamp(selected[target]["ts_recv"]) <= pd.Timestamp(signal["signal_ts_recv"]) for target in ENTRY_TARGETS):
            entry_after_signal = False
            continue
        waits.append(float(selected[PRIMARY_ENTRY]["event_wait_seconds"]))
        executable[day] = {"symbol": symbol, "quote_times": selected}

    development = {day: row for day, row in primary.items() if "2021-01-01" <= day <= "2023-12-31"}
    executable_development = {
        day: row for day, row in executable.items() if "2023-03-28" <= day <= "2023-12-31"
    }
    dev_sides = Counter(row["side"] for row in development.values())
    exec_sides = Counter(primary[day]["side"] for day in executable_development)
    minority_dev = min(dev_sides.values()) / max(sum(dev_sides.values()), 1) if len(dev_sides) == 2 else 0.0
    minority_exec = min(exec_sides.values()) / max(sum(exec_sides.values()), 1) if len(exec_sides) == 2 else 0.0
    by_year = {str(year): sum(day.startswith(str(year)) for day in primary) for year in range(2021, 2027)}
    overlap_signals = sum("2023-03-28" <= day <= "2026-07-24" for day in primary)
    execution_coverage = len(executable) / max(overlap_signals, 1)

    final_map = {
        row["session_date"]: row
        for row in snapshots["snapshots"]
        if row["cutoff"] == "09:29:50"
    }
    final_joint = [
        day for day in primary
        if day in final_map and final_map[day]["side"] in {"A", "B"}
    ]
    final_side_agreement = 100.0 * sum(
        primary[day]["side"] == final_map[day]["side"] for day in final_joint
    ) / max(len(final_joint), 1)
    early_joint = [day for day, row in primary.items() if row["early"]["net_move"] != 0]
    early_agreement = 100.0 * sum(
        primary[day]["side"] == ("B" if primary[day]["early"]["net_move"] > 0 else "A")
        for day in early_joint
    ) / max(len(early_joint), 1)

    openings, previous_closes, _ = v48.load_statistics()
    gap_joint: list[str] = []
    gap_agree = 0
    for day, signal in primary.items():
        prior = previous_closes.get(day)
        if prior and day in openings and "SPY" in openings[day]:
            gap = float(openings[day]["SPY"]["price"]) / float(prior["SPY"]) - 1.0
            if gap != 0:
                gap_joint.append(day)
                gap_agree += signal["side"] == ("B" if gap > 0 else "A")
    gap_agreement = 100.0 * gap_agree / max(len(gap_joint), 1)
    all_signal_before_boundary = all(
        pd.Timestamp(row["signal_ts_recv"]).tz_convert("America/New_York").time()
        < pd.Timestamp("09:30:00").time()
        for row in primary.values()
    )
    selection_share = len(primary) / max(nonzero_late_sessions, 1)
    waits_p95 = percentile(waits, 95)

    gates = {
        "development_frequency_at_least_two_per_week": len(development)
        / declared_weeks("2021-01-01", "2023-12-31")
        >= 2.0,
        "at_least_100_signals_each_development_year": all(by_year[str(year)] >= 100 for year in [2021, 2022, 2023]),
        "at_least_20_signals_in_2026": by_year["2026"] >= 20,
        "both_directions_and_minority_at_least_20pct": len(dev_sides) == 2 and minority_dev >= 0.20,
        "left_window_identical_action_including_cash_at_least_60pct": stability["left"][
            "identical_action_including_cash_pct"
        ]
        >= 60.0,
        "right_window_identical_action_including_cash_at_least_60pct": stability["right"][
            "identical_action_including_cash_pct"
        ]
        >= 60.0,
        "execution_coverage_at_least_90pct": execution_coverage >= 0.90,
        "executable_development_frequency_at_least_two_per_week": len(executable_development)
        / declared_weeks("2023-03-28", "2023-12-31")
        >= 2.0,
        "executable_both_directions_and_minority_at_least_20pct": len(exec_sides) == 2
        and minority_exec >= 0.20,
        "primary_entry_wait_p95_no_more_than_30s": waits_p95 is not None and waits_p95 <= 30.0,
        "opening_gap_direction_agreement_below_80pct": gap_agreement < 80.0,
        "early_window_direction_agreement_below_80pct": early_agreement < 80.0,
        "final_imbalance_side_agreement_below_80pct": final_side_agreement < 80.0,
        "selection_share_between_20_and_80pct_of_nonzero_late_moves": 0.20 <= selection_share <= 0.80,
        "signals_before_boundary_and_entries_after_signal": all_signal_before_boundary and entry_after_signal,
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
            "primary_windows": PRIMARY,
            "direction": "sign of late ind_match_price net move",
            "condition": "late price-revision rate strictly exceeds early rate",
            "signal_boundary": "09:30:00",
            "entries": ENTRY_TARGETS,
            "primary_entry": PRIMARY_ENTRY,
            "exit": EXIT_TARGET,
        },
        "degraded_dates_excluded_union": sorted(excluded),
        "development_2021_2023": {
            "signals": len(development),
            "signals_per_week": len(development) / declared_weeks("2021-01-01", "2023-12-31"),
            "side_counts": dict(dev_sides),
            "minority_share": minority_dev,
        },
        "by_year": by_year,
        "stability": stability,
        "all_overlap_execution": {
            "feature_signals": overlap_signals,
            "executable_signals": len(executable),
            "coverage": execution_coverage,
            "primary_entry_wait_p95_seconds": waits_p95,
        },
        "executable_development_2023_overlap": {
            "signals": len(executable_development),
            "signals_per_week": len(executable_development)
            / declared_weeks("2023-03-28", "2023-12-31"),
            "side_counts": dict(exec_sides),
            "minority_share": minority_exec,
        },
        "returns_blind_controls": {
            "nonzero_late_move_sessions": nonzero_late_sessions,
            "selection_share": selection_share,
            "opening_gap_joint_days": len(gap_joint),
            "opening_gap_direction_agreement_pct": gap_agreement,
            "early_window_joint_days": len(early_joint),
            "early_window_direction_agreement_pct": early_agreement,
            "final_side_joint_days": len(final_joint),
            "final_imbalance_side_agreement_pct": final_side_agreement,
        },
        "timestamp_observability": {
            "all_signals_received_before_09_30": all_signal_before_boundary,
            "all_entries_after_signal": entry_after_signal,
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
                "development_per_week": payload["development_2021_2023"]["signals_per_week"],
                "failed_gates": [name for name, value in gates.items() if not value],
                "output": str(OUTPUT.relative_to(ROOT)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
