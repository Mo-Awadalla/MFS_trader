"""Returns-blind feasibility for leveraged-ETF opening-auction demand consensus v40."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

from research_scout import audit_cash_etf_new_data_v34 as technical
from research_scout import audit_spy_auction_absorption_failure_v35 as shared

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "leveraged_etf_opening_auction_demand_consensus_returns_blind_audit_v40.json"
SIGNAL_SYMBOLS = ["UPRO", "SPXU", "SSO", "SDS"]
ALL_STAT_SYMBOLS = ["SPY", "UPRO", "SPXU", "SSO", "SDS"]
PRIMARY_WINDOW = 20
ADJACENT_WINDOWS = [10, 40]
PRIMARY_ENTRY = "09:31:05"
DELAY_TARGETS = ["09:31:01", "09:32:00"]
EXIT_TARGET = "09:35:00"
POSITIVE_LADDER = ["SPY", "SSO", "UPRO"]
NEGATIVE_LADDER = ["SH", "SDS", "SPXU"]


def declared_weeks(start: str, end: str) -> float:
    return ((pd.Timestamp(end) - pd.Timestamp(start)).days + 1) / 7.0


def load_statistics() -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, float], dict[str, Any]]:
    frame = technical.db.read_dbn(technical.STATISTICS).to_df(map_symbols=True, tz="UTC").reset_index()
    frame["stat_name"] = frame["stat_type"].map(lambda value: technical.enum_name(technical.db.StatType, value))
    event = pd.to_datetime(frame["ts_event"], utc=True).dt.tz_convert("America/New_York")
    receive = pd.to_datetime(frame["ts_recv"], utc=True).dt.tz_convert("America/New_York")
    frame["event_ny"] = event
    frame["receive_ny"] = receive
    frame["session_date"] = event.dt.strftime("%Y-%m-%d")

    opening_frame = frame.loc[
        frame["stat_name"].eq("OPENING_PRICE") & frame["symbol"].astype(str).isin(ALL_STAT_SYMBOLS)
    ].copy()
    openings: dict[str, dict[str, dict[str, Any]]] = {}
    duplicate_openings: list[str] = []
    for (day, symbol), group in opening_frame.groupby(["session_date", "symbol"], sort=True):
        if len(group) != 1:
            duplicate_openings.append(f"{day}:{symbol}:{len(group)}")
            continue
        row = group.iloc[0]
        price = float(row["price"])
        quantity = int(row["quantity"])
        if price <= 0 or quantity <= 0:
            continue
        openings.setdefault(str(day), {})[str(symbol)] = {
            "price": price,
            "quantity": quantity,
            "ts_event": pd.Timestamp(row["ts_event"]).isoformat(),
            "ts_recv": pd.Timestamp(row["ts_recv"]).isoformat(),
            "event_ny": row["event_ny"].isoformat(),
            "receive_ny": row["receive_ny"].isoformat(),
            "publisher_id": int(row["publisher_id"]),
            "instrument_id": int(row["instrument_id"]),
        }

    close_frame = frame.loc[
        frame["stat_name"].eq("CLOSE_PRICE") & frame["symbol"].astype(str).eq("SPY")
    ].copy()
    closes: dict[str, float] = {}
    duplicate_closes: list[str] = []
    for day, group in close_frame.groupby("session_date", sort=True):
        if len(group) != 1:
            duplicate_closes.append(f"{day}:{len(group)}")
            continue
        price = float(group.iloc[0]["price"])
        if price > 0:
            closes[str(day)] = price

    ordered_close_days = sorted(closes)
    previous_close: dict[str, float] = {}
    for previous_day, current_day in zip(ordered_close_days, ordered_close_days[1:]):
        previous_close[current_day] = closes[previous_day]

    integrity = {
        "opening_rows": int(len(opening_frame)),
        "opening_sessions": int(opening_frame["session_date"].nunique()),
        "duplicate_opening_symbol_sessions": duplicate_openings,
        "spy_close_rows": int(len(close_frame)),
        "duplicate_spy_close_sessions": duplicate_closes,
    }
    return openings, previous_close, integrity


def build_actions(
    openings: dict[str, dict[str, dict[str, Any]]],
    excluded: set[str],
    window: int,
    previous_close: dict[str, float],
) -> tuple[dict[str, dict[str, Any]], int]:
    history: dict[str, list[int]] = {symbol: [] for symbol in SIGNAL_SYMBOLS}
    actions: dict[str, dict[str, Any]] = {}
    eligible_with_history = 0
    for day in sorted(openings):
        rows = openings[day]
        complete = all(symbol in rows for symbol in SIGNAL_SYMBOLS)
        warm = all(len(history[symbol]) >= window for symbol in SIGNAL_SYMBOLS)
        if complete and warm and day not in excluded:
            eligible_with_history += 1
            surprises = {
                symbol: rows[symbol]["quantity"] / float(median(history[symbol][-window:]))
                for symbol in SIGNAL_SYMBOLS
            }
            bullish = surprises["UPRO"] > surprises["SPXU"] and surprises["SSO"] > surprises["SDS"]
            bearish = surprises["UPRO"] < surprises["SPXU"] and surprises["SSO"] < surprises["SDS"]
            if bullish or bearish:
                side = "B" if bullish else "A"
                signal_receive = max(pd.Timestamp(rows[symbol]["ts_recv"]) for symbol in SIGNAL_SYMBOLS)
                signal_event = max(pd.Timestamp(rows[symbol]["ts_event"]) for symbol in SIGNAL_SYMBOLS)
                spy_open = rows.get("SPY", {}).get("price")
                prior_close = previous_close.get(day)
                spy_overnight = float(spy_open) / prior_close - 1.0 if spy_open and prior_close else None
                actions[day] = {
                    "side": side,
                    "symbol": "UPRO" if side == "B" else "SPXU",
                    "window": window,
                    "surprises": surprises,
                    "quantities": {symbol: rows[symbol]["quantity"] for symbol in SIGNAL_SYMBOLS},
                    "trailing_medians": {symbol: float(median(history[symbol][-window:])) for symbol in SIGNAL_SYMBOLS},
                    "spy_official_overnight_return": spy_overnight,
                    "signal_ts_event": signal_event.isoformat(),
                    "signal_ts_recv": signal_receive.isoformat(),
                    "statistic_times": {
                        symbol: {"ts_event": rows[symbol]["ts_event"], "ts_recv": rows[symbol]["ts_recv"]}
                        for symbol in SIGNAL_SYMBOLS
                    },
                }
        if complete and day not in excluded:
            for symbol in SIGNAL_SYMBOLS:
                history[symbol].append(int(rows[symbol]["quantity"]))
    return actions, eligible_with_history


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
    quote_payload = shared.load_json(shared.TARGET_QUOTES)
    audit = shared.load_json(shared.AUDIT)
    if any(payload.get("returns_read") is not False for payload in [quote_payload, audit]):
        raise RuntimeError("Returns-blind source artifact is not marked clean")
    quotes = shared.quote_map(quote_payload)
    excluded = set(audit["degraded_dates"]["ARCX.PILLAR"]) | set(audit["degraded_dates"]["EQUS.MINI"])
    openings, previous_close, statistic_integrity = load_statistics()
    primary, eligible_sessions = build_actions(openings, excluded, PRIMARY_WINDOW, previous_close)
    adjacent = {
        window: build_actions(openings, excluded, window, previous_close)[0]
        for window in ADJACENT_WINDOWS
    }

    executable: dict[str, dict[str, Any]] = {}
    quote_missing: Counter[str] = Counter()
    delay_available: Counter[str] = Counter()
    relevant_ladder_days = 0
    relevant_ladder_missing: Counter[str] = Counter()
    entry_after_signal = True
    for day, signal in primary.items():
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
        signal_recv = pd.Timestamp(signal["signal_ts_recv"])
        if not all(pd.Timestamp(quote["ts_recv"]) > signal_recv for quote in row["quotes"].values()):
            entry_after_signal = False
            continue
        entry = row["quotes"][PRIMARY_ENTRY]
        row["entry_spread_bps"] = (entry["ask"] - entry["bid"]) / ((entry["ask"] + entry["bid"]) / 2.0) * 10_000.0
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

    feature_dev = [day for day in primary if "2021-01-01" <= day <= "2023-12-31"]
    executable_dev = [day for day in executable if "2023-03-28" <= day <= "2023-12-31"]
    feature_sides = Counter(primary[day]["side"] for day in feature_dev)
    executable_sides = Counter(executable[day]["side"] for day in executable_dev)
    minority_feature = min(feature_sides.values()) / max(sum(feature_sides.values()), 1) if len(feature_sides) == 2 else 0.0
    minority_executable = min(executable_sides.values()) / max(sum(executable_sides.values()), 1) if len(executable_sides) == 2 else 0.0
    by_year = {
        str(year): {
            "signals": sum(day.startswith(str(year)) for day in primary),
            "executable_signals": sum(day.startswith(str(year)) for day in executable),
            "side_counts": dict(Counter(signal["side"] for day, signal in primary.items() if day.startswith(str(year)))),
        }
        for year in range(2021, 2027)
    }
    overlap_signals = sum("2023-03-28" <= day <= "2026-07-24" for day in primary)
    quote_coverage = len(executable) / max(overlap_signals, 1)
    ladder_coverage = relevant_ladder_days / max(len(executable), 1)
    selection_share = len(primary) / max(eligible_sessions, 1)
    stability = {str(window): compare_actions(primary, mapping) for window, mapping in adjacent.items()}
    overnight_agreement = 100.0 * sum(
        signal["spy_official_overnight_return"] is not None
        and ((signal["spy_official_overnight_return"] > 0 and signal["side"] == "B") or (signal["spy_official_overnight_return"] < 0 and signal["side"] == "A"))
        for signal in primary.values()
    ) / max(sum(signal["spy_official_overnight_return"] not in {None, 0} for signal in primary.values()), 1)
    statistics_before_cutoff = all(
        pd.Timestamp(signal["signal_ts_event"]).tz_convert("America/New_York").time() < pd.Timestamp("09:30:05").time()
        and pd.Timestamp(signal["signal_ts_recv"]).tz_convert("America/New_York").time() < pd.Timestamp("09:30:05").time()
        for signal in primary.values()
    )
    quantities_positive = all(all(value > 0 for value in signal["quantities"].values()) for signal in primary.values())

    gates = {
        "feature_frequency_at_least_two_per_declared_week_2021_2023": len(feature_dev) / declared_weeks("2021-01-01", "2023-12-31") >= 2.0,
        "executable_frequency_at_least_two_per_declared_week_2023_overlap": len(executable_dev) / declared_weeks("2023-03-28", "2023-12-31") >= 2.0,
        "development_year_signal_minimums_2021_80_2022_100_2023_100": by_year["2021"]["signals"] >= 80 and by_year["2022"]["signals"] >= 100 and by_year["2023"]["signals"] >= 100,
        "at_least_20_feature_signals_2026_extension": by_year["2026"]["signals"] >= 20,
        "minority_direction_at_least_20pct_feature_and_executable_development": minority_feature >= 0.20 and minority_executable >= 0.20,
        "upro_and_spxu_each_executable_in_development": len(executable_sides) == 2 and all(value > 0 for value in executable_sides.values()),
        "primary_entry_exit_quote_coverage_at_least_90pct": quote_coverage >= 0.90,
        "relevant_side_ladder_09_31_05_availability_at_least_80pct": ladder_coverage >= 0.80,
        "rolling_10_identical_action_including_cash_at_least_70pct": stability["10"]["identical_action_including_cash_pct"] >= 70.0,
        "rolling_40_identical_action_including_cash_at_least_70pct": stability["40"]["identical_action_including_cash_pct"] >= 70.0,
        "not_redundant_to_spy_official_overnight_direction_below_80pct": overnight_agreement < 80.0,
        "pair_consensus_selects_between_20_and_80pct_eligible_sessions": 0.20 <= selection_share <= 0.80,
        "statistics_unique_received_before_09_30_05_and_entries_after_signal": not statistic_integrity["duplicate_opening_symbol_sessions"] and statistics_before_cutoff and entry_after_signal,
        "all_selected_quantities_positive": quantities_positive,
    }

    payload = {
        "status": "passed_returns_blind_feasibility" if all(gates.values()) else "failed_returns_blind_feasibility_no_pnl_opened",
        "returns_read": False,
        "rule": {
            "quantity_source": "ARCX OPENING_PRICE statistic quantity",
            "rolling_window_sessions": PRIMARY_WINDOW,
            "condition": "UPRO-vs-SPXU and SSO-vs-SDS own-history quantity surprises agree",
            "direction": "pair consensus",
            "actuator": "bullish -> UPRO; bearish -> SPXU",
            "primary_entry_target": PRIMARY_ENTRY,
            "delay_diagnostics": DELAY_TARGETS,
            "exit_target": EXIT_TARGET,
            "maximum_event_wait_seconds": 60,
        },
        "degraded_dates_excluded_union": sorted(excluded),
        "statistic_integrity": statistic_integrity,
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
        "by_year": by_year,
        "rolling_window_stability": stability,
        "returns_blind_controls": {
            "spy_official_overnight_direction_agreement_pct": overnight_agreement,
            "eligible_sessions_with_primary_history": eligible_sessions,
            "selected_signal_sessions": len(primary),
            "selection_share_pct": 100.0 * selection_share,
        },
        "timestamp_observability": {
            "all_signal_statistics_before_09_30_05": statistics_before_cutoff,
            "all_entry_and_exit_observations_after_signal": entry_after_signal,
        },
        "gates": gates,
        "gate_passed": all(gates.values()),
        "signals": primary,
        "executable_signal_dates": sorted(executable),
        "warning": "No post-entry return, P&L, profit factor, benchmark, or placebo outcome was calculated.",
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
