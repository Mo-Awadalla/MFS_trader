"""Evaluate the preregistered index-simplex coherence hypothesis."""

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
OUTPUT = ROOT / "research_scout" / "upro_spxu_index_simplex_results_v13.json"
REPORT = ROOT / "research_scout" / "UPRO_SPXU_INDEX_SIMPLEX_REPORT_V13.md"
END = pd.Timestamp("2026-06-29")


def classify(values: dict[str, dict[str, float]]) -> tuple[str, float] | None:
    """Classify same-sign breadth as coherent or outside the return simplex."""
    qqq = values["QQQ"]["hour"]
    iwm = values["IWM"]["hour"]
    spy = values["SPY"]["hour"]
    if (
        qqq == 0
        or iwm == 0
        or math.copysign(1.0, qqq) != math.copysign(1.0, iwm)
    ):
        return None
    direction = 1.0 if qqq > 0 else -1.0
    label = "coherent" if min(qqq, iwm) <= spy <= max(qqq, iwm) else "incoherent"
    return label, direction


def make_rows(
    variant: str,
    signals: dict[pd.Timestamp, dict[str, dict[str, float]]],
    bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    *,
    adverse_cents: float = 0.0,
    entry_delay_minutes: int = 0,
) -> list[dict[str, Any]]:
    """Create causal executable rows for a prespecified simplex variant."""
    rows: list[dict[str, Any]] = []
    for day, values in sorted(signals.items()):
        if day in excluded or not common.START <= day <= END:
            continue
        classification = classify(values)
        if classification is None:
            continue
        label, direction = classification
        if variant != "unfiltered" and label != variant:
            continue
        symbol = "UPRO" if direction > 0 else "SPXU"
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
                "classification": label,
                "return": realized,
                "pnl_usd": 100.0 * realized,
            }
        )
    return rows


def mean_edge_gate(
    candidate: dict[str, Any],
    unfiltered: dict[str, Any],
    incoherent: dict[str, Any],
) -> dict[str, bool]:
    """Test whether containment adds value rather than merely selecting trades."""
    candidate_mean = candidate["mean_session_pnl_usd"]
    return {
        "mean_trade_pnl_above_unfiltered_breadth_consensus": (
            candidate_mean > unfiltered["mean_session_pnl_usd"]
        ),
        "mean_trade_pnl_above_incoherent_same_sign_sessions": (
            candidate_mean > incoherent["mean_session_pnl_usd"]
        ),
    }


