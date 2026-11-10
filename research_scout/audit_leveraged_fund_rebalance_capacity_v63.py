"""Returns-blind audit of modelled leveraged-fund closing rebalance capacity.

The audit combines prior-session official ProShares AUM with the current
completed SPY 15:49 bar and an exchange-published SPY closing-auction snapshot.
It reads no price after the prospective 15:51 entry.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_leveraged_etf_official_open_basis_v48 as v48
from research_scout import audit_proshares_primary_market_flows_v60 as flowlib
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay
from research_scout import audit_upro_spxu_premarket_wrapper_premium as v19
from research_scout import test_upro_spxu_creative_hypotheses as base

ROOT = Path(__file__).resolve().parents[1]
CLOSING_SNAPSHOTS = (
    ROOT / "research_scout" / "spy_late_closing_auction_snapshots_v42.json"
)
FLOW_AUDIT = (
    ROOT / "research_scout" / "proshares_primary_market_flow_audit_v60.json"
)
OUTPUT = (
    ROOT
    / "research_scout"
    / "leveraged_fund_rebalance_capacity_returns_blind_audit_v63.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "LEVERAGED_FUND_REBALANCE_CAPACITY_AUDIT_V63.md"
)

START = pd.Timestamp("2021-01-01")
END = pd.Timestamp("2023-12-31")
PRIMARY_SPY_BAR = "15:49"
PRIMARY_AUCTION_CUTOFF = "15:50:00"
PLANNED_ENTRY = "15:51"
FUNDS = {
    "UPRO": 3.0,
    "SPXU": -3.0,
    "SSO": 2.0,
    "SDS": -2.0,
}
ADJACENT_CUTOFFS = ("15:49:50", "15:50:10")
CORPORATE_ACTION_RETURN_CAP = 0.25


def sign(value: float) -> int:
    return int(value > 0) - int(value < 0)


def clock_stamp(
    day: pd.Timestamp, clock: str, timezone: Any
) -> pd.Timestamp:
    hour, minute = (int(part) for part in clock.split(":"))
    return (
        day.tz_localize(timezone)
        + pd.Timedelta(hours=hour, minutes=minute)
    )


def load_aum_states() -> tuple[
    pd.DatetimeIndex, dict[pd.Timestamp, dict[str, Any]]
]:
    expected = flowlib.load_spy_sessions()
    next_sessions = flowlib.next_session_map(expected)
    nav = pd.read_csv(flowlib.NAV_PATH)
    nav["date"] = pd.to_datetime(nav["Date"], errors="coerce")
    nav["aum"] = pd.to_numeric(
        nav["Assets Under Management"], errors="coerce"
    )
    nav = nav[
        nav["Ticker"].isin(FUNDS)
        & nav["date"].between(START, END)
    ].copy()
    pivot = nav.pivot(index="date", columns="Ticker", values="aum")
    states: dict[pd.Timestamp, dict[str, Any]] = {}
    for source_date, row in pivot.sort_index().iterrows():
        if not all(
            symbol in row
            and math.isfinite(float(row[symbol]))
            and float(row[symbol]) > 0
            for symbol in FUNDS
        ):
            continue
        available = next_sessions.get(pd.Timestamp(source_date).normalize())
        if available is None or not START <= available <= END:
            continue
        states[pd.Timestamp(available).normalize()] = {
            "source_date": pd.Timestamp(source_date).normalize(),
            "aum": {
                symbol: float(row[symbol]) for symbol in FUNDS
            },
        }
    return expected, states


def load_snapshots(
    cutoff: str,
) -> dict[pd.Timestamp, dict[str, Any]]:
    payload = json.loads(CLOSING_SNAPSHOTS.read_text(encoding="utf-8"))
    if payload.get("returns_read") is not False:
        raise RuntimeError("Closing snapshots are not marked returns-blind")
    return {
        pd.Timestamp(row["session_date"]).normalize(): row
        for row in payload["snapshots"]
        if row["cutoff"] == cutoff
        and "2021-01-01" <= row["session_date"] <= "2023-12-31"
    }


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


def build_states(
    expected: pd.DatetimeIndex,
    aum_states: dict[pd.Timestamp, dict[str, Any]],
    snapshots: dict[pd.Timestamp, dict[str, Any]],
    spy: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
    previous_closes: dict[str, dict[str, float]],
    *,
    fund_subset: tuple[str, ...] = tuple(FUNDS),
) -> dict[pd.Timestamp, dict[str, Any]]:
    rows: dict[pd.Timestamp, dict[str, Any]] = {}
    for day in expected:
        day = pd.Timestamp(day).normalize()
        if (
            day in excluded
            or day not in aum_states
            or day not in snapshots
        ):
            continue
        prior = previous_closes.get(day.strftime("%Y-%m-%d"))
        spy_now = exact_bar_close(spy, day, PRIMARY_SPY_BAR)
        if prior is None or "SPY" not in prior or spy_now is None:
            continue
        spy_return = spy_now / float(prior["SPY"]) - 1.0
        if (
            not math.isfinite(spy_return)
            or abs(spy_return) > CORPORATE_ACTION_RETURN_CAP
        ):
            continue
        snapshot = snapshots[day]
        auction_qty = float(snapshot["total_imbalance_qty"])
        auction_side = str(snapshot["side"])
        if (
            not math.isfinite(auction_qty)
            or auction_qty <= 0
            or auction_side not in {"A", "B"}
        ):
            continue
        coefficient_aum = sum(
            FUNDS[symbol]
            * (FUNDS[symbol] - 1.0)
            * aum_states[day]["aum"][symbol]
            for symbol in fund_subset
        )
        model_dollars = coefficient_aum * spy_return
        model_shares = model_dollars / spy_now
        auction_signed_shares = auction_qty * (
            1.0 if auction_side == "B" else -1.0
        )
        net_shares = model_shares + auction_signed_shares
        model_direction = sign(model_shares)
        net_direction = sign(net_shares)
        action = (
            "UPRO"
            if model_direction > 0 and net_direction == model_direction
            else "SPXU"
            if model_direction < 0 and net_direction == model_direction
            else "CASH"
        )
        rows[day] = {
            "session_date": day.strftime("%Y-%m-%d"),
            "source_date": aum_states[day]["source_date"].strftime(
                "%Y-%m-%d"
            ),
            "action": action,
            "model_direction": model_direction,
            "auction_side": auction_side,
            "spy_return_to_signal": spy_return,
            "spy_signal_price": spy_now,
            "fund_aum": aum_states[day]["aum"],
            "coefficient_aum_dollars": coefficient_aum,
            "model_rebalance_dollars": model_dollars,
            "model_equivalent_spy_shares": model_shares,
            "auction_signed_spy_shares": auction_signed_shares,
            "net_model_plus_auction_shares": net_shares,
            "capacity_blocked": model_direction != 0
            and net_direction != model_direction,
            "snapshot_ts_event": snapshot["ts_event"],
            "snapshot_ts_recv": snapshot["ts_recv"],
        }
    return rows


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
        "identical_action_including_cash": sum(
            first[day]["action"] == second[day]["action"]
            for day in joint
        )
        / max(len(joint), 1),
        "both_signal_sessions": len(both_signal),
        "conditional_symbol_agreement": sum(
            first[day]["action"] == second[day]["action"]
            for day in both_signal
        )
        / max(len(both_signal), 1),
    }


def action_agreement(
    primary: dict[pd.Timestamp, dict[str, Any]],
    alternative: dict[pd.Timestamp, str],
) -> float:
    joint = sorted(set(primary).intersection(alternative))
    return sum(
        primary[day]["action"] == alternative[day] for day in joint
    ) / max(len(joint), 1)


def old_closing_torque_actions(
    primary: dict[pd.Timestamp, dict[str, Any]],
    spy: dict[pd.Timestamp, pd.DataFrame],
    previous_closes: dict[str, dict[str, float]],
) -> dict[pd.Timestamp, str]:
    actions: dict[pd.Timestamp, str] = {}
    for day in primary:
        frame = spy.get(day)
        prior = previous_closes.get(day.strftime("%Y-%m-%d"))
        if frame is None or prior is None:
            continue
        start = base.exact_row(
            frame, clock_stamp(day, "13:30", frame.index.tz)
        )
        end = base.exact_row(
            frame, clock_stamp(day, "14:29", frame.index.tz)
        )
        action = "CASH"
        if start is not None and end is not None:
            day_direction = sign(float(end["close"]) - float(prior["SPY"]))
            late_direction = sign(
                float(end["close"]) - float(start["open"])
            )
            if day_direction != 0 and late_direction == day_direction:
                action = "UPRO" if day_direction > 0 else "SPXU"
        actions[day] = action
    return actions


def entry_quote_coverage(
    states: dict[pd.Timestamp, dict[str, Any]],
    pair: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
) -> dict[str, Any]:
    signals = {
        day: row
        for day, row in states.items()
        if row["action"] != "CASH" and day not in excluded
    }
    available = 0
    spreads: list[float] = []
    for day, row in signals.items():
        frame = pair.get(day, {}).get(row["action"])
        if frame is None:
            continue
        quote = base.exact_row(
            frame, clock_stamp(day, PLANNED_ENTRY, frame.index.tz)
        )
        if not base.valid_quote(quote):
            continue
        available += 1
        midpoint = base.midpoint(quote)
        spreads.append(
            (float(quote.ask_px_00) - float(quote.bid_px_00))
            / midpoint
            * 10_000.0
        )
    return {
        "signals": len(signals),
        "available": available,
        "coverage": available / max(len(signals), 1),
        "median_spread_bps": float(pd.Series(spreads).median())
        if spreads
        else None,
        "p95_spread_bps": float(pd.Series(spreads).quantile(0.95))
        if spreads
        else None,
    }


def render(payload: dict[str, Any]) -> str:
    development = payload["development_2021_2023"]
    failures = [
        name for name, passed in payload["gates"].items() if not passed
    ]
    lines = [
        "# Leveraged-Fund Rebalance / Auction-Capacity Audit v63",
        "",
        "## Verdict",
        "",
        (
            "**Returns-blind construction gates passed. Formal critique and "
            "preregistration are allowed; P&L remains unopened.**"
            if payload["gate_passed"]
            else "**Rejected returns-blind before P&L.**"
        ),
        "",
        "## Frozen construction",
        "",
        "- Use prior-session official AUM for UPRO (+3), SPXU (-3), "
        "SSO (+2), and SDS (-2).",
        "- Model each fund's first-order rebalance demand as "
        "`L × (L - 1) × prior AUM × SPY return`.",
        "- SPY return ends at the completed 15:49 bar.",
        "- Add the latest SPY closing-auction signed total imbalance strictly "
        "before 15:50.",
        "- Trade only in the model direction when the auction imbalance does "
        "not overwhelm it; otherwise cash. No fitted magnitude threshold.",
        "",
        "## Development reachability",
        "",
        f"- Eligible sessions: {development['eligible_sessions']} "
        f"({development['coverage']:.3%})",
        f"- Signals: {development['signals']} "
        f"({development['signals_per_week']:.3f}/week)",
        f"- UPRO / SPXU: {development['upro_signals']} / "
        f"{development['spxu_signals']}",
        "- By year: "
        + ", ".join(
            f"{year}={count}"
            for year, count in development["signals_by_year"].items()
        ),
        f"- Auction capacity blocked the model on "
        f"{development['capacity_block_share']:.3%} of eligible sessions.",
        "",
        "## Stability and distinctness",
        "",
    ]
    for name, item in payload["auction_cutoff_stability"].items():
        lines.append(
            f"- {name}: {item['identical_action_including_cash']:.3%} "
            "identical action including cash"
        )
    lines.extend(
        [
            f"- ARCX/EQUS signal agreement: "
            f"{payload['independent_feed_overlap_2023']['identical_action_including_cash']:.3%}",
            f"- Agreement with pure late-day momentum: "
            f"{payload['distinctness']['pure_model_direction_agreement']:.3%}",
            f"- Agreement with failed Closing Rebalance Torque: "
            f"{payload['distinctness']['failed_closing_torque_agreement']:.3%}",
            f"- Agreement with auction-only direction: "
            f"{payload['distinctness']['auction_only_agreement']:.3%}",
            "",
            "## Entry evidence",
            "",
            f"- Primary 15:51 quote coverage: "
            f"{payload['entry_quote_evidence']['primary']['coverage']:.3%}",
            f"- Independent-overlap quote coverage: "
            f"{payload['entry_quote_evidence']['independent']['coverage']:.3%}",
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
            "No price after the prospective 15:51 entry, strategy P&L, or "
            "2024-2025 outcome was read.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    flow_audit = json.loads(FLOW_AUDIT.read_text(encoding="utf-8"))
    expected, aum_states = load_aum_states()
    _, previous_closes, statistic_integrity = v48.load_statistics()
    snapshots = load_snapshots(PRIMARY_AUCTION_CUTOFF)
    spy_arca = v19.spy_sessions(v19.ARCA_SPY)
    excluded_arca = relay.degraded(relay.ARCA_CONDITIONS)
    primary = build_states(
        expected,
        aum_states,
        snapshots,
        spy_arca,
        excluded_arca,
        previous_closes,
    )

    adjacent = {
        cutoff: build_states(
            expected,
            aum_states,
            load_snapshots(cutoff),
            spy_arca,
            excluded_arca,
            previous_closes,
        )
        for cutoff in ADJACENT_CUTOFFS
    }
    cutoff_stability = {
        cutoff: compare_states(primary, states)
        for cutoff, states in adjacent.items()
    }

    spy_equs = v19.spy_sessions(v19.EQUS_SPY)
    excluded_equs = relay.degraded(relay.EQUS_CONDITIONS)
    equs = build_states(
        expected,
        aum_states,
        snapshots,
        spy_equs,
        excluded_equs,
        previous_closes,
    )
    feed_overlap = compare_states(primary, equs)

    three_x_only = build_states(
        expected,
        aum_states,
        snapshots,
        spy_arca,
        excluded_arca,
        previous_closes,
        fund_subset=("UPRO", "SPXU"),
    )
    pure_model = {
        day: (
            "UPRO"
            if row["model_direction"] > 0
            else "SPXU"
            if row["model_direction"] < 0
            else "CASH"
        )
        for day, row in primary.items()
    }
    auction_only = {
        day: "UPRO" if row["auction_side"] == "B" else "SPXU"
        for day, row in primary.items()
    }
    torque = old_closing_torque_actions(
        primary, spy_arca, previous_closes
    )
    distinctness = {
        "pure_model_direction_agreement": action_agreement(
            primary, pure_model
        ),
        "auction_only_agreement": action_agreement(primary, auction_only),
        "failed_closing_torque_agreement": action_agreement(
            primary, torque
        ),
        "three_x_only_action_agreement": compare_states(
            primary, three_x_only
        )["identical_action_including_cash"],
    }

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
        "capacity_blocked_sessions": sum(
            bool(row["capacity_blocked"]) for row in primary.values()
        ),
        "capacity_block_share": sum(
            bool(row["capacity_blocked"]) for row in primary.values()
        )
        / max(len(primary), 1),
        "upro_signals": counts["UPRO"],
        "spxu_signals": counts["SPXU"],
        "minority_share": min(counts.values()) / max(len(signals), 1)
        if len(counts) == 2
        else 0.0,
        "signals_by_year": signals_by_year,
    }

    arca_pair = relay.sessions(relay.ARCA_PATH)
    equs_pair = relay.sessions(relay.EQUS_PATH)
    entry_evidence = {
        "primary": entry_quote_coverage(
            primary, arca_pair, excluded_arca
        ),
        "independent": entry_quote_coverage(
            equs, equs_pair, excluded_equs
        ),
    }
    causal = all(
        pd.Timestamp(row["source_date"]) < day
        and pd.Timestamp(row["snapshot_ts_event"])
        .tz_convert("America/New_York")
        .time()
        < pd.Timestamp(PRIMARY_AUCTION_CUTOFF).time()
        for day, row in primary.items()
    )
    gates = {
        "official_aum_source_audit_passed": bool(
            flow_audit["admission_passed"]
        ),
        "all_four_funds_have_complete_positive_prior_aum": len(aum_states)
        == len(expected) - 1,
        "official_close_statistics_unique_and_positive": not statistic_integrity[
            "duplicate_symbol_sessions"
        ]
        and not statistic_integrity["invalid_prices"],
        "eligible_coverage_at_least_95_percent": development["coverage"]
        >= 0.95,
        "signal_frequency_at_least_2_per_week": development[
            "signals_per_week"
        ]
        >= 2.0,
        "at_least_100_signals_each_year": min(signals_by_year.values())
        >= 100,
        "both_sleeves_and_minority_at_least_20_percent": len(counts) == 2
        and development["minority_share"] >= 0.20,
        "selection_share_between_25_and_90_percent": 0.25
        <= development["selection_share"]
        <= 0.90,
        "auction_capacity_changes_at_least_10_percent_of_actions": distinctness[
            "pure_model_direction_agreement"
        ]
        <= 0.90,
        "adjacent_cutoff_15_49_50_stability_at_least_70_percent": cutoff_stability[
            "15:49:50"
        ]["identical_action_including_cash"]
        >= 0.70,
        "adjacent_cutoff_15_50_10_stability_at_least_70_percent": cutoff_stability[
            "15:50:10"
        ]["identical_action_including_cash"]
        >= 0.70,
        "independent_feed_overlap_at_least_150_sessions": feed_overlap[
            "joint_eligible_sessions"
        ]
        >= 150,
        "independent_feed_action_agreement_at_least_90_percent": feed_overlap[
            "identical_action_including_cash"
        ]
        >= 0.90,
        "distinct_from_failed_closing_torque_below_80_percent": distinctness[
            "failed_closing_torque_agreement"
        ]
        < 0.80,
        "distinct_from_auction_only_below_80_percent": distinctness[
            "auction_only_agreement"
        ]
        < 0.80,
        "primary_entry_quote_coverage_at_least_95_percent": entry_evidence[
            "primary"
        ]["coverage"]
        >= 0.95,
        "independent_entry_quote_coverage_at_least_90_percent": entry_evidence[
            "independent"
        ]["coverage"]
        >= 0.90,
        "one_session_aum_delay_and_pre_entry_snapshot": causal,
        "no_fitted_magnitude_threshold": True,
        "no_post_entry_return_pnl_or_recent_outcome_read": True,
    }
    payload = {
        "status": "returns_blind_leveraged_fund_rebalance_capacity_audit",
        "sources": {
            "official_proshares_nav_aum": str(
                flowlib.NAV_PATH.relative_to(ROOT)
            ),
            "official_proshares_nav_sha256": flow_audit["source"][
                "historical_nav_sha256"
            ],
            "spy_closing_auction_snapshots": str(
                CLOSING_SNAPSHOTS.relative_to(ROOT)
            ),
            "arca_spy_bars": str(v19.ARCA_SPY.relative_to(ROOT)),
            "equs_spy_bars": str(v19.EQUS_SPY.relative_to(ROOT)),
            "new_databento_calls_or_purchases": False,
        },
        "rule": {
            "fund_leverage": FUNDS,
            "fund_rebalance_formula": (
                "L * (L - 1) * prior_session_AUM * "
                "SPY_return_to_15_49"
            ),
            "spy_bar": PRIMARY_SPY_BAR,
            "auction_cutoff": PRIMARY_AUCTION_CUTOFF,
            "auction_quantity": "side-signed total_imbalance_qty",
            "candidate": (
                "trade the model direction only when sign(model equivalent "
                "SPY shares + auction signed shares) equals model direction"
            ),
            "cash": "auction opposing capacity overwhelms the model or model is zero",
            "magnitude_threshold": None,
            "prospective_entry_not_before": PLANNED_ENTRY,
        },
        "development_2021_2023": development,
        "auction_cutoff_stability": cutoff_stability,
        "independent_feed_overlap_2023": feed_overlap,
        "distinctness": distinctness,
        "entry_quote_evidence": entry_evidence,
        "gates": gates,
        "gate_passed": all(gates.values()),
        "decision": (
            "allow_formal_critique_and_preregistration_only"
            if all(gates.values())
            else "reject_before_pnl"
        ),
        "states": [row for _, row in sorted(primary.items())],
        "independent_states_2023": [
            row for _, row in sorted(equs.items())
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
