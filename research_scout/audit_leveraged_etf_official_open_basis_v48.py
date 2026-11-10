"""Returns-blind feature feasibility for official-open 3x basis catch-up v48."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

from research_scout import audit_cash_etf_new_data_v34 as technical
from research_scout import audit_spy_auction_absorption_failure_v35 as shared

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "leveraged_etf_official_open_basis_returns_blind_audit_v48.json"
SYMBOLS = ["SPY", "SSO", "UPRO", "SH", "SDS", "SPXU"]
PRIMARY_WINDOW = 20
ADJACENT_WINDOWS = [10, 40]
CORPORATE_ACTION_RETURN_CAP = 0.25
SIGNAL_BOUNDARY = "09:30:01"
PREFLIGHT_TARGETS = ["09:30:01", "09:30:05", "09:31:00", "09:35:00"]


def declared_weeks(start: str, end: str) -> float:
    return ((pd.Timestamp(end) - pd.Timestamp(start)).days + 1) / 7.0


def load_statistics() -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, dict[str, float]], dict[str, Any]]:
    frame = technical.db.read_dbn(technical.STATISTICS).to_df(map_symbols=True, tz="UTC").reset_index()
    frame["stat_name"] = frame["stat_type"].map(lambda value: technical.enum_name(technical.db.StatType, value))
    frame["event_ny"] = pd.to_datetime(frame["ts_event"], utc=True).dt.tz_convert("America/New_York")
    frame["receive_ny"] = pd.to_datetime(frame["ts_recv"], utc=True).dt.tz_convert("America/New_York")
    frame["session_date"] = frame["event_ny"].dt.strftime("%Y-%m-%d")
    selected = frame.loc[
        frame["stat_name"].isin(["OPENING_PRICE", "CLOSE_PRICE"])
        & frame["symbol"].astype(str).isin(SYMBOLS)
    ].copy()

    by_kind: dict[str, dict[str, dict[str, Any]]] = {"OPENING_PRICE": {}, "CLOSE_PRICE": {}}
    duplicates: list[str] = []
    invalid: list[str] = []
    for (kind, day, symbol), group in selected.groupby(["stat_name", "session_date", "symbol"], sort=True):
        key = f"{kind}:{day}:{symbol}"
        if len(group) != 1:
            duplicates.append(f"{key}:{len(group)}")
            continue
        row = group.iloc[0]
        price = float(row["price"])
        if not math.isfinite(price) or price <= 0:
            invalid.append(key)
            continue
        by_kind[str(kind)].setdefault(str(day), {})[str(symbol)] = {
            "price": price,
            "ts_event": pd.Timestamp(row["ts_event"]).isoformat(),
            "ts_recv": pd.Timestamp(row["ts_recv"]).isoformat(),
            "event_ny": row["event_ny"].isoformat(),
            "receive_ny": row["receive_ny"].isoformat(),
        }

    closes = by_kind["CLOSE_PRICE"]
    complete_close_days = [day for day in sorted(closes) if all(symbol in closes[day] for symbol in SYMBOLS)]
    previous_closes: dict[str, dict[str, float]] = {}
    for previous_day, current_day in zip(complete_close_days, complete_close_days[1:]):
        previous_closes[current_day] = {
            symbol: float(closes[previous_day][symbol]["price"]) for symbol in SYMBOLS
        }
    integrity = {
        "rows_selected": int(len(selected)),
        "duplicate_symbol_sessions": duplicates,
        "invalid_prices": invalid,
        "complete_opening_sessions": sum(
            all(symbol in rows for symbol in SYMBOLS)
            for rows in by_kind["OPENING_PRICE"].values()
        ),
        "complete_closing_sessions": len(complete_close_days),
    }
    return by_kind["OPENING_PRICE"], previous_closes, integrity


def build_actions(
    openings: dict[str, dict[str, dict[str, Any]]],
    previous_closes: dict[str, dict[str, float]],
    excluded: set[str],
    window: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], int]:
    positive_history: list[float] = []
    negative_history: list[float] = []
    actions: dict[str, dict[str, Any]] = {}
    eligible_rows: dict[str, dict[str, Any]] = {}
    integrity_exclusions = 0

    for day in sorted(openings):
        rows = openings[day]
        prior = previous_closes.get(day)
        if day in excluded or prior is None or not all(symbol in rows for symbol in SYMBOLS):
            continue
        returns = {
            symbol: float(rows[symbol]["price"]) / float(prior[symbol]) - 1.0
            for symbol in SYMBOLS
        }
        if any(not math.isfinite(value) or abs(value) > CORPORATE_ACTION_RETURN_CAP for value in returns.values()):
            integrity_exclusions += 1
            continue

        positive_basis = median([returns["SPY"], returns["SSO"] / 2.0]) - returns["UPRO"] / 3.0
        negative_basis = median([-returns["SPY"], returns["SH"], returns["SDS"] / 2.0]) - returns["SPXU"] / 3.0
        if len(positive_history) >= window and len(negative_history) >= window:
            positive_baseline = median(positive_history[-window:])
            negative_baseline = median(negative_history[-window:])
            positive_excess = positive_basis - positive_baseline
            negative_excess = negative_basis - negative_baseline
            positive_signal = (
                returns["SPY"] > 0
                and returns["SSO"] > 0
                and returns["UPRO"] > 0
                and positive_excess > 0
            )
            negative_signal = (
                returns["SPY"] < 0
                and returns["SH"] > 0
                and returns["SDS"] > 0
                and returns["SPXU"] > 0
                and negative_excess > 0
            )
            signal_receive = max(pd.Timestamp(rows[symbol]["ts_recv"]) for symbol in SYMBOLS)
            signal_event = max(pd.Timestamp(rows[symbol]["ts_event"]) for symbol in SYMBOLS)
            eligible_rows[day] = {
                "returns": returns,
                "positive_basis": positive_basis,
                "negative_basis": negative_basis,
                "positive_baseline": positive_baseline,
                "negative_baseline": negative_baseline,
                "positive_excess": positive_excess,
                "negative_excess": negative_excess,
                "signal_ts_event": signal_event.isoformat(),
                "signal_ts_recv": signal_receive.isoformat(),
            }
            if positive_signal ^ negative_signal:
                side = "B" if positive_signal else "A"
                basis_excess = positive_excess if positive_signal else negative_excess
                actions[day] = {
                    **eligible_rows[day],
                    "side": side,
                    "symbol": "UPRO" if side == "B" else "SPXU",
                    "basis_excess": basis_excess,
                    "window": window,
                    "statistic_times": {
                        symbol: {
                            "ts_event": rows[symbol]["ts_event"],
                            "ts_recv": rows[symbol]["ts_recv"],
                        }
                        for symbol in SYMBOLS
                    },
                }
        positive_history.append(positive_basis)
        negative_history.append(negative_basis)
    return actions, eligible_rows, integrity_exclusions


def compare_actions(primary: dict[str, dict[str, Any]], alternative: dict[str, dict[str, Any]]) -> dict[str, Any]:
    joint = set(primary) & set(alternative)
    union = set(primary) | set(alternative)
    return {
        "signals": len(alternative),
        "joint_signal_days": len(joint),
        "direction_agreement_on_joint_pct": 100.0
        * sum(primary[day]["side"] == alternative[day]["side"] for day in joint)
        / max(len(joint), 1),
        "identical_action_including_cash_pct": 100.0
        * sum((primary.get(day) or {}).get("side") == (alternative.get(day) or {}).get("side") for day in union)
        / max(len(union), 1),
    }


def pearson_abs_gap_basis(rows: dict[str, dict[str, Any]]) -> float | None:
    if len(rows) < 3:
        return None
    frame = pd.DataFrame(
        [
            {
                "gap": abs(row["returns"]["SPY"]),
                "excess": row["basis_excess"],
            }
            for row in rows.values()
        ]
    )
    value = frame["gap"].corr(frame["excess"])
    return None if pd.isna(value) else float(value)


def main() -> int:
    audit = shared.load_json(shared.AUDIT)
    quote_payload = shared.load_json(shared.TARGET_QUOTES)
    if audit.get("returns_read") is not False or quote_payload.get("returns_read") is not False:
        raise RuntimeError("Returns-blind sources are not marked clean")
    excluded = set(audit["degraded_dates"]["ARCX.PILLAR"]) | set(audit["degraded_dates"]["EQUS.MINI"])
    openings, previous_closes, statistic_integrity = load_statistics()
    primary, eligible, integrity_exclusions = build_actions(
        openings, previous_closes, excluded, PRIMARY_WINDOW
    )
    adjacent = {
        window: build_actions(openings, previous_closes, excluded, window)[0]
        for window in ADJACENT_WINDOWS
    }
    stability = {
        str(window): compare_actions(primary, actions)
        for window, actions in adjacent.items()
    }

    feature_development = {
        day: row for day, row in primary.items() if "2021-01-01" <= day <= "2023-12-31"
    }
    side_counts = Counter(row["side"] for row in feature_development.values())
    minority_share = (
        min(side_counts.values()) / max(sum(side_counts.values()), 1)
        if len(side_counts) == 2
        else 0.0
    )
    by_year = {
        str(year): {
            "signals": sum(day.startswith(str(year)) for day in primary),
            "side_counts": dict(
                Counter(row["side"] for day, row in primary.items() if day.startswith(str(year)))
            ),
        }
        for year in range(2021, 2027)
    }
    selected_correlation = pearson_abs_gap_basis(primary)
    all_received_before_boundary = all(
        pd.Timestamp(row["signal_ts_recv"]).tz_convert("America/New_York").time()
        < pd.Timestamp(SIGNAL_BOUNDARY).time()
        for row in primary.values()
    )

    quotes = shared.quote_map(quote_payload)
    overlap = {
        day: row for day, row in primary.items() if "2023-03-28" <= day <= "2026-07-24"
    }
    preflight_complete = 0
    preflight_ladder_complete = 0
    for day, row in overlap.items():
        actuator_keys = [(day, row["symbol"], target) for target in PREFLIGHT_TARGETS]
        if all(key in quotes and not quotes[key]["equs_degraded"] for key in actuator_keys):
            preflight_complete += 1
            ladder = ["SPY", "SSO", "UPRO"] if row["side"] == "B" else ["SH", "SDS", "SPXU"]
            ladder_keys = [(day, symbol, "09:30:05") for symbol in ladder]
            if all(key in quotes and not quotes[key]["equs_degraded"] for key in ladder_keys):
                preflight_ladder_complete += 1
    preflight_coverage = preflight_complete / max(len(overlap), 1)
    preflight_ladder_coverage = preflight_ladder_complete / max(preflight_complete, 1)
    selection_share = len(primary) / max(len(eligible), 1)

    gates = {
        "feature_frequency_at_least_two_per_declared_week_2021_2023": len(feature_development)
        / declared_weeks("2021-01-01", "2023-12-31")
        >= 2.0,
        "at_least_100_signals_each_full_development_year": all(
            by_year[str(year)]["signals"] >= 100 for year in [2021, 2022, 2023]
        ),
        "minority_actuator_at_least_20pct_and_both_present": len(side_counts) == 2
        and minority_share >= 0.20,
        "at_least_20_signals_in_2026_extension": by_year["2026"]["signals"] >= 20,
        "selection_share_between_20_and_80pct": 0.20 <= selection_share <= 0.80,
        "rolling_10_identical_action_including_cash_at_least_70pct": stability["10"][
            "identical_action_including_cash_pct"
        ]
        >= 70.0,
        "rolling_40_identical_action_including_cash_at_least_70pct": stability["40"][
            "identical_action_including_cash_pct"
        ]
        >= 70.0,
        "absolute_gap_basis_excess_correlation_below_0_80": selected_correlation is not None
        and abs(selected_correlation) < 0.80,
        "statistics_unique_positive_and_received_before_09_30_01": not statistic_integrity[
            "duplicate_symbol_sessions"
        ]
        and not statistic_integrity["invalid_prices"]
        and all_received_before_boundary,
        "fixed_clock_quote_preflight_coverage_at_least_80pct": preflight_coverage >= 0.80,
        "relevant_ladder_quote_preflight_at_least_70pct": preflight_ladder_coverage >= 0.70,
    }
    feature_gate_passed = all(gates.values())
    payload = {
        "status": "pass_feature_gate_authorize_exact_quote_extraction"
        if feature_gate_passed
        else "fail_returns_blind_feature_gate_no_pnl",
        "returns_read": False,
        "pnl_calculated": False,
        "rule": {
            "source": "ARCX official OPENING_PRICE and prior official CLOSE_PRICE",
            "rolling_window": PRIMARY_WINDOW,
            "corporate_action_return_cap": CORPORATE_ACTION_RETURN_CAP,
            "signal_boundary": SIGNAL_BOUNDARY,
            "actuator": "positive-ladder residual -> UPRO; inverse-ladder residual -> SPXU",
        },
        "degraded_dates_excluded_union": sorted(excluded),
        "statistic_integrity": statistic_integrity,
        "integrity_cap_exclusions": integrity_exclusions,
        "feature_development_2021_2023": {
            "signals": len(feature_development),
            "signals_per_declared_week": len(feature_development)
            / declared_weeks("2021-01-01", "2023-12-31"),
            "side_counts": dict(side_counts),
            "minority_share": minority_share,
        },
        "by_year": by_year,
        "eligible_warm_sessions": len(eligible),
        "selected_sessions": len(primary),
        "selection_share": selection_share,
        "rolling_window_stability": stability,
        "returns_blind_controls": {
            "pearson_abs_spy_gap_vs_selected_basis_excess": selected_correlation,
        },
        "timestamp_observability": {
            "all_selected_statistics_received_before_09_30_01": all_received_before_boundary,
        },
        "fixed_clock_quote_preflight": {
            "targets": PREFLIGHT_TARGETS,
            "overlap_signals": len(overlap),
            "complete_actuator_sessions": preflight_complete,
            "coverage": preflight_coverage,
            "relevant_ladder_complete_sessions": preflight_ladder_complete,
            "relevant_ladder_coverage": preflight_ladder_coverage,
            "warning": "Preflight only. Exact 1/5/60-second quote extraction remains mandatory.",
        },
        "gates": gates,
        "feature_gate_passed": feature_gate_passed,
        "signals": primary,
        "warning": "No post-entry return, exit bid, P&L, benchmark, or placebo outcome was calculated.",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "development_signals": len(feature_development),
                "signals_per_week": payload["feature_development_2021_2023"][
                    "signals_per_declared_week"
                ],
                "side_counts": dict(side_counts),
                "failed_gates": [name for name, passed in gates.items() if not passed],
                "output": str(OUTPUT.relative_to(ROOT)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
