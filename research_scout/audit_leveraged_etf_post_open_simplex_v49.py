"""Returns-blind feasibility for the synchronized post-open fair-value simplex v49."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

from research_scout import audit_spy_auction_absorption_failure_v35 as shared
from research_scout import audit_leveraged_etf_official_open_basis_v48 as v48

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "leveraged_etf_post_open_simplex_returns_blind_audit_v49.json"
SYMBOLS = ["SPY", "SSO", "UPRO", "SH", "SDS", "SPXU"]
PRIMARY_OBSERVATION = "09:30:05"
ADJACENT_OBSERVATION = "09:30:01"
SIGNAL_BOUNDARY = pd.Timestamp("2026-01-01 09:31:00").time()
ENTRY_TARGETS = ["09:31:01", "09:31:05", "09:32:00"]
PRIMARY_ENTRY = "09:31:05"
EXIT_TARGET = "09:35:00"
PRIMARY_WINDOW = 20
ADJACENT_WINDOWS = [10, 40]
MAX_FEATURE_EVENT_WAIT_SECONDS = 5.0
MAX_FEATURE_EVENT_SPAN_SECONDS = 5.0
MAX_EXECUTION_EVENT_WAIT_SECONDS = 60.0


def declared_weeks(start: str, end: str) -> float:
    return ((pd.Timestamp(end) - pd.Timestamp(start)).days + 1) / 7.0


def load_openings() -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, Any]]:
    openings, _, integrity = v48.load_statistics()
    return openings, integrity


def feature_rows(
    openings: dict[str, dict[str, dict[str, Any]]],
    quotes: dict[tuple[str, str, str], dict[str, Any]],
    excluded: set[str],
    observation: str,
    window: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], Counter[str]]:
    upro_history: list[float] = []
    spxu_history: list[float] = []
    actions: dict[str, dict[str, Any]] = {}
    eligible: dict[str, dict[str, Any]] = {}
    exclusions: Counter[str] = Counter()

    for day in sorted(openings):
        if day in excluded or not "2023-03-28" <= day <= "2026-07-24":
            continue
        open_rows = openings[day]
        if not all(symbol in open_rows for symbol in SYMBOLS):
            exclusions["incomplete_official_open"] += 1
            continue
        keys = [(day, symbol, observation) for symbol in SYMBOLS]
        if not all(key in quotes and not quotes[key]["equs_degraded"] for key in keys):
            exclusions["incomplete_six_symbol_tbbo"] += 1
            continue
        quote_rows = {symbol: quotes[(day, symbol, observation)] for symbol in SYMBOLS}
        if any(float(row["event_wait_seconds"]) > MAX_FEATURE_EVENT_WAIT_SECONDS for row in quote_rows.values()):
            exclusions["feature_event_wait_over_5s"] += 1
            continue
        event_times = [pd.Timestamp(row["ts_event"]) for row in quote_rows.values()]
        event_span = (max(event_times) - min(event_times)).total_seconds()
        if event_span > MAX_FEATURE_EVENT_SPAN_SECONDS:
            exclusions["cross_symbol_event_span_over_5s"] += 1
            continue
        receive_times = [pd.Timestamp(row["ts_recv"]) for row in quote_rows.values()]
        opening_receive_times = [
            pd.Timestamp(open_rows[symbol]["ts_recv"]) for symbol in SYMBOLS
        ]
        if any(ts.tz_convert("America/New_York").time() >= SIGNAL_BOUNDARY for ts in receive_times + opening_receive_times):
            exclusions["not_observable_before_09_31"] += 1
            continue

        mids = {
            symbol: (float(quote_rows[symbol]["bid"]) + float(quote_rows[symbol]["ask"])) / 2.0
            for symbol in SYMBOLS
        }
        returns = {
            symbol: mids[symbol] / float(open_rows[symbol]["price"]) - 1.0
            for symbol in SYMBOLS
        }
        consensus = median(
            [
                returns["SPY"],
                returns["SSO"] / 2.0,
                -returns["SH"],
                -returns["SDS"] / 2.0,
            ]
        )
        upro_residual = 3.0 * consensus - returns["UPRO"]
        spxu_residual = -3.0 * consensus - returns["SPXU"]
        if len(upro_history) >= window and len(spxu_history) >= window:
            upro_excess = upro_residual - median(upro_history[-window:])
            spxu_excess = spxu_residual - median(spxu_history[-window:])
            eligible[day] = {
                "observation": observation,
                "window": window,
                "consensus": consensus,
                "returns": returns,
                "upro_residual": upro_residual,
                "spxu_residual": spxu_residual,
                "upro_excess": upro_excess,
                "spxu_excess": spxu_excess,
                "feature_event_span_seconds": event_span,
                "feature_event_wait_seconds": {
                    symbol: float(quote_rows[symbol]["event_wait_seconds"])
                    for symbol in SYMBOLS
                },
                "feature_quote_ts_event": {
                    symbol: quote_rows[symbol]["ts_event"] for symbol in SYMBOLS
                },
                "feature_quote_ts_recv": {
                    symbol: quote_rows[symbol]["ts_recv"] for symbol in SYMBOLS
                },
            }
            upro_signal = upro_excess > 0
            spxu_signal = spxu_excess > 0
            if upro_signal ^ spxu_signal:
                symbol = "UPRO" if upro_signal else "SPXU"
                actions[day] = {
                    **eligible[day],
                    "symbol": symbol,
                    "side": "B" if symbol == "UPRO" else "A",
                    "selected_excess": upro_excess if upro_signal else spxu_excess,
                }
        upro_history.append(upro_residual)
        spxu_history.append(spxu_residual)
    return actions, eligible, exclusions


def compare(primary: dict[str, dict[str, Any]], alternative: dict[str, dict[str, Any]]) -> dict[str, Any]:
    joint = set(primary) & set(alternative)
    union = set(primary) | set(alternative)
    return {
        "signals": len(alternative),
        "joint_signal_days": len(joint),
        "direction_agreement_on_joint_pct": 100.0
        * sum(primary[day]["symbol"] == alternative[day]["symbol"] for day in joint)
        / max(len(joint), 1),
        "identical_action_including_cash_pct": 100.0
        * sum((primary.get(day) or {}).get("symbol") == (alternative.get(day) or {}).get("symbol") for day in union)
        / max(len(union), 1),
    }


def main() -> int:
    audit = shared.load_json(shared.AUDIT)
    quote_payload = shared.load_json(shared.TARGET_QUOTES)
    if audit.get("returns_read") is not False or quote_payload.get("returns_read") is not False:
        raise RuntimeError("Returns-blind source artifact is invalid")
    excluded = set(audit["degraded_dates"]["ARCX.PILLAR"]) | set(audit["degraded_dates"]["EQUS.MINI"])
    quotes = shared.quote_map(quote_payload)
    openings, statistic_integrity = load_openings()
    primary, eligible, exclusions = feature_rows(
        openings, quotes, excluded, PRIMARY_OBSERVATION, PRIMARY_WINDOW
    )
    adjacent_clock, _, adjacent_clock_exclusions = feature_rows(
        openings, quotes, excluded, ADJACENT_OBSERVATION, PRIMARY_WINDOW
    )
    adjacent_windows = {
        window: feature_rows(openings, quotes, excluded, PRIMARY_OBSERVATION, window)[0]
        for window in ADJACENT_WINDOWS
    }

    execution_complete: dict[str, dict[str, Any]] = {}
    execution_missing: Counter[str] = Counter()
    execution_after_boundary = True
    for day, signal in primary.items():
        symbol = signal["symbol"]
        required = [(day, symbol, target) for target in ENTRY_TARGETS + [EXIT_TARGET]]
        if not all(key in quotes and not quotes[key]["equs_degraded"] for key in required):
            for key in required:
                if key not in quotes:
                    execution_missing[f"{symbol}:{key[2]}"] += 1
            continue
        selected = {target: quotes[(day, symbol, target)] for target in ENTRY_TARGETS + [EXIT_TARGET]}
        if any(float(row["event_wait_seconds"]) > MAX_EXECUTION_EVENT_WAIT_SECONDS for row in selected.values()):
            execution_missing[f"{symbol}:wait_over_60s"] += 1
            continue
        if any(
            pd.Timestamp(selected[target]["ts_recv"]).tz_convert("America/New_York").time()
            <= SIGNAL_BOUNDARY
            for target in ENTRY_TARGETS
        ):
            execution_after_boundary = False
            continue
        execution_complete[day] = {
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
        day: row for day, row in primary.items() if "2023-03-28" <= day <= "2023-12-31"
    }
    executable_development = {
        day: row for day, row in execution_complete.items() if "2023-03-28" <= day <= "2023-12-31"
    }
    dev_sides = Counter(row["side"] for row in development.values())
    exec_sides = Counter(primary[day]["side"] for day in executable_development)
    minority_dev = min(dev_sides.values()) / max(sum(dev_sides.values()), 1) if len(dev_sides) == 2 else 0.0
    minority_exec = min(exec_sides.values()) / max(sum(exec_sides.values()), 1) if len(exec_sides) == 2 else 0.0
    extension_signals = sum(day.startswith("2026") for day in primary)
    execution_coverage = len(execution_complete) / max(len(primary), 1)
    selection_share = len(primary) / max(len(eligible), 1)
    clock_stability = compare(primary, adjacent_clock)
    window_stability = {
        str(window): compare(primary, actions)
        for window, actions in adjacent_windows.items()
    }

    gates = {
        "development_feature_frequency_at_least_two_per_week": len(development)
        / declared_weeks("2023-03-28", "2023-12-31")
        >= 2.0,
        "at_least_80_development_feature_signals": len(development) >= 80,
        "at_least_20_signals_in_2026": extension_signals >= 20,
        "both_actuators_and_minority_at_least_20pct": len(dev_sides) == 2 and minority_dev >= 0.20,
        "execution_coverage_at_least_90pct": execution_coverage >= 0.90,
        "executable_development_frequency_at_least_two_per_week": len(executable_development)
        / declared_weeks("2023-03-28", "2023-12-31")
        >= 2.0,
        "executable_both_actuators_and_minority_at_least_20pct": len(exec_sides) == 2
        and minority_exec >= 0.20,
        "adjacent_clock_identical_action_including_cash_at_least_60pct": clock_stability[
            "identical_action_including_cash_pct"
        ]
        >= 60.0,
        "rolling_10_identical_action_including_cash_at_least_70pct": window_stability["10"][
            "identical_action_including_cash_pct"
        ]
        >= 70.0,
        "rolling_40_identical_action_including_cash_at_least_70pct": window_stability["40"][
            "identical_action_including_cash_pct"
        ]
        >= 70.0,
        "selection_share_between_20_and_80pct": 0.20 <= selection_share <= 0.80,
        "all_entries_after_signal_boundary": execution_after_boundary,
        "statistics_unique_and_positive": not statistic_integrity["duplicate_symbol_sessions"]
        and not statistic_integrity["invalid_prices"],
    }
    passed = all(gates.values())
    payload = {
        "status": "pass_returns_blind_feasibility_authorize_preregistration"
        if passed
        else "fail_returns_blind_feasibility_no_pnl",
        "returns_read": False,
        "pnl_calculated": False,
        "rule": {
            "official_open_anchor": "ARCX OPENING_PRICE",
            "primary_observation": PRIMARY_OBSERVATION,
            "signal_boundary": "09:31:00",
            "primary_window": PRIMARY_WINDOW,
            "feature_event_wait_cap_seconds": MAX_FEATURE_EVENT_WAIT_SECONDS,
            "cross_symbol_event_span_cap_seconds": MAX_FEATURE_EVENT_SPAN_SECONDS,
            "entry_targets": ENTRY_TARGETS,
            "primary_entry": PRIMARY_ENTRY,
            "exit_target": EXIT_TARGET,
        },
        "degraded_dates_excluded_union": sorted(excluded),
        "statistic_integrity": statistic_integrity,
        "feature_exclusions": dict(exclusions),
        "adjacent_clock_exclusions": dict(adjacent_clock_exclusions),
        "development_2023_overlap": {
            "signals": len(development),
            "signals_per_declared_week": len(development)
            / declared_weeks("2023-03-28", "2023-12-31"),
            "side_counts": dict(dev_sides),
            "minority_share": minority_dev,
        },
        "all_periods": {
            "synchronized_warm_sessions": len(eligible),
            "signals": len(primary),
            "selection_share": selection_share,
            "execution_complete": len(execution_complete),
            "execution_coverage": execution_coverage,
            "extension_2026_signals": extension_signals,
        },
        "executable_development_2023_overlap": {
            "signals": len(executable_development),
            "signals_per_declared_week": len(executable_development)
            / declared_weeks("2023-03-28", "2023-12-31"),
            "side_counts": dict(exec_sides),
            "minority_share": minority_exec,
        },
        "stability": {
            "adjacent_09_30_01": clock_stability,
            "rolling_windows": window_stability,
        },
        "execution_missing": dict(execution_missing),
        "timestamp_observability": {
            "all_entries_after_09_31_signal_boundary": execution_after_boundary,
        },
        "gates": gates,
        "gate_passed": passed,
        "signals": primary,
        "executable_signal_dates": sorted(execution_complete),
        "warning": "No post-entry return, P&L, profit factor, benchmark, or placebo outcome was calculated.",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "development_signals": len(development),
                "development_per_week": payload["development_2023_overlap"][
                    "signals_per_declared_week"
                ],
                "feature_exclusions": dict(exclusions),
                "failed_gates": [name for name, value in gates.items() if not value],
                "output": str(OUTPUT.relative_to(ROOT)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
