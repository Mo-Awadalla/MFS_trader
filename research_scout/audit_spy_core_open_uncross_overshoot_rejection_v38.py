"""Returns-blind feasibility gate for SPY Core-Open uncross overshoot rejection v38."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_cash_etf_new_data_v34 as technical
from research_scout import audit_spy_auction_absorption_failure_v35 as shared

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "spy_core_open_uncross_overshoot_rejection_returns_blind_audit_v38.json"
PRIMARY_INDICATION = "09:29:59"
ADJACENT_INDICATION = "09:29:50"
PRIMARY_SPY_TARGET = "09:30:01"
ADJACENT_SPY_TARGET = "09:30:05"
ENTRY_TARGETS = {1: "09:31:01", 5: "09:31:05", 60: "09:32:00"}
EXIT_TARGET = "09:35:00"
POSITIVE_LADDER = ["SPY", "SSO", "UPRO"]
NEGATIVE_LADDER = ["SH", "SDS", "SPXU"]


def declared_weeks(start: str, end: str) -> float:
    return ((pd.Timestamp(end) - pd.Timestamp(start)).days + 1) / 7.0


def clock_before(value: str, clock: str) -> bool:
    return pd.Timestamp(value).tz_convert("America/New_York").time() < pd.Timestamp(clock).time()


def load_spy_opening_statistics() -> tuple[dict[str, dict[str, Any]], dict[str, int], dict[str, Any]]:
    frame = technical.db.read_dbn(technical.STATISTICS).to_df(map_symbols=True, tz="UTC").reset_index()
    frame["stat_name"] = frame["stat_type"].map(lambda value: technical.enum_name(technical.db.StatType, value))
    frame = frame.loc[frame["symbol"].astype(str).eq("SPY") & frame["stat_name"].eq("OPENING_PRICE")].copy()
    event = pd.to_datetime(frame["ts_event"], utc=True).dt.tz_convert("America/New_York")
    receive = pd.to_datetime(frame["ts_recv"], utc=True).dt.tz_convert("America/New_York")
    frame["event_ny"] = event
    frame["receive_ny"] = receive
    frame["session_date"] = event.dt.strftime("%Y-%m-%d")
    counts = frame.groupby("session_date").size().astype(int).to_dict()
    mapping: dict[str, dict[str, Any]] = {}
    for day, group in frame.groupby("session_date", sort=True):
        if len(group) != 1:
            continue
        row = group.iloc[0]
        price = float(row["price"])
        quantity = int(row["quantity"])
        if price <= 0 or quantity <= 0:
            continue
        mapping[str(day)] = {
            "price": price,
            "quantity": quantity,
            "ts_event": pd.Timestamp(row["ts_event"]).isoformat(),
            "ts_recv": pd.Timestamp(row["ts_recv"]).isoformat(),
            "event_ny": row["event_ny"].isoformat(),
            "receive_ny": row["receive_ny"].isoformat(),
            "publisher_id": int(row["publisher_id"]),
            "instrument_id": int(row["instrument_id"]),
        }
    integrity = {
        "rows": int(len(frame)),
        "sessions": int(frame["session_date"].nunique()),
        "duplicate_or_ambiguous_sessions": sorted(day for day, count in counts.items() if count != 1),
        "positive_unique_sessions": len(mapping),
        "first_event_ny": event.min().isoformat() if not frame.empty else None,
        "last_event_ny": event.max().isoformat() if not frame.empty else None,
    }
    return mapping, counts, integrity


def action(
    snapshot: dict[str, Any] | None,
    opening: dict[str, Any] | None,
    spy_quote: dict[str, Any] | None,
    *,
    quote_deadline: str,
    maximum_wait_seconds: float,
) -> dict[str, Any] | None:
    if snapshot is None or opening is None or spy_quote is None:
        return None
    indication = float(snapshot.get("ind_match_price") or 0.0)
    reference = float(snapshot.get("ref_price") or 0.0)
    opening_price = float(opening.get("price") or 0.0)
    bid = float(spy_quote.get("bid") or 0.0)
    ask = float(spy_quote.get("ask") or 0.0)
    wait = float(spy_quote.get("event_wait_seconds") or 0.0)
    if min(indication, reference, opening_price, bid, ask) <= 0 or ask < bid or wait > maximum_wait_seconds:
        return None
    if not all(
        [
            clock_before(opening["ts_event"], quote_deadline),
            clock_before(opening["ts_recv"], quote_deadline),
            clock_before(spy_quote["ts_event"], quote_deadline),
            clock_before(spy_quote["ts_recv"], quote_deadline),
        ]
    ):
        return None
    midpoint = (bid + ask) / 2.0
    if indication == opening_price or not min(indication, opening_price) < midpoint < max(indication, opening_price):
        return None
    side = "B" if indication > opening_price else "A"
    signal_received = max(pd.Timestamp(opening["ts_recv"]), pd.Timestamp(spy_quote["ts_recv"]))
    final_displacement = indication / reference - 1.0
    first_continuous_move = midpoint / reference - 1.0
    return {
        "side": side,
        "symbol": "UPRO" if side == "B" else "SPXU",
        "ind_match_price": indication,
        "ref_price": reference,
        "official_open_price": opening_price,
        "spy_continuous_bid": bid,
        "spy_continuous_ask": ask,
        "spy_continuous_midpoint": midpoint,
        "overshoot_return_from_indication": opening_price / indication - 1.0,
        "rejection_fraction": abs(midpoint - opening_price) / abs(indication - opening_price),
        "first_continuous_move_from_reference": first_continuous_move,
        "final_indicative_displacement": final_displacement,
        "final_imbalance_side": snapshot.get("side"),
        "opening_stat_ts_event": opening["ts_event"],
        "opening_stat_ts_recv": opening["ts_recv"],
        "spy_signal_ts_event": spy_quote["ts_event"],
        "spy_signal_ts_recv": spy_quote["ts_recv"],
        "signal_ts_recv": signal_received.isoformat(),
        "spy_signal_event_wait_seconds": wait,
    }


def same_direction(value: float, side: str) -> bool:
    return (value > 0 and side == "B") or (value < 0 and side == "A")


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
    openings, opening_counts, opening_integrity = load_spy_opening_statistics()
    excluded = set(audit["degraded_dates"]["ARCX.PILLAR"]) | set(audit["degraded_dates"]["EQUS.MINI"])
    days = sorted(day for day in openings if "2023-03-28" <= day <= "2026-07-24" and day not in excluded)

    signals: dict[str, dict[str, Any]] = {}
    adjacent_indication: dict[str, dict[str, Any]] = {}
    adjacent_continuous: dict[str, dict[str, Any]] = {}
    for day in days:
        opening = openings.get(day)
        primary_spy = quotes.get((day, "SPY", PRIMARY_SPY_TARGET))
        adjacent_spy = quotes.get((day, "SPY", ADJACENT_SPY_TARGET))
        primary = action(
            snapshots.get((day, PRIMARY_INDICATION)),
            opening,
            primary_spy,
            quote_deadline="09:30:05",
            maximum_wait_seconds=4.0,
        )
        if primary is not None:
            signals[day] = primary
        alternate_indication = action(
            snapshots.get((day, ADJACENT_INDICATION)),
            opening,
            primary_spy,
            quote_deadline="09:30:05",
            maximum_wait_seconds=4.0,
        )
        if alternate_indication is not None:
            adjacent_indication[day] = alternate_indication
        alternate_continuous = action(
            snapshots.get((day, PRIMARY_INDICATION)),
            opening,
            adjacent_spy,
            quote_deadline="09:30:10",
            maximum_wait_seconds=5.0,
        )
        if alternate_continuous is not None:
            adjacent_continuous[day] = alternate_continuous

    executable: dict[str, dict[str, Any]] = {}
    quote_missing: Counter[str] = Counter()
    relevant_ladder_days = 0
    relevant_ladder_missing: Counter[str] = Counter()
    entry_after_signal = True
    for day, signal in signals.items():
        symbol = signal["symbol"]
        required = [(day, symbol, target) for target in [*ENTRY_TARGETS.values(), EXIT_TARGET]]
        if not all(key in quotes and not quotes[key]["equs_degraded"] for key in required):
            for key in required:
                if key not in quotes:
                    quote_missing[f"{symbol}:{key[2]}"] += 1
            continue
        row = dict(signal)
        row["quotes"] = {target: quotes[(day, symbol, target)] for target in [*ENTRY_TARGETS.values(), EXIT_TARGET]}
        signal_recv = pd.Timestamp(signal["signal_ts_recv"])
        if not all(pd.Timestamp(quote["ts_recv"]) > signal_recv for quote in row["quotes"].values()):
            entry_after_signal = False
            continue
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

    development = [day for day in signals if "2023-03-28" <= day <= "2023-12-31"]
    executable_development = [day for day in executable if "2023-03-28" <= day <= "2023-12-31"]
    development_sides = Counter(signals[day]["side"] for day in development)
    executable_development_sides = Counter(executable[day]["side"] for day in executable_development)
    all_sides = Counter(signal["side"] for signal in signals.values())
    minority_development = min(development_sides.values()) / max(sum(development_sides.values()), 1) if len(development_sides) == 2 else 0.0
    minority_all = min(all_sides.values()) / max(sum(all_sides.values()), 1) if len(all_sides) == 2 else 0.0

    controls = {
        "first_continuous_move_from_reference_same_direction_pct": 100.0 * sum(
            same_direction(signal["first_continuous_move_from_reference"], signal["side"])
            for signal in signals.values()
        ) / max(sum(signal["first_continuous_move_from_reference"] != 0 for signal in signals.values()), 1),
        "final_imbalance_side_same_direction_pct": 100.0 * sum(
            signal["final_imbalance_side"] == signal["side"]
            for signal in signals.values()
            if signal["final_imbalance_side"] in {"A", "B"}
        ) / max(sum(signal["final_imbalance_side"] in {"A", "B"} for signal in signals.values()), 1),
        "final_indicative_displacement_same_direction_pct": 100.0 * sum(
            same_direction(signal["final_indicative_displacement"], signal["side"])
            for signal in signals.values()
        ) / max(sum(signal["final_indicative_displacement"] != 0 for signal in signals.values()), 1),
    }

    by_year = {
        str(year): {
            "signals": sum(day.startswith(str(year)) for day in signals),
            "executable_signals": sum(day.startswith(str(year)) for day in executable),
            "side_counts": dict(Counter(signal["side"] for day, signal in signals.items() if day.startswith(str(year)))),
        }
        for year in range(2023, 2027)
    }
    quote_coverage = len(executable) / max(len(signals), 1)
    ladder_coverage = relevant_ladder_days / max(len(executable), 1)
    preopen_stability = compare_actions(signals, adjacent_indication)
    continuous_stability = compare_actions(signals, adjacent_continuous)
    opening_unique = all(opening_counts.get(day) == 1 for day in days)
    primary_availability = all(
        clock_before(signal["opening_stat_ts_event"], "09:30:05")
        and clock_before(signal["opening_stat_ts_recv"], "09:30:05")
        and clock_before(signal["spy_signal_ts_event"], "09:30:05")
        and clock_before(signal["spy_signal_ts_recv"], "09:30:05")
        for signal in signals.values()
    )

    gates = {
        "development_frequency_at_least_two_per_declared_week": len(development) / declared_weeks("2023-03-28", "2023-12-31") >= 2.0,
        "at_least_80_development_signals": len(development) >= 80,
        "at_least_100_signals_each_2024_2025": all(by_year[str(year)]["signals"] >= 100 for year in [2024, 2025]),
        "at_least_20_signals_2026_extension": by_year["2026"]["signals"] >= 20,
        "minority_direction_at_least_20pct_development_and_all": minority_development >= 0.20 and minority_all >= 0.20,
        "upro_and_spxu_each_executable_in_development": len(executable_development_sides) == 2 and all(value > 0 for value in executable_development_sides.values()),
        "actuator_quote_coverage_at_least_90pct": quote_coverage >= 0.90,
        "relevant_side_ladder_09_31_05_availability_at_least_80pct": ladder_coverage >= 0.80,
        "adjacent_indication_09_29_50_identical_action_at_least_60pct": preopen_stability["identical_action_including_cash_pct"] >= 60.0,
        "adjacent_continuous_09_30_05_identical_action_at_least_60pct": continuous_stability["identical_action_including_cash_pct"] >= 60.0,
        "not_redundant_to_first_continuous_move_below_80pct": controls["first_continuous_move_from_reference_same_direction_pct"] < 80.0,
        "not_redundant_to_final_imbalance_side_below_80pct": controls["final_imbalance_side_same_direction_pct"] < 80.0,
        "not_redundant_to_final_displacement_below_80pct": controls["final_indicative_displacement_same_direction_pct"] < 80.0,
        "all_primary_information_received_before_09_30_05_and_entry_after_signal": primary_availability and entry_after_signal,
        "exactly_one_spy_core_open_statistic_per_eligible_session": opening_unique,
    }

    payload = {
        "status": "passed_returns_blind_feasibility" if all(gates.values()) else "failed_returns_blind_feasibility_no_pnl_opened",
        "returns_read": False,
        "rule": {
            "preopen_indication_cutoff": PRIMARY_INDICATION,
            "official_outcome": "ARCX SPY OPENING_PRICE statistic",
            "continuous_acceptance_target": PRIMARY_SPY_TARGET,
            "continuous_acceptance_deadline": "09:30:05",
            "condition": "SPY midpoint strictly between official open and final indicative match price",
            "direction": "from official open toward final indicative match price",
            "actuator": "positive -> UPRO; negative -> SPXU",
            "entry_targets": ENTRY_TARGETS,
            "exit_target": EXIT_TARGET,
            "maximum_event_wait_seconds": 60,
        },
        "degraded_dates_excluded_union": sorted(excluded),
        "opening_statistic_integrity": opening_integrity,
        "development_2023_03_28_2023_12_31": {
            "signals": len(development),
            "trades_per_declared_calendar_week": len(development) / declared_weeks("2023-03-28", "2023-12-31"),
            "side_counts": dict(development_sides),
            "minority_side_share": minority_development,
            "executable_signals": len(executable_development),
            "executable_side_counts": dict(executable_development_sides),
        },
        "all_overlap": {
            "signals": len(signals),
            "executable_signals": len(executable),
            "actuator_quote_coverage_pct": 100.0 * quote_coverage,
            "relevant_side_ladder_available_days": relevant_ladder_days,
            "relevant_side_ladder_coverage_pct": 100.0 * ladder_coverage,
            "side_counts": dict(all_sides),
            "minority_side_share": minority_all,
            "quote_missing": dict(quote_missing),
            "relevant_ladder_missing": dict(relevant_ladder_missing),
        },
        "by_year": by_year,
        "adjacent_stability": {
            "preopen_indication_09_29_50": preopen_stability,
            "continuous_observation_09_30_05": continuous_stability,
        },
        "returns_blind_control_distinctness": controls,
        "timestamp_observability": {
            "all_primary_information_before_09_30_05": primary_availability,
            "all_entry_and_exit_observations_after_signal": entry_after_signal,
        },
        "gates": gates,
        "gate_passed": all(gates.values()),
        "signals": signals,
        "executable_signal_dates": sorted(executable),
        "warning": "No actuator exit return, P&L, profit factor, or benchmark outcome was calculated.",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "development_signals": len(development),
        "development_trades_per_week": payload["development_2023_03_28_2023_12_31"]["trades_per_declared_calendar_week"],
        "all_signals": len(signals),
        "failed_gates": [name for name, passed in gates.items() if not passed],
        "output": str(OUTPUT.relative_to(ROOT)),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
