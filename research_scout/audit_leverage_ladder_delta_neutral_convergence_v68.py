"""Returns-blind audit of same-issuer leverage-ladder convergence v68."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_scout import audit_proshares_primary_market_flows_v60 as flowlib
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay
from research_scout import test_upro_spxu_creative_hypotheses as base

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research_scout"
    / "leverage_ladder_delta_neutral_convergence_returns_blind_audit_v68.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "LEVERAGE_LADDER_DELTA_NEUTRAL_CONVERGENCE_AUDIT_V68.md"
)

START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")
SIGNAL_CLOCK = "09:32"
ADJACENT_CLOCKS = ("09:31", "09:33")
ENTRY_CLOCK = "09:33"
EXIT_CLOCK = "10:30"
RETURN_CAP = 0.25
FUNDS = {
    "UPRO": 3.0,
    "SSO": 2.0,
    "SPXU": -3.0,
    "SDS": -2.0,
}
LADDERS = {
    "positive": ("UPRO", "SSO"),
    "inverse": ("SPXU", "SDS"),
}


def sign(value: float) -> int:
    return int(value > 0) - int(value < 0)


def clock_stamp(day: pd.Timestamp, clock: str, timezone: Any) -> pd.Timestamp:
    hour, minute = (int(part) for part in clock.split(":"))
    return day.tz_localize(timezone) + pd.Timedelta(hours=hour, minutes=minute)


def point_in_time_nav(
    symbol: str,
    source_date: pd.Timestamp,
    current_adjusted_nav: float,
    split_rows: dict[str, list[tuple[pd.Timestamp, str, float]]],
) -> float:
    value = current_adjusted_nav
    for split_date, split_type, ratio in split_rows[symbol]:
        if split_date <= source_date:
            continue
        if split_type.casefold() == "forward":
            value *= ratio
        elif split_type.casefold() == "reverse":
            value /= ratio
        else:
            raise ValueError(f"Unsupported split type: {split_type}")
    return value


def load_nav_states() -> tuple[
    pd.DatetimeIndex, dict[pd.Timestamp, dict[str, Any]]
]:
    expected = flowlib.load_spy_sessions()
    next_sessions = flowlib.next_session_map(expected)

    splits = pd.read_csv(flowlib.SPLIT_PATH)
    splits["date"] = pd.to_datetime(
        splits["Date of Split"], errors="coerce"
    )
    splits["ratio"] = pd.to_numeric(splits["Ratio"], errors="coerce")
    split_rows = {
        symbol: sorted(
            [
                (
                    pd.Timestamp(row["date"]).normalize(),
                    str(row["Split Type"]),
                    float(row["ratio"]),
                )
                for row in splits[
                    (splits["Symbol"] == symbol)
                    & splits["date"].notna()
                    & splits["ratio"].notna()
                ].to_dict(orient="records")
            ],
            key=lambda item: item[0],
        )
        for symbol in FUNDS
    }

    nav = pd.read_csv(flowlib.NAV_PATH)
    nav["date"] = pd.to_datetime(nav["Date"], errors="coerce")
    nav["nav"] = pd.to_numeric(nav["NAV"], errors="coerce")
    nav = nav[
        nav["Ticker"].isin(FUNDS)
        & nav["date"].between(START - pd.Timedelta(days=10), END)
        & nav["nav"].notna()
        & (nav["nav"] > 0)
    ].copy()
    states: dict[pd.Timestamp, dict[str, Any]] = {}
    for row in nav.to_dict(orient="records"):
        source_date = pd.Timestamp(row["date"]).normalize()
        available = next_sessions.get(source_date)
        if available is None or not START <= available <= END:
            continue
        symbol = str(row["Ticker"])
        states.setdefault(available, {"source_dates": {}, "nav": {}})
        states[available]["source_dates"][symbol] = source_date
        states[available]["nav"][symbol] = point_in_time_nav(
            symbol,
            source_date,
            float(row["nav"]),
            split_rows,
        )
    states = {
        day: row
        for day, row in states.items()
        if set(row["nav"]) == set(FUNDS)
        and all(
            math.isfinite(float(value)) and float(value) > 0
            for value in row["nav"].values()
        )
    }
    return expected, states


def quote_midpoint(
    frame: pd.DataFrame, day: pd.Timestamp, clock: str
) -> float | None:
    row = base.exact_row(frame, clock_stamp(day, clock, frame.index.tz))
    if not base.valid_quote(row):
        return None
    return base.midpoint(row)


def leg_sides(ladder: str, basis_sign: int) -> dict[str, str]:
    three_x, two_x = LADDERS[ladder]
    if ladder == "positive":
        three_side = "SHORT" if basis_sign > 0 else "LONG"
    else:
        three_side = "LONG" if basis_sign > 0 else "SHORT"
    two_side = "SHORT" if three_side == "LONG" else "LONG"
    return {three_x: three_side, two_x: two_side}


def build_states(
    nav_states: dict[pd.Timestamp, dict[str, Any]],
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    clock: str,
) -> dict[pd.Timestamp, dict[str, Any]]:
    states: dict[pd.Timestamp, dict[str, Any]] = {}
    for day in sorted(nav_states):
        if day in excluded or day not in sessions:
            continue
        implied: dict[str, float] = {}
        mids: dict[str, float] = {}
        valid = True
        for symbol, leverage in FUNDS.items():
            frame = sessions[day].get(symbol)
            midpoint = (
                quote_midpoint(frame, day, clock)
                if frame is not None
                else None
            )
            if midpoint is None:
                valid = False
                break
            wrapper_return = (
                midpoint / float(nav_states[day]["nav"][symbol]) - 1.0
            )
            if (
                not math.isfinite(wrapper_return)
                or abs(wrapper_return) > RETURN_CAP
            ):
                valid = False
                break
            mids[symbol] = midpoint
            implied[symbol] = wrapper_return / leverage
        if not valid:
            continue

        bases = {
            "positive": implied["UPRO"] - implied["SSO"],
            "inverse": implied["SPXU"] - implied["SDS"],
        }
        ladders: dict[str, dict[str, Any]] = {}
        for ladder, basis in bases.items():
            basis_direction = sign(basis)
            ladders[ladder] = {
                "basis": basis,
                "basis_sign": basis_direction,
                "action": (
                    "POSITIVE_BASIS"
                    if basis_direction > 0
                    else "NEGATIVE_BASIS"
                    if basis_direction < 0
                    else "CASH"
                ),
                "legs": (
                    leg_sides(ladder, basis_direction)
                    if basis_direction != 0
                    else {}
                ),
            }
        states[day] = {
            "session_date": day.strftime("%Y-%m-%d"),
            "source_dates": {
                symbol: date.strftime("%Y-%m-%d")
                for symbol, date in nav_states[day][
                    "source_dates"
                ].items()
            },
            "signal_clock": clock,
            "nav": nav_states[day]["nav"],
            "midpoints": mids,
            "implied_underlying_returns": implied,
            "ladders": ladders,
        }
    return states


def pair_actions(
    states: dict[pd.Timestamp, dict[str, Any]]
) -> dict[tuple[pd.Timestamp, str], str]:
    return {
        (day, ladder): row["ladders"][ladder]["action"]
        for day, row in states.items()
        for ladder in LADDERS
    }


def action_agreement(
    first: dict[pd.Timestamp, dict[str, Any]],
    second: dict[pd.Timestamp, dict[str, Any]],
) -> dict[str, Any]:
    left = pair_actions(first)
    right = pair_actions(second)
    joint = sorted(set(left).intersection(right))
    return {
        "joint_pair_states": len(joint),
        "identical_pair_action_including_cash": sum(
            left[key] == right[key] for key in joint
        )
        / max(len(joint), 1),
    }


def four_leg_quote_coverage(
    states: dict[pd.Timestamp, dict[str, Any]],
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
) -> dict[str, Any]:
    active = {
        day: row
        for day, row in states.items()
        if day not in excluded
        and any(
            row["ladders"][ladder]["action"] != "CASH"
            for ladder in LADDERS
        )
    }
    valid = 0
    for day in active:
        all_valid = True
        for symbol in FUNDS:
            frame = sessions.get(day, {}).get(symbol)
            if frame is None:
                all_valid = False
                break
            entry = base.exact_row(
                frame, clock_stamp(day, ENTRY_CLOCK, frame.index.tz)
            )
            exit_quote = base.exact_row(
                frame, clock_stamp(day, EXIT_CLOCK, frame.index.tz)
            )
            if not (base.valid_quote(entry) and base.valid_quote(exit_quote)):
                all_valid = False
                break
        valid += int(all_valid)
    return {
        "active_sessions": len(active),
        "four_leg_entry_exit_valid": valid,
        "coverage": valid / max(len(active), 1),
    }


def render(payload: dict[str, Any]) -> str:
    development = payload["development_2021_2023"]
    failures = [name for name, passed in payload["gates"].items() if not passed]
    lines = [
        "# Same-Issuer Leverage-Ladder Convergence Audit v68",
        "",
        "## Verdict",
        "",
        (
            "**Every returns-blind gate passed. One frozen 2021–2023 P&L "
            "test is authorized; recent years remain locked.**"
            if payload["gate_passed"]
            else "**Rejected returns-blind before P&L.**"
        ),
        "",
        "## Reachability and balance",
        "",
        f"- Eligible sessions: {development['eligible_sessions']} "
        f"({development['eligible_coverage']:.3%})",
        f"- Active pair trades: {development['active_pair_trades']} "
        f"({development['active_pair_trades_per_week']:.3f}/week)",
        "- Pair trades by year: "
        + ", ".join(
            f"{year}={count}"
            for year, count in development[
                "active_pair_trades_by_year"
            ].items()
        ),
        "- Positive ladder basis signs: "
        f"+={development['basis_sign_counts']['positive']['positive']}, "
        f"-={development['basis_sign_counts']['positive']['negative']}",
        "- Inverse ladder basis signs: "
        f"+={development['basis_sign_counts']['inverse']['positive']}, "
        f"-={development['basis_sign_counts']['inverse']['negative']}",
        "",
        "## Stability and independent evidence",
        "",
        f"- 09:31 pair-action agreement: "
        f"{payload['neighboring_clock_stability']['09:31']['identical_pair_action_including_cash']:.3%}",
        f"- 09:33 pair-action agreement: "
        f"{payload['neighboring_clock_stability']['09:33']['identical_pair_action_including_cash']:.3%}",
        f"- Independent feature agreement: "
        f"{payload['independent_overlap_2023']['identical_pair_action_including_cash']:.3%}",
        f"- Primary four-leg quote coverage: "
        f"{payload['quote_evidence']['primary']['coverage']:.3%}",
        f"- Independent four-leg quote coverage: "
        f"{payload['quote_evidence']['independent']['coverage']:.3%}",
        "",
        "## Gates",
        "",
    ]
    lines.extend(
        f"- {name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in payload["gates"].items()
    )
    lines.extend(
        [
            "",
            "Failed gates: " + (", ".join(failures) if failures else "none"),
            "",
            "No post-entry return, P&L, or 2024–2025 strategy outcome was "
            "calculated.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    expected, nav_states = load_nav_states()
    arca = relay.sessions(relay.ARCA_PATH)
    arca_excluded = relay.degraded(relay.ARCA_CONDITIONS)
    primary = build_states(
        nav_states, arca, arca_excluded, SIGNAL_CLOCK
    )
    adjacent = {
        clock: build_states(nav_states, arca, arca_excluded, clock)
        for clock in ADJACENT_CLOCKS
    }

    equs = relay.sessions(relay.EQUS_PATH)
    equs_excluded = relay.degraded(relay.EQUS_CONDITIONS)
    independent = build_states(
        nav_states, equs, equs_excluded, SIGNAL_CLOCK
    )

    pair_states = pair_actions(primary)
    active_pairs = {
        key: action
        for key, action in pair_states.items()
        if action != "CASH"
    }
    signs: dict[str, Counter[int]] = {
        ladder: Counter(
            row["ladders"][ladder]["basis_sign"]
            for row in primary.values()
        )
        for ladder in LADDERS
    }
    by_year = {
        str(year): sum(day.year == year for day, _ in active_pairs)
        for year in (2021, 2022, 2023)
    }
    development = {
        "expected_sessions": len(expected),
        "nav_complete_sessions": len(nav_states),
        "eligible_sessions": len(primary),
        "eligible_coverage": len(primary) / max(len(expected), 1),
        "active_pair_trades": len(active_pairs),
        "active_pair_trades_per_week": len(active_pairs)
        / (len(expected) / 5.0),
        "active_pair_trades_by_year": by_year,
        "basis_sign_counts": {
            ladder: {
                "positive": signs[ladder][1],
                "negative": signs[ladder][-1],
                "zero": signs[ladder][0],
            }
            for ladder in LADDERS
        },
    }

    neighboring = {
        clock: action_agreement(primary, states)
        for clock, states in adjacent.items()
    }
    independent_overlap = action_agreement(primary, independent)
    quote_evidence = {
        "primary": four_leg_quote_coverage(
            primary, arca, arca_excluded
        ),
        "independent": four_leg_quote_coverage(
            independent, equs, equs_excluded
        ),
    }
    causal = all(
        all(
            pd.Timestamp(source_date).normalize() < day
            for source_date in row["source_dates"].values()
        )
        for day, row in primary.items()
    )
    min_sign_count = min(
        signs[ladder][direction]
        for ladder in LADDERS
        for direction in (-1, 1)
    )
    gates = {
        "complete_prior_nav_coverage_at_least_95_percent": len(nav_states)
        / max(len(expected), 1)
        >= 0.95,
        "eligible_session_coverage_at_least_95_percent": development[
            "eligible_coverage"
        ]
        >= 0.95,
        "active_pair_trades_at_least_2_per_week": development[
            "active_pair_trades_per_week"
        ]
        >= 2.0,
        "at_least_200_active_pair_trades_each_year": min(by_year.values())
        >= 200,
        "each_ladder_each_basis_sign_at_least_100": min_sign_count >= 100,
        "neighboring_09_31_pair_action_agreement_at_least_85_percent": neighboring[
            "09:31"
        ]["identical_pair_action_including_cash"]
        >= 0.85,
        "neighboring_09_33_pair_action_agreement_at_least_85_percent": neighboring[
            "09:33"
        ]["identical_pair_action_including_cash"]
        >= 0.85,
        "independent_pair_action_agreement_at_least_90_percent": independent_overlap[
            "identical_pair_action_including_cash"
        ]
        >= 0.90,
        "primary_four_leg_quote_coverage_at_least_95_percent": quote_evidence[
            "primary"
        ]["coverage"]
        >= 0.95,
        "independent_four_leg_quote_coverage_at_least_90_percent": quote_evidence[
            "independent"
        ]["coverage"]
        >= 0.90,
        "all_nav_source_dates_strictly_before_signal_dates": causal,
        "no_basis_threshold_or_fitted_weight": True,
        "no_post_entry_return_or_recent_outcome_read": True,
    }
    payload = {
        "status": "returns_blind_v68_audit",
        "sources": {
            "official_nav": str(flowlib.NAV_PATH.relative_to(ROOT)),
            "official_splits": str(flowlib.SPLIT_PATH.relative_to(ROOT)),
            "new_databento_calls_or_purchases": False,
        },
        "rule": {
            "signal_clock": SIGNAL_CLOCK,
            "entry_clock": ENTRY_CLOCK,
            "exit_clock": EXIT_CLOCK,
            "pair_weights": "40% 3x and 60% 2x within each $50 ladder",
            "maximum_gross": 100.0,
        },
        "development_2021_2023": development,
        "neighboring_clock_stability": neighboring,
        "independent_overlap_2023": independent_overlap,
        "quote_evidence": quote_evidence,
        "gates": gates,
        "gate_passed": all(gates.values()),
        "decision": (
            "authorize_frozen_development_pnl_only"
            if all(gates.values())
            else "reject_before_pnl"
        ),
        "states": [row for _, row in sorted(primary.items())],
        "independent_states_2023": [
            row for _, row in sorted(independent.items())
        ],
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    REPORT.write_text(render(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                key: value
                for key, value in payload.items()
                if key not in {"states", "independent_states_2023"}
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
