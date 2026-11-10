"""Returns-blind audit of creation-conditioned leveraged-ETF discounts.

This file may inspect prices only through the frozen signal observation. It
does not read an entry fill, exit fill, strategy return, or 2024-2025 result.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_scout import audit_leveraged_etf_official_open_basis_v48 as v48
from research_scout import audit_proshares_primary_market_flows_v60 as flowlib
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay
from research_scout import audit_upro_spxu_premarket_wrapper_premium as v19
from research_scout import test_upro_spxu_creative_hypotheses as base

ROOT = Path(__file__).resolve().parents[1]
FLOW_AUDIT = (
    ROOT / "research_scout" / "proshares_primary_market_flow_audit_v60.json"
)
V48_AUDIT = (
    ROOT
    / "research_scout"
    / "leveraged_etf_official_open_basis_returns_blind_audit_v48.json"
)
OUTPUT = (
    ROOT
    / "research_scout"
    / "creation_conditioned_wrapper_discount_returns_blind_audit_v62.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "CREATION_CONDITIONED_WRAPPER_DISCOUNT_AUDIT_V62.md"
)

START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")
PRIMARY_SPY_BAR = "09:31"
PRIMARY_WRAPPER_QUOTE = "09:32"
PLANNED_ENTRY = "09:33"
ADJACENT_CLOCKS = {
    "one_minute_earlier": ("09:30", "09:31"),
    "one_minute_later_diagnostic_only": ("09:32", "09:33"),
}
CORPORATE_ACTION_RETURN_CAP = 0.25
SYMBOLS = ("UPRO", "SPXU")


def clock_stamp(
    day: pd.Timestamp, clock: str, timezone: Any
) -> pd.Timestamp:
    hour, minute = (int(part) for part in clock.split(":"))
    return (
        day.tz_localize(timezone)
        + pd.Timedelta(hours=hour, minutes=minute)
    )


def load_flow_inventory() -> tuple[
    pd.DatetimeIndex, dict[pd.Timestamp, dict[str, dict[str, Any]]]
]:
    """Reconstruct every per-fund flow state, including paired-zero days."""
    sessions = flowlib.load_spy_sessions()
    next_sessions = flowlib.next_session_map(sessions)

    nav = pd.read_csv(flowlib.NAV_PATH)
    nav["date"] = pd.to_datetime(nav["Date"], errors="coerce")
    nav["shares_000"] = pd.to_numeric(
        nav["Shares Outstanding (000)"], errors="coerce"
    )
    nav["nav"] = pd.to_numeric(nav["NAV"], errors="coerce")
    nav = nav[nav["Ticker"].isin(SYMBOLS)].copy()

    splits = pd.read_csv(flowlib.SPLIT_PATH)
    splits["date"] = pd.to_datetime(
        splits["Date of Split"], errors="coerce"
    )
    splits["ratio"] = pd.to_numeric(splits["Ratio"], errors="coerce")
    split_lookup = {
        (str(row["Symbol"]), row["date"]): (
            str(row["Split Type"]),
            float(row["ratio"]),
        )
        for row in splits[splits["Symbol"].isin(SYMBOLS)].to_dict(
            orient="records"
        )
    }
    split_rows = {
        symbol: sorted(
            [
                (
                    pd.Timestamp(row["date"]),
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
        for symbol in SYMBOLS
    }

    def point_in_time_nav(
        symbol: str, source_date: pd.Timestamp, current_adjusted_nav: float
    ) -> float:
        """Undo splits after source_date from the mutable historical NAV file."""
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

    states: dict[pd.Timestamp, dict[str, dict[str, Any]]] = {}
    for symbol in SYMBOLS:
        selected = nav[nav["Ticker"] == symbol].sort_values("date").copy()
        selected["prior_shares_000"] = selected["shares_000"].shift(1)
        expected_prior: list[float] = []
        for row in selected.itertuples(index=False):
            split_type, ratio = split_lookup.get(
                (symbol, row.date), (None, None)
            )
            expected_prior.append(
                flowlib.split_expected_shares(
                    float(row.prior_shares_000), split_type, ratio
                )
                if pd.notna(row.prior_shares_000)
                else np.nan
            )
        selected["expected_prior_shares_000"] = expected_prior
        selected["flow_dollars"] = (
            selected["shares_000"] - selected["expected_prior_shares_000"]
        ) * 1000.0 * selected["nav"]
        selected = selected[selected["date"].between(START, END)].copy()
        selected["available_session"] = selected["date"].map(next_sessions)
        for row in selected.itertuples(index=False):
            if pd.isna(row.available_session):
                continue
            available = pd.Timestamp(row.available_session).normalize()
            if not START <= available <= END:
                continue
            states.setdefault(available, {})[symbol] = {
                "source_date": pd.Timestamp(row.date).normalize(),
                "flow_dollars": float(row.flow_dollars),
                "prior_nav": point_in_time_nav(
                    symbol, pd.Timestamp(row.date), float(row.nav)
                ),
            }
    return sessions, states


def exact_bar_close(
    sessions: dict[pd.Timestamp, pd.DataFrame],
    day: pd.Timestamp,
    clock: str,
) -> float | None:
    frame = sessions.get(day)
    if frame is None:
        return None
    row = base.exact_row(frame, clock_stamp(day, clock, frame.index.tz))
    if row is None:
        return None
    value = float(row["close"])
    return value if math.isfinite(value) and value > 0 else None


def exact_midpoint(
    pair: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    day: pd.Timestamp,
    symbol: str,
    clock: str,
) -> tuple[float, float] | None:
    frame = pair.get(day, {}).get(symbol)
    if frame is None:
        return None
    stamp = clock_stamp(day, clock, frame.index.tz)
    row = base.exact_row(frame, stamp)
    if not base.valid_quote(row):
        return None
    return base.midpoint(row), (
        (float(row.ask_px_00) - float(row.bid_px_00))
        / base.midpoint(row)
        * 10_000.0
    )


def build_states(
    expected: pd.DatetimeIndex,
    flows: dict[pd.Timestamp, dict[str, dict[str, Any]]],
    spy: dict[pd.Timestamp, pd.DataFrame],
    pair: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    previous_closes: dict[str, dict[str, float]],
    spy_bar_clock: str,
    wrapper_quote_clock: str,
) -> dict[pd.Timestamp, dict[str, Any]]:
    states: dict[pd.Timestamp, dict[str, Any]] = {}
    for day in expected:
        day = pd.Timestamp(day).normalize()
        if day in excluded or day not in flows:
            continue
        fund_flow = flows[day]
        if not all(symbol in fund_flow for symbol in SYMBOLS):
            continue
        prior = previous_closes.get(day.strftime("%Y-%m-%d"))
        if prior is None or "SPY" not in prior:
            continue
        spy_now = exact_bar_close(spy, day, spy_bar_clock)
        quote_rows = {
            symbol: exact_midpoint(
                pair, day, symbol, wrapper_quote_clock
            )
            for symbol in SYMBOLS
        }
        if spy_now is None or any(value is None for value in quote_rows.values()):
            continue

        spy_return = spy_now / float(prior["SPY"]) - 1.0
        wrapper_returns = {
            symbol: float(quote_rows[symbol][0])
            / float(fund_flow[symbol]["prior_nav"])
            - 1.0
            for symbol in SYMBOLS
        }
        if (
            not math.isfinite(spy_return)
            or abs(spy_return) > CORPORATE_ACTION_RETURN_CAP
            or any(
                not math.isfinite(value)
                or abs(value) > CORPORATE_ACTION_RETURN_CAP
                for value in wrapper_returns.values()
            )
        ):
            continue

        residuals = {
            "UPRO": wrapper_returns["UPRO"] / 3.0 - spy_return,
            "SPXU": wrapper_returns["SPXU"] / 3.0 + spy_return,
        }
        candidates = [
            symbol
            for symbol in SYMBOLS
            if fund_flow[symbol]["flow_dollars"] > 0.01
            and residuals[symbol] < 0.0
        ]
        action = "CASH"
        if len(candidates) == 1:
            action = candidates[0]
        elif len(candidates) == 2:
            if residuals[candidates[0]] != residuals[candidates[1]]:
                action = min(candidates, key=residuals.get)

        states[day] = {
            "session_date": day.strftime("%Y-%m-%d"),
            "action": action,
            "source_date": fund_flow["UPRO"]["source_date"].strftime(
                "%Y-%m-%d"
            ),
            "spy_return_to_signal": spy_return,
            "wrapper_returns_from_prior_nav": wrapper_returns,
            "residuals_underlying_units": residuals,
            "flows_dollars": {
                symbol: fund_flow[symbol]["flow_dollars"]
                for symbol in SYMBOLS
            },
            "prior_nav": {
                symbol: fund_flow[symbol]["prior_nav"] for symbol in SYMBOLS
            },
            "signal_midpoints": {
                symbol: quote_rows[symbol][0] for symbol in SYMBOLS
            },
            "signal_spreads_bps": {
                symbol: quote_rows[symbol][1] for symbol in SYMBOLS
            },
        }
    return states


def compare_states(
    first: dict[pd.Timestamp, dict[str, Any]],
    second: dict[pd.Timestamp, dict[str, Any]],
) -> dict[str, Any]:
    joint = sorted(set(first).intersection(second))
    both_signal = [
        day
        for day in joint
        if first[day]["action"] != "CASH"
        and second[day]["action"] != "CASH"
    ]
    return {
        "joint_eligible_sessions": len(joint),
        "identical_action_including_cash": (
            sum(first[day]["action"] == second[day]["action"] for day in joint)
            / max(len(joint), 1)
        ),
        "both_signal_sessions": len(both_signal),
        "conditional_symbol_agreement": (
            sum(first[day]["action"] == second[day]["action"] for day in both_signal)
            / max(len(both_signal), 1)
        ),
    }


def external_action_agreement(
    primary: dict[pd.Timestamp, dict[str, Any]],
    external: dict[pd.Timestamp, str],
    universe: pd.DatetimeIndex,
) -> float:
    return sum(
        primary.get(pd.Timestamp(day), {}).get("action", "CASH")
        == external.get(pd.Timestamp(day), "CASH")
        for day in universe
    ) / max(len(universe), 1)


def render(payload: dict[str, Any]) -> str:
    development = payload["development_2021_2023"]
    failures = [
        name for name, passed in payload["gates"].items() if not passed
    ]
    lines = [
        "# Creation-Conditioned Wrapper Discount Audit v62",
        "",
        "## Verdict",
        "",
        (
            "**Returns-blind construction gates passed. Formal critique and "
            "preregistration are allowed; entry/exit P&L remains unopened.**"
            if payload["gate_passed"]
            else "**Rejected returns-blind before P&L.**"
        ),
        "",
        "## Frozen measurement",
        "",
        "- Only a fund with a positive prior-session creation estimate is eligible.",
        "- SPY return: prior official close to the 09:31 one-minute bar close.",
        "- Wrapper return: point-in-time split-normalized prior official NAV "
        "to the 09:32 BBO midpoint.",
        "- UPRO residual = UPRO return / 3 - SPY return.",
        "- SPXU residual = SPXU return / 3 + SPY return.",
        "- Buy eligibility requires a strictly negative residual. If both funds "
        "qualify, select the more negative underlying-unit residual.",
        "- The 09:31 bar is timestamped at interval start and is not complete "
        "before 09:32. A future implementation may not enter before 09:33.",
        "",
        "## Reachability",
        "",
        f"- Eligible sessions: {development['eligible_sessions']} "
        f"({development['coverage']:.3%} coverage)",
        f"- Signals: {development['signals']} "
        f"({development['signals_per_week']:.3f}/week)",
        f"- UPRO / SPXU: {development['upro_signals']} / "
        f"{development['spxu_signals']}",
        "- By year: "
        + ", ".join(
            f"{year}={count}"
            for year, count in development["signals_by_year"].items()
        ),
        "",
        "## Measurement stability and distinctness",
        "",
    ]
    for name, item in payload["clock_stability"].items():
        lines.append(
            f"- {name}: {item['identical_action_including_cash']:.3%} "
            "identical action including cash"
        )
    feed = payload["independent_feed_overlap_2023"]
    lines.extend(
        [
            f"- ARCX/EQUS overlap: {feed['joint_eligible_sessions']} sessions; "
            f"{feed['identical_action_including_cash']:.3%} identical action",
            f"- Action agreement with failed V19: "
            f"{payload['distinctness']['v19_action_agreement']:.3%}",
            f"- Action agreement with failed V48: "
            f"{payload['distinctness']['v48_action_agreement']:.3%}",
            "",
            "## Gates",
            "",
        ]
    )
    lines.extend(
        f"- {name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in payload["gates"].items()
    )
    lines.extend(
        [
            "",
            "Failed gates: " + (", ".join(failures) if failures else "none"),
            "",
            "No price after the prospective 09:33 entry, strategy P&L, or "
            "2024-2025 result was read.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    flow_audit = json.loads(FLOW_AUDIT.read_text(encoding="utf-8"))
    expected, flows = load_flow_inventory()
    _, previous_closes, statistic_integrity = v48.load_statistics()

    spy_arca = v19.spy_sessions(v19.ARCA_SPY)
    pair_arca = relay.sessions(relay.ARCA_PATH)
    excluded_arca = relay.degraded(relay.ARCA_CONDITIONS)
    primary = build_states(
        expected,
        flows,
        spy_arca,
        pair_arca,
        excluded_arca,
        previous_closes,
        PRIMARY_SPY_BAR,
        PRIMARY_WRAPPER_QUOTE,
    )
    adjacent = {
        name: build_states(
            expected,
            flows,
            spy_arca,
            pair_arca,
            excluded_arca,
            previous_closes,
            spy_clock,
            quote_clock,
        )
        for name, (spy_clock, quote_clock) in ADJACENT_CLOCKS.items()
    }
    stability = {
        name: compare_states(primary, states)
        for name, states in adjacent.items()
    }

    spy_equs = v19.spy_sessions(v19.EQUS_SPY)
    pair_equs = relay.sessions(relay.EQUS_PATH)
    excluded_equs = relay.degraded(relay.EQUS_CONDITIONS)
    equs = build_states(
        expected,
        flows,
        spy_equs,
        pair_equs,
        excluded_equs,
        previous_closes,
        PRIMARY_SPY_BAR,
        PRIMARY_WRAPPER_QUOTE,
    )
    feed_overlap = compare_states(primary, equs)

    signals = {
        day: row for day, row in primary.items() if row["action"] != "CASH"
    }
    counts = Counter(row["action"] for row in signals.values())
    signals_by_year = {
        str(year): sum(day.year == year for day in signals)
        for year in (2021, 2022, 2023)
    }
    development = {
        "expected_sessions": len(expected),
        "eligible_sessions": len(primary),
        "coverage": len(primary) / len(expected),
        "signals": len(signals),
        "signals_per_week": len(signals) / (len(expected) / 5.0),
        "selection_share": len(signals) / max(len(primary), 1),
        "upro_signals": counts["UPRO"],
        "spxu_signals": counts["SPXU"],
        "minority_share": min(counts.values()) / max(len(signals), 1)
        if len(counts) == 2
        else 0.0,
        "signals_by_year": signals_by_year,
    }

    v19_frame = v19.signal_frame(spy_arca, pair_arca, excluded_arca)
    v19_actions = {
        pd.Timestamp(row.date).normalize(): (
            "UPRO" if int(row.direction) > 0 else
            "SPXU" if int(row.direction) < 0 else
            "CASH"
        )
        for row in v19_frame.itertuples()
        if START <= pd.Timestamp(row.date) <= END
    }
    v48_payload = json.loads(V48_AUDIT.read_text(encoding="utf-8"))
    v48_actions = {
        pd.Timestamp(day): str(row["symbol"])
        for day, row in v48_payload["signals"].items()
        if "2021-01-01" <= day <= "2023-12-31"
    }
    distinctness = {
        "v19_action_agreement": external_action_agreement(
            primary, v19_actions, expected
        ),
        "v48_action_agreement": external_action_agreement(
            primary, v48_actions, expected
        ),
    }

    causal_delay = all(
        pd.Timestamp(row["source_date"]) < day for day, row in primary.items()
    )
    gates = {
        "official_flow_audit_passed": bool(flow_audit["admission_passed"]),
        "statistics_unique_and_positive": not statistic_integrity[
            "duplicate_symbol_sessions"
        ]
        and not statistic_integrity["invalid_prices"],
        "primary_source_coverage_at_least_95_percent": development["coverage"]
        >= 0.95,
        "signal_frequency_at_least_2_per_week": development[
            "signals_per_week"
        ]
        >= 2.0,
        "at_least_90_signals_each_year": min(signals_by_year.values()) >= 90,
        "both_sleeves_and_minority_at_least_20_percent": len(counts) == 2
        and development["minority_share"] >= 0.20,
        "selection_share_between_25_and_75_percent": 0.25
        <= development["selection_share"]
        <= 0.75,
        "earlier_clock_action_stability_at_least_65_percent": stability[
            "one_minute_earlier"
        ]["identical_action_including_cash"]
        >= 0.65,
        "later_clock_diagnostic_stability_at_least_65_percent": stability[
            "one_minute_later_diagnostic_only"
        ]["identical_action_including_cash"]
        >= 0.65,
        "independent_feed_overlap_at_least_150_sessions": feed_overlap[
            "joint_eligible_sessions"
        ]
        >= 150,
        "independent_feed_action_agreement_at_least_75_percent": feed_overlap[
            "identical_action_including_cash"
        ]
        >= 0.75,
        "distinct_from_failed_v19_below_80_percent_agreement": distinctness[
            "v19_action_agreement"
        ]
        < 0.80,
        "distinct_from_failed_v48_below_80_percent_agreement": distinctness[
            "v48_action_agreement"
        ]
        < 0.80,
        "one_session_flow_delay_and_entry_after_signal": causal_delay
        and PRIMARY_SPY_BAR < PRIMARY_WRAPPER_QUOTE < PLANNED_ENTRY,
        "no_magnitude_threshold": True,
        "no_post_entry_return_pnl_or_recent_outcome_read": True,
    }
    payload = {
        "status": "returns_blind_creation_conditioned_wrapper_discount_audit",
        "sources": {
            "official_proshares_flow_audit": str(
                FLOW_AUDIT.relative_to(ROOT)
            ),
            "official_proshares_nav_sha256": flow_audit["source"][
                "historical_nav_sha256"
            ],
            "official_arca_close_statistics": str(
                v48.technical.STATISTICS.relative_to(ROOT)
            ),
            "arca_spy_bars": str(v19.ARCA_SPY.relative_to(ROOT)),
            "arca_wrapper_bbo": str(relay.ARCA_PATH.relative_to(ROOT)),
            "equs_spy_bars": str(v19.EQUS_SPY.relative_to(ROOT)),
            "equs_wrapper_bbo": str(relay.EQUS_PATH.relative_to(ROOT)),
            "new_databento_calls_or_purchases": False,
            "free_external_sources": ["ProShares official NAV/shares/splits"],
        },
        "rule": {
            "creation_condition": "prior-session estimated fund flow > $0.01",
            "primary_spy_bar": PRIMARY_SPY_BAR,
            "primary_wrapper_quote": PRIMARY_WRAPPER_QUOTE,
            "signal_available_not_before": "09:32",
            "prospective_entry_not_before": PLANNED_ENTRY,
            "fair_value_anchor": (
                "point-in-time split-normalized prior official fund NAV and "
                "prior official SPY close"
            ),
            "upro_residual": "(UPRO midpoint / prior UPRO NAV - 1) / 3 - SPY return",
            "spxu_residual": "(SPXU midpoint / prior SPXU NAV - 1) / 3 + SPY return",
            "eligibility": "positive creation and strictly negative residual",
            "both_qualify": "choose the more negative underlying-unit residual",
            "magnitude_threshold": None,
            "corporate_action_return_cap": CORPORATE_ACTION_RETURN_CAP,
        },
        "development_2021_2023": development,
        "clock_stability": stability,
        "independent_feed_overlap_2023": feed_overlap,
        "distinctness": distinctness,
        "gates": gates,
        "gate_passed": all(gates.values()),
        "decision": (
            "allow_formal_critique_and_preregistration_only"
            if all(gates.values())
            else "reject_before_pnl"
        ),
        "states": [
            row for _, row in sorted(primary.items())
        ],
        "independent_states_2023": [
            row for _, row in sorted(equs.items())
        ],
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    REPORT.write_text(render(payload), encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items() if key != "states"}, indent=2))


if __name__ == "__main__":
    main()