def evaluate(
    signals: dict[pd.Timestamp, dict[str, dict[str, float]]],
    bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    hurdles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate the frozen candidate, contrasts, and robustness conditions."""
    observed_rows = make_rows("coherent", signals, bbo, excluded)
    cent_rows = make_rows(
        "coherent", signals, bbo, excluded, adverse_cents=0.01
    )
    delay_rows = make_rows(
        "coherent", signals, bbo, excluded, entry_delay_minutes=5
    )
    unfiltered_rows = make_rows("unfiltered", signals, bbo, excluded)
    incoherent_rows = make_rows("incoherent", signals, bbo, excluded)
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
            "unfiltered_breadth_consensus": common.summarize(
                common.subset(unfiltered_rows, start, end),
                remove_best=remove_best,
            ),
            "incoherent_same_sign_sessions": common.summarize(
                common.subset(incoherent_rows, start, end),
                remove_best=remove_best,
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
    result["development_gate"].update(
        mean_edge_gate(
            development["observed_bbo"],
            development["unfiltered_breadth_consensus"],
            development["incoherent_same_sign_sessions"],
        )
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
    result["holdout_gate"].update(
        mean_edge_gate(
            observed,
            holdout["unfiltered_breadth_consensus"],
            holdout["incoherent_same_sign_sessions"],
        )
    )
    result["holdout_gate_passed"] = all(result["holdout_gate"].values())
    return result


def fmt(value: float) -> str:
    return f"${value:,.2f}"


def render_report(payload: dict[str, Any]) -> str:
    """Render a concise human-readable audit."""
    result = payload["candidate"]
    verdict = (
        "**The frozen rule passed development and holdout gates. It remains "
        "research-only pending future paper validation.**"
        if result["holdout_gate_passed"]
        else "**The frozen rule failed. It must not be repaired on these data.**"
    )
    lines = [
        "# UPRO/SPXU Index-Simplex Coherence v13",
        "",
        "## Verdict",
        "",
        verdict,
        "",
        "QQQ and IWM must agree in first-hour direction, while SPY must lie "
        "inside their return interval. Entry is the 10:31 ask and exit is the "
        "15:55 bid.",
        "",
    ]
    for period, title in [
        ("development", "Development: 2021-2023"),
        ("holdout", "Secondary holdout: 2024-2025"),
        ("extension_2026", "2026 diagnostic through June 29"),
        ("full", "Full retrospective span"),
    ]:
        current = result[period]
        lines.extend(
            [
                f"## {title}",
                "",
                "| Group | Trades/week | Ending cash | Fixed-$100 P&L | "
                "Mean/trade | PF |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for key, label in [
            ("observed_bbo", "Coherent simplex"),
            ("unfiltered_breadth_consensus", "Unfiltered breadth"),
            ("incoherent_same_sign_sessions", "Outside simplex"),
        ]:
            summary = current[key]
            lines.append(
                f"| {label} | {summary['trades_per_week']:.2f} | "
                f"{fmt(summary['ending_cash_usd'])} | "
                f"{fmt(summary['fixed_notional_pnl_usd'])} | "
                f"{fmt(summary['mean_session_pnl_usd'])} | "
                f"{summary['profit_factor']:.3f} |"
            )
        spy = current["spy_price_only_hurdle"]
        lines.extend(
            [
                "",
                f"Price-only SPY ending cash: {fmt(spy['ending_cash_usd'])}.",
                "",
            ]
        )
    development = result["development"]
    lines.extend(
        [
            "## Robustness",
            "",
            f"- Development with one extra cent at each fill: "
            f"{fmt(development['one_extra_cent_each_fill']['fixed_notional_pnl_usd'])}.",
            f"- Development with five-minute entry delay: "
            f"{fmt(development['five_minute_entry_delay']['fixed_notional_pnl_usd'])}.",
            f"- Development after removing ten best sessions: "
            f"{fmt(development['observed_bbo']['pnl_without_best_10_sessions_usd'])}.",
            "",
            "## Gate failures",
            "",
        ]
    )
    for gate_name in ["development_gate", "holdout_gate"]:
        failures = [
            key.replace("_", " ")
            for key, passed in result[gate_name].items()
            if not passed
        ]
        lines.append(
            f"- {gate_name.replace('_', ' ').title()}: "
            f"{', '.join(failures) if failures else 'none'}."
        )
    audit = result["consolidated_execution_audit"]
    lines.extend(
        [
            "",
            "## Consolidated execution audit",
            "",
            f"- ARCA fixed-$100 P&L: "
            f"{fmt(audit['arca']['fixed_notional_pnl_usd'])}.",
            f"- Consolidated fixed-$100 P&L: "
            f"{fmt(audit['consolidated']['fixed_notional_pnl_usd'])}.",
            "",
            "Preimplementation critique: "
            "`research_scout/UPRO_SPXU_INDEX_SIMPLEX_PREIMPLEMENTATION_CRITIQUE_V13.md`.",
            "",
            "Machine-readable results: "
            "`research_scout/upro_spxu_index_simplex_results_v13.json`.",
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
    result = evaluate(signals, bbo, excluded, hurdles)
    audit_start = pd.Timestamp("2023-03-28")
    audit_end = pd.Timestamp("2025-12-31")
    arca_rows = make_rows("coherent", signals, bbo, excluded)
    consolidated_rows = make_rows(
        "coherent", signals, consolidated_bbo, excluded
    )
    result["consolidated_execution_audit"] = {
        "period": "2023-03-28 through 2025-12-31",
        "arca": common.summarize(
            common.subset(arca_rows, audit_start, audit_end), remove_best=5
        ),
        "consolidated": common.summarize(
            common.subset(consolidated_rows, audit_start, audit_end),
            remove_best=5,
        ),
    }
    payload = {
        "specification": "research_scout/upro_spxu_index_simplex_prereg_v13.json",
        "status": (
            "candidate_survived"
            if result["holdout_gate_passed"]
            else "candidate_rejected"
        ),
        "complete_cross_market_sessions": len(signals),
        "candidate": result,
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    REPORT.write_text(render_report(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
