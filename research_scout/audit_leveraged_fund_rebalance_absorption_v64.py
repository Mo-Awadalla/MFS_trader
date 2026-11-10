"""Returns-blind audit of opposing-auction absorption deficit v64."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_leveraged_fund_rebalance_capacity_v63 as v63
from research_scout import audit_leveraged_etf_official_open_basis_v48 as v48
from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay
from research_scout import audit_upro_spxu_premarket_wrapper_premium as v19

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research_scout"
    / "leveraged_fund_rebalance_absorption_returns_blind_audit_v64.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "LEVERAGED_FUND_REBALANCE_ABSORPTION_AUDIT_V64.md"
)


def absorption_states(
    raw: dict[pd.Timestamp, dict[str, Any]]
) -> dict[pd.Timestamp, dict[str, Any]]:
    result: dict[pd.Timestamp, dict[str, Any]] = {}
    for day, source in raw.items():
        row = dict(source)
        model_direction = int(row["model_direction"])
        auction_direction = v63.sign(
            float(row["auction_signed_spy_shares"])
        )
        opposite = (
            model_direction != 0
            and auction_direction == -model_direction
        )
        model_overruns = abs(
            float(row["model_equivalent_spy_shares"])
        ) > abs(float(row["auction_signed_spy_shares"]))
        row["auction_direction"] = auction_direction
        row["opposing_auction"] = opposite
        row["model_strictly_exceeds_opposing_capacity"] = model_overruns
        row["action"] = (
            "UPRO"
            if opposite and model_overruns and model_direction > 0
            else "SPXU"
            if opposite and model_overruns and model_direction < 0
            else "CASH"
        )
        result[day] = row
    return result


def opposite_only_actions(
    states: dict[pd.Timestamp, dict[str, Any]]
) -> dict[pd.Timestamp, str]:
    return {
        day: (
            "UPRO"
            if row["opposing_auction"] and row["model_direction"] > 0
            else "SPXU"
            if row["opposing_auction"] and row["model_direction"] < 0
            else "CASH"
        )
        for day, row in states.items()
    }


def render(payload: dict[str, Any]) -> str:
    development = payload["development_2021_2023"]
    failures = [
        name for name, passed in payload["gates"].items() if not passed
    ]
    lines = [
        "# Leveraged-Fund Rebalance Absorption Audit v64",
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
        "- Use the v63 four-fund prior-AUM rebalance model at 15:50.",
        "- Require the published SPY closing-auction imbalance to be strictly "
        "opposite modelled rebalance direction.",
        "- Trade only when absolute model-equivalent SPY shares strictly exceed "
        "that opposing auction quantity.",
        "- Enter no earlier than 15:51. Same-side auctions and capacity overruns "
        "by the auction are cash.",
        "",
        "## Development reachability",
        "",
        f"- Eligible sessions: {development['eligible_sessions']}",
        f"- Opposing-auction sessions: "
        f"{development['opposing_auction_sessions']}",
        f"- Signals: {development['signals']} "
        f"({development['signals_per_week']:.3f}/week)",
        f"- UPRO / SPXU: {development['upro_signals']} / "
        f"{development['spxu_signals']}",
        "- By year: "
        + ", ".join(
            f"{year}={count}"
            for year, count in development["signals_by_year"].items()
        ),
        f"- Model-size filter rejected "
        f"{development['opposing_capacity_rejection_share']:.3%} of "
        "opposing-auction sessions.",
        "",
        "## Stability and independence",
        "",
    ]
    for cutoff, item in payload["auction_cutoff_stability"].items():
        lines.append(
            f"- {cutoff}: "
            f"{item['identical_action_including_cash']:.3%} exact action"
        )
    lines.extend(
        [
            f"- ARCX/EQUS overlap action agreement: "
            f"{payload['independent_feed_overlap_2023']['identical_action_including_cash']:.3%}",
            f"- Agreement with rejected broad v63: "
            f"{payload['distinctness']['v63_broad_capacity_agreement']:.3%}",
            f"- Agreement with failed Closing Rebalance Torque: "
            f"{payload['distinctness']['failed_closing_torque_agreement']:.3%}",
            "",
            "## Entry evidence",
            "",
            f"- Primary exact 15:51 quote coverage: "
            f"{payload['entry_quote_evidence']['primary']['coverage']:.3%}",
            f"- Independent exact 15:51 quote coverage: "
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
            "No post-15:51 price, strategy P&L, or 2024-2025 outcome was read.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    expected, aum_states = v63.load_aum_states()
    _, previous_closes, statistic_integrity = v48.load_statistics()
    spy_arca = v19.spy_sessions(v19.ARCA_SPY)
    excluded_arca = relay.degraded(relay.ARCA_CONDITIONS)
    primary_raw = v63.build_states(
        expected,
        aum_states,
        v63.load_snapshots(v63.PRIMARY_AUCTION_CUTOFF),
        spy_arca,
        excluded_arca,
        previous_closes,
    )
    primary = absorption_states(primary_raw)

    adjacent = {}
    for cutoff in v63.ADJACENT_CUTOFFS:
        raw = v63.build_states(
            expected,
            aum_states,
            v63.load_snapshots(cutoff),
            spy_arca,
            excluded_arca,
            previous_closes,
        )
        adjacent[cutoff] = absorption_states(raw)
    cutoff_stability = {
        cutoff: v63.compare_states(primary, states)
        for cutoff, states in adjacent.items()
    }

    spy_equs = v19.spy_sessions(v19.EQUS_SPY)
    excluded_equs = relay.degraded(relay.EQUS_CONDITIONS)
    equs_raw = v63.build_states(
        expected,
        aum_states,
        v63.load_snapshots(v63.PRIMARY_AUCTION_CUTOFF),
        spy_equs,
        excluded_equs,
        previous_closes,
    )
    equs = absorption_states(equs_raw)
    feed_overlap = v63.compare_states(primary, equs)

    three_x_raw = v63.build_states(
        expected,
        aum_states,
        v63.load_snapshots(v63.PRIMARY_AUCTION_CUTOFF),
        spy_arca,
        excluded_arca,
        previous_closes,
        fund_subset=("UPRO", "SPXU"),
    )
    three_x = absorption_states(three_x_raw)
    torque = v63.old_closing_torque_actions(
        primary, spy_arca, previous_closes
    )
    v63_broad_actions = {
        day: str(row["action"]) for day, row in primary_raw.items()
    }
    distinctness = {
        "v63_broad_capacity_agreement": v63.action_agreement(
            primary, v63_broad_actions
        ),
        "failed_closing_torque_agreement": v63.action_agreement(
            primary, torque
        ),
        "three_x_only_action_agreement": v63.compare_states(
            primary, three_x
        )["identical_action_including_cash"],
    }

    signals = {
        day: row for day, row in primary.items() if row["action"] != "CASH"
    }
    counts = Counter(row["action"] for row in signals.values())
    opposing = sum(
        bool(row["opposing_auction"]) for row in primary.values()
    )
    rejected_capacity = sum(
        bool(row["opposing_auction"])
        and not bool(row["model_strictly_exceeds_opposing_capacity"])
        for row in primary.values()
    )
    signals_by_year = {
        str(year): sum(day.year == year for day in signals)
        for year in (2021, 2022, 2023)
    }
    development = {
        "expected_sessions": len(expected),
        "eligible_sessions": len(primary),
        "eligible_coverage": len(primary) / len(expected),
        "opposing_auction_sessions": opposing,
        "opposing_auction_share": opposing / max(len(primary), 1),
        "opposing_capacity_rejections": rejected_capacity,
        "opposing_capacity_rejection_share": rejected_capacity
        / max(opposing, 1),
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

    arca_pair = relay.sessions(relay.ARCA_PATH)
    equs_pair = relay.sessions(relay.EQUS_PATH)
    entry_evidence = {
        "primary": v63.entry_quote_coverage(
            primary, arca_pair, excluded_arca
        ),
        "independent": v63.entry_quote_coverage(
            equs, equs_pair, excluded_equs
        ),
    }
    causal = all(
        pd.Timestamp(row["source_date"]) < day
        and pd.Timestamp(row["snapshot_ts_event"])
        .tz_convert("America/New_York")
        .time()
        < pd.Timestamp(v63.PRIMARY_AUCTION_CUTOFF).time()
        for day, row in primary.items()
    )
    gates = {
        "all_four_funds_have_complete_positive_prior_aum": len(aum_states)
        == len(expected) - 1,
        "official_close_statistics_unique_and_positive": not statistic_integrity[
            "duplicate_symbol_sessions"
        ]
        and not statistic_integrity["invalid_prices"],
        "eligible_coverage_at_least_95_percent": development[
            "eligible_coverage"
        ]
        >= 0.95,
        "signal_frequency_at_least_2_per_week": development[
            "signals_per_week"
        ]
        >= 2.0,
        "at_least_90_signals_each_year": min(signals_by_year.values())
        >= 90,
        "both_sleeves_and_minority_at_least_20_percent": len(counts) == 2
        and development["minority_share"] >= 0.20,
        "selection_share_between_25_and_65_percent": 0.25
        <= development["selection_share"]
        <= 0.65,
        "aum_capacity_filter_rejects_5_to_40_percent_of_opposing_sessions": 0.05
        <= development["opposing_capacity_rejection_share"]
        <= 0.40,
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
        "distinct_from_v63_broad_capacity_below_80_percent": distinctness[
            "v63_broad_capacity_agreement"
        ]
        < 0.80,
        "distinct_from_failed_closing_torque_below_80_percent": distinctness[
            "failed_closing_torque_agreement"
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
        "status": "returns_blind_rebalance_absorption_deficit_audit",
        "sources": {
            "v63_data_audit_and_formula": (
                "research_scout/leveraged_fund_rebalance_capacity_"
                "returns_blind_audit_v63.json"
            ),
            "new_databento_calls_or_purchases": False,
        },
        "rule": {
            "model": (
                "sum over UPRO/SPXU/SSO/SDS of "
                "L*(L-1)*prior AUM*SPY return to completed 15:49 bar"
            ),
            "auction": (
                "latest side-signed SPY total_imbalance_qty strictly before "
                "15:50"
            ),
            "opposition_required": True,
            "capacity_test": (
                "absolute model-equivalent SPY shares strictly greater than "
                "absolute opposing auction shares"
            ),
            "action": "trade model direction; otherwise cash",
            "magnitude_threshold": None,
            "prospective_entry_not_before": "15:51",
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
