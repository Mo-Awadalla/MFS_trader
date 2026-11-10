"""Evaluate preregistered cross-market state-transition hypotheses."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import test_upro_spxu_cross_market_diffusion as diffusion
from research_scout import test_upro_spxu_expanding_analog_memory as analog
from research_scout import test_upro_spxu_flow_geometry as flow
from research_scout import test_upro_spxu_variance_state as common

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT / "research_scout" / "upro_spxu_cross_market_transitions_results_v12.json"
)
REPORT = ROOT / "research_scout" / "UPRO_SPXU_CROSS_MARKET_TRANSITIONS_REPORT_V12.md"
END = pd.Timestamp("2026-06-29")
CANDIDATES = [
    "synchronized_breadth_acceleration",
    "consensus_formation_event",
    "leadership_curvature",
]
LABELS = {
    "synchronized_breadth_acceleration": "Synchronized Breadth Acceleration",
    "consensus_formation_event": "Consensus Formation Event",
    "leadership_curvature": "Leadership Curvature",
}


def same_nonzero_sign(left: float, right: float) -> bool:
    """Return whether two nonzero values share a sign."""
    return (
        left != 0
        and right != 0
        and math.copysign(1.0, left) == math.copysign(1.0, right)
    )


def signal(candidate: str, values: dict[str, dict[str, float]]) -> float | None:
    """Calculate a frozen transition score using completed first-hour bars."""
    qqq_first = values["QQQ"]["first"]
    qqq_second = values["QQQ"]["second"]
    iwm_first = values["IWM"]["first"]
    iwm_second = values["IWM"]["second"]
    if candidate == "synchronized_breadth_acceleration":
        qqq_acceleration = qqq_second - qqq_first
        iwm_acceleration = iwm_second - iwm_first
        if not same_nonzero_sign(qqq_acceleration, iwm_acceleration):
            return None
        return 1.0 if qqq_acceleration > 0 else -1.0
    if candidate == "consensus_formation_event":
        first_agreed = same_nonzero_sign(qqq_first, iwm_first)
        if (
            qqq_first == 0
            or iwm_first == 0
            or first_agreed
            or not same_nonzero_sign(qqq_second, iwm_second)
        ):
            return None
        return 1.0 if qqq_second > 0 else -1.0
    if candidate == "leadership_curvature":
        score = (iwm_second - qqq_second) - (iwm_first - qqq_first)
        return score if score != 0 else None
    raise ValueError(f"Unknown candidate: {candidate}")


def make_rows(
    candidate: str,
    signals: dict[pd.Timestamp, dict[str, dict[str, float]]],
    bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    *,
    adverse_cents: float = 0.0,
    entry_delay_minutes: int = 0,
) -> list[dict[str, Any]]:
    """Join a causal signal to later observed leveraged-ETF BBO fills."""
    rows: list[dict[str, Any]] = []
    for day, values in sorted(signals.items()):
        if day in excluded or not common.START <= day <= END:
            continue
        value = signal(candidate, values)
        if value is None or not math.isfinite(value):
            continue
        symbol = "UPRO" if value > 0 else "SPXU"
        realized = flow.trade_return(
            bbo,
            day,
            symbol,
            adverse_cents=adverse_cents,
            entry_delay_minutes=entry_delay_minutes,
        )
        if realized is None:
            continue
        rows.append(
            {
                "date": day,
                "symbol": symbol,
                "score": value,
                "return": realized,
                "pnl_usd": 100.0 * realized,
            }
        )
    return rows


def evaluate(
    candidate: str,
    signals: dict[pd.Timestamp, dict[str, dict[str, float]]],
    bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    hurdles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate the frozen candidate across all prespecified partitions."""
    observed_rows = make_rows(candidate, signals, bbo, excluded)
    cent_rows = make_rows(
        candidate, signals, bbo, excluded, adverse_cents=0.01
    )
    delay_rows = make_rows(
        candidate, signals, bbo, excluded, entry_delay_minutes=5
    )
    periods = {
        "development": (common.START, common.DEVELOPMENT_END, 10),
        "holdout": (common.HOLDOUT_START, common.HOLDOUT_END, 5),
        "extension_2026": (common.EXTENSION_START, END, 5),
        "full": (common.START, END, 10),
    }
    result: dict[str, Any] = {}
    for name, (start, end, remove_best) in periods.items():
        result[name] = {
            "observed_bbo": common.summarize(
                common.subset(observed_rows, start, end), remove_best=remove_best
            ),
            "one_extra_cent_each_fill": common.summarize(
                common.subset(cent_rows, start, end), remove_best=remove_best
            ),
            "five_minute_entry_delay": common.summarize(
                common.subset(delay_rows, start, end), remove_best=remove_best
            ),
            "spy_price_only_hurdle": hurdles[name],
        }
    development = result["development"]
    result["development_gate"] = diffusion.development_gate(
        development["observed_bbo"],
        development["one_extra_cent_each_fill"],
        development["five_minute_entry_delay"],
        hurdles["development"],
    )
    result["development_gate_passed"] = all(result["development_gate"].values())
    holdout = result["holdout"]
    observed = holdout["observed_bbo"]
    years = observed.get("year_pnl_usd", {})
    instruments = observed.get("instrument_pnl_usd", {})
    result["holdout_gate"] = {
        "development_gate_passed": result["development_gate_passed"],
        "each_holdout_year_positive": all(
            years.get(str(year), 0.0) > 0 for year in [2024, 2025]
        ),
        "bullish_and_bearish_positive": all(
            instruments.get(symbol, 0.0) > 0 for symbol in ["UPRO", "SPXU"]
        ),
        "ending_cash_above_spy": (
            observed["ending_cash_usd"] > hurdles["holdout"]["ending_cash_usd"]
        ),
        "positive_after_one_extra_cent_each_fill": (
            holdout["one_extra_cent_each_fill"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_removing_five_best_sessions": (
            observed["pnl_without_best_5_sessions_usd"] > 0
        ),
    }
    result["holdout_gate_passed"] = all(result["holdout_gate"].values())
    return result


def fmt(value: float) -> str:
    return f"${value:,.2f}"


def render_report(payload: dict[str, Any]) -> str:
    """Render the compact human-readable research audit."""
    lines = [
        "# UPRO/SPXU Cross-Market Transitions v12",
        "",
        "## Verdict",
        "",
    ]
    survivors = [
        LABELS[name]
        for name, result in payload["candidates"].items()
        if result["holdout_gate_passed"]
    ]
    if survivors:
        lines.append("**Frozen-rule survivors:** " + ", ".join(survivors) + ".")
    else:
        lines.append(
            "**No transition candidate passed both development and holdout. "
            "None is approved for paper or live trading.**"
        )
    lines.extend(
        [
            "",
            "The three hypotheses were frozen before calculation and carry "
            "forward only the cross-market diffusion mechanism—not the prior "
            "Breadth Consensus rule or its favorable cases.",
            "",
        ]
    )
    for period, title in [
        ("development", "Development: 2021-2023"),
        ("holdout", "Secondary holdout: 2024-2025"),
        ("extension_2026", "2026 diagnostic extension through June 29"),
        ("full", "Full retrospective span"),
    ]:
        lines.extend(
            [
                f"## {title}",
                "",
                "| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | "
                "PF | SPY ending cash |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for name, result in payload["candidates"].items():
            summary = result[period]["observed_bbo"]
            spy = result[period]["spy_price_only_hurdle"]
            lines.append(
                f"| {LABELS[name]} | {summary['trades_per_week']:.2f} | "
                f"{fmt(summary['ending_cash_usd'])} | "
                f"{fmt(summary['fixed_notional_pnl_usd'])} | "
                f"{summary['profit_factor']:.3f} | "
                f"{fmt(spy['ending_cash_usd'])} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Consolidated execution audit: 2023-03-28 through 2025-12-31",
            "",
            "| Candidate | ARCA BBO P&L | Consolidated BBO P&L |",
            "|---|---:|---:|",
        ]
    )
    for name, result in payload["candidates"].items():
        audit = result["consolidated_execution_audit"]
        lines.append(
            f"| {LABELS[name]} | "
            f"{fmt(audit['arca']['fixed_notional_pnl_usd'])} | "
            f"{fmt(audit['consolidated']['fixed_notional_pnl_usd'])} |"
        )
    lines.extend(["", "## Frozen-gate audit", ""])
    for name, result in payload["candidates"].items():
        development = result["development"]
        failures = [
            key.replace("_", " ")
            for key, passed in result["development_gate"].items()
            if not passed
        ]
        lines.append(
            f"- **{LABELS[name]}:** development +1-cent stress "
            f"{fmt(development['one_extra_cent_each_fill']['fixed_notional_pnl_usd'])}; "
            f"five-minute delay "
            f"{fmt(development['five_minute_entry_delay']['fixed_notional_pnl_usd'])}; "
            "failed development gates: "
            f"{', '.join(failures) if failures else 'none'}."
        )
    lines.extend(
        [
            "",
            "Machine-readable results: "
            "`research_scout/upro_spxu_cross_market_transitions_results_v12.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    spy_sessions, _, bbo = analog.combined_sessions()
    consolidated_bbo = common.load_consolidated_bbo()
    excluded = analog.excluded_dates()
    signals = diffusion.load_signal_sessions()
    periods = {
        "development": (common.START, common.DEVELOPMENT_END),
        "holdout": (common.HOLDOUT_START, common.HOLDOUT_END),
        "extension_2026": (common.EXTENSION_START, END),
        "full": (common.START, END),
    }
    hurdles = {
        name: common.spy_hurdle(spy_sessions, excluded, start, end)
        for name, (start, end) in periods.items()
    }
    candidates = {
        name: evaluate(name, signals, bbo, excluded, hurdles)
        for name in CANDIDATES
    }
    audit_start = pd.Timestamp("2023-03-28")
    audit_end = pd.Timestamp("2025-12-31")
    for name, result in candidates.items():
        arca_rows = make_rows(name, signals, bbo, excluded)
        consolidated_rows = make_rows(
            name, signals, consolidated_bbo, excluded
        )
        result["consolidated_execution_audit"] = {
            "period": "2023-03-28 through 2025-12-31",
            "arca": common.summarize(
                common.subset(arca_rows, audit_start, audit_end), remove_best=5
            ),
            "consolidated": common.summarize(
                common.subset(
                    consolidated_rows, audit_start, audit_end
                ),
                remove_best=5,
            ),
        }
    payload = {
        "specification": (
            "research_scout/upro_spxu_cross_market_transitions_prereg_v12.json"
        ),
        "status": (
            "candidate_survived"
            if any(result["holdout_gate_passed"] for result in candidates.values())
            else "all_candidates_rejected"
        ),
        "complete_cross_market_sessions": len(signals),
        "spy_price_only_hurdles": hurdles,
        "candidates": candidates,
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    REPORT.write_text(render_report(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
