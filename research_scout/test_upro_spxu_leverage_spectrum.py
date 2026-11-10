"""Evaluate the preregistered persistent leverage-spectrum odd-mode signal."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_market_diffusion as diffusion
from research_scout import test_upro_spxu_expanding_analog_memory as analog
from research_scout import test_upro_spxu_flow_geometry as flow
from research_scout import test_upro_spxu_variance_state as common

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "upro_spxu_leverage_spectrum_results_v14.json"
REPORT = ROOT / "research_scout" / "UPRO_SPXU_LEVERAGE_SPECTRUM_REPORT_V14.md"
END = pd.Timestamp("2025-12-31")
EQUS_FRACTIONAL_BARS = (
    ROOT
    / "external_artifacts"
    / "databento_fractional_etf"
    / "EQUS.MINI"
    / "bars"
    / "spy_sh_ohlcv_1m_2023-03-28_2026-01-01.dbn.zst"
)
EQUS_PAIR_BARS = (
    ROOT
    / "external_artifacts"
    / "databento_leveraged_etf"
    / "EQUS.MINI"
    / "bars"
    / "upro_spxu_ohlcv_1m_2023-03-28_2026-01-01.dbn.zst"
)
EQUS_PAIR_BBO = (
    ROOT
    / "external_artifacts"
    / "databento_leveraged_etf"
    / "EQUS.MINI"
    / "bbo"
    / "upro_spxu_bbo_1m_2023-03-28_2026-01-01.dbn.zst"
)
EQUS_CONDITIONS = (
    ROOT
    / "external_artifacts"
    / "databento_fractional_etf"
    / "EQUS.MINI"
    / "dataset_condition_2023_2025.json"
)


@dataclass(frozen=True)
class SpectrumState:
    date: pd.Timestamp
    odd_residual_one: float
    odd_residual_two: float
    low_odd_hour: float
    even_residual_one: float
    even_residual_two: float


def symbol_sessions(
    fractional_path: Path,
    pair_path: Path,
) -> dict[pd.Timestamp, dict[str, pd.DataFrame]]:
    """Load the four leverage points from matching venue/schema bar files."""
    fractional = base.load_dbn(fractional_path)
    pair = base.load_dbn(pair_path)
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]] = {}
    for symbol, frame in [
        ("SPY", fractional[fractional.symbol == "SPY"]),
        ("SH", fractional[fractional.symbol == "SH"]),
        ("UPRO", pair[pair.symbol == "UPRO"]),
        ("SPXU", pair[pair.symbol == "SPXU"]),
    ]:
        for day, bars in base.split_sessions(frame).items():
            sessions.setdefault(day, {})[symbol] = bars
    return sessions


def pair_bbo_sessions(path: Path) -> dict[pd.Timestamp, dict[str, pd.DataFrame]]:
    frame = base.load_dbn(path)
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]] = {}
    for symbol in ["UPRO", "SPXU"]:
        for day, quotes in base.split_sessions(frame[frame.symbol == symbol]).items():
            sessions.setdefault(day, {})[symbol] = quotes
    return sessions


def block_return(
    frame: pd.DataFrame,
    start: str,
    end: str,
) -> float | None:
    day = frame.index[0].normalize()
    start_parts = [int(part) for part in start.split(":")]
    end_parts = [int(part) for part in end.split(":")]
    start_stamp = day + pd.Timedelta(
        hours=start_parts[0], minutes=start_parts[1]
    )
    end_stamp = day + pd.Timedelta(hours=end_parts[0], minutes=end_parts[1])
    opening_row = base.exact_row(frame, start_stamp)
    closing_row = base.exact_row(frame, end_stamp)
    if opening_row is None or closing_row is None:
        return None
    opening = float(opening_row.open)
    closing = float(closing_row.close)
    if opening <= 0 or closing <= 0:
        return None
    value = math.log(closing / opening)
    return value if math.isfinite(value) else None


def spectrum_components(returns: dict[str, float]) -> tuple[float, float, float]:
    low_odd = (returns["SPY"] - returns["SH"]) / 2.0
    high_odd = (returns["UPRO"] - returns["SPXU"]) / 6.0
    odd_residual = high_odd - low_odd
    even_residual = (
        (returns["UPRO"] + returns["SPXU"]) / 18.0
        - (returns["SPY"] + returns["SH"]) / 2.0
    )
    return low_odd, odd_residual, even_residual


def build_states(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
) -> dict[pd.Timestamp, SpectrumState]:
    """Build two-block states without using any later-session observation."""
    states: dict[pd.Timestamp, SpectrumState] = {}
    required = {"SPY", "SH", "UPRO", "SPXU"}
    for day, instruments in sorted(sessions.items()):
        if day in excluded or not common.START <= day <= END:
            continue
        if not required.issubset(instruments):
            continue
        block_one: dict[str, float] = {}
        block_two: dict[str, float] = {}
        valid = True
        for symbol in sorted(required):
            one = block_return(instruments[symbol], "09:30", "09:59")
            two = block_return(instruments[symbol], "10:00", "10:29")
            if one is None or two is None:
                valid = False
                break
            block_one[symbol] = one
            block_two[symbol] = two
        if not valid:
            continue
        low_one, odd_one, even_one = spectrum_components(block_one)
        low_two, odd_two, even_two = spectrum_components(block_two)
        states[day] = SpectrumState(
            date=day,
            odd_residual_one=odd_one,
            odd_residual_two=odd_two,
            low_odd_hour=low_one + low_two,
            even_residual_one=even_one,
            even_residual_two=even_two,
        )
    return states


def frozen_direction(state: SpectrumState) -> int:
    if state.odd_residual_one > 0 and state.odd_residual_two > 0:
        return 1
    if state.odd_residual_one < 0 and state.odd_residual_two < 0:
        return -1
    return 0


def variant_direction(state: SpectrumState, variant: str) -> int:
    actual = frozen_direction(state)
    if actual == 0:
        return 0
    if variant == "actual":
        return actual
    if variant == "flipped":
        return -actual
    if variant == "market":
        return int(state.low_odd_hour > 0) - int(state.low_odd_hour < 0)
    raise ValueError(f"Unknown variant: {variant}")


def make_rows(
    states: dict[pd.Timestamp, SpectrumState],
    bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    variant: str,
    *,
    adverse_cents: float = 0.0,
    entry_delay_minutes: int = 0,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day, state in sorted(states.items()):
        direction = variant_direction(state, variant)
        if direction == 0:
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
                "direction": direction,
                "odd_residual_one": state.odd_residual_one,
                "odd_residual_two": state.odd_residual_two,
                "even_residual_one": state.even_residual_one,
                "even_residual_two": state.even_residual_two,
                "return": realized,
                "pnl_usd": 100.0 * realized,
            }
        )
    return rows


def evaluate(
    states: dict[pd.Timestamp, SpectrumState],
    bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
) -> dict[str, Any]:
    actual = make_rows(states, bbo, "actual")
    extra_cent = make_rows(states, bbo, "actual", adverse_cents=0.01)
    delayed = make_rows(states, bbo, "actual", entry_delay_minutes=5)
    market = make_rows(states, bbo, "market")
    flipped = make_rows(states, bbo, "flipped")
    periods = {
        "development": (common.START, common.DEVELOPMENT_END, 10),
        "holdout": (common.HOLDOUT_START, common.HOLDOUT_END, 5),
        "full": (common.START, END, 10),
    }
    result: dict[str, Any] = {}
    for name, (start, end, remove_best) in periods.items():
        result[name] = {
            "observed_bbo": common.summarize(
                common.subset(actual, start, end), remove_best=remove_best
            ),
            "one_extra_cent_each_fill": common.summarize(
                common.subset(extra_cent, start, end), remove_best=remove_best
            ),
            "five_minute_entry_delay": common.summarize(
                common.subset(delayed, start, end), remove_best=remove_best
            ),
            "low_leverage_market_direction_placebo": common.summarize(
                common.subset(market, start, end), remove_best=remove_best
            ),
            "sign_flipped_placebo": common.summarize(
                common.subset(flipped, start, end), remove_best=remove_best
            ),
            "spy_price_only_hurdle": common.spy_hurdle(
                spy_sessions, excluded, start, end
            ),
        }
    development = result["development"]
    observed = development["observed_bbo"]
    result["development_gate"] = diffusion.development_gate(
        observed,
        development["one_extra_cent_each_fill"],
        development["five_minute_entry_delay"],
        development["spy_price_only_hurdle"],
    )
    result["development_gate"].update(
        {
            "mean_trade_pnl_above_low_leverage_market_direction_placebo": (
                observed["mean_session_pnl_usd"]
                > development["low_leverage_market_direction_placebo"][
                    "mean_session_pnl_usd"
                ]
            ),
            "fixed_notional_pnl_above_sign_flipped_placebo": (
                observed["fixed_notional_pnl_usd"]
                > development["sign_flipped_placebo"]["fixed_notional_pnl_usd"]
            ),
        }
    )
    result["development_gate_passed"] = all(result["development_gate"].values())
    return result


def signal_agreement(
    primary: dict[pd.Timestamp, SpectrumState],
    consolidated: dict[pd.Timestamp, SpectrumState],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    common_days = sorted(
        day
        for day in set(primary).intersection(consolidated)
        if start <= day <= end
    )
    same = sum(
        frozen_direction(primary[day]) == frozen_direction(consolidated[day])
        for day in common_days
    )
    return {
        "common_complete_sessions": len(common_days),
        "identical_actions": same,
        "agreement_fraction": same / len(common_days) if common_days else 0.0,
    }


def add_holdout_gate(
    result: dict[str, Any],
    consolidated_holdout: dict[str, Any],
    agreement: dict[str, Any],
) -> None:
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
            observed["ending_cash_usd"]
            > holdout["spy_price_only_hurdle"]["ending_cash_usd"]
        ),
        "positive_after_one_extra_cent_each_fill": (
            holdout["one_extra_cent_each_fill"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_removing_five_best_sessions": (
            observed["pnl_without_best_5_sessions_usd"] > 0
        ),
        "mean_trade_pnl_above_low_leverage_market_direction_placebo": (
            observed["mean_session_pnl_usd"]
            > holdout["low_leverage_market_direction_placebo"][
                "mean_session_pnl_usd"
            ]
        ),
        "fixed_notional_pnl_above_sign_flipped_placebo": (
            observed["fixed_notional_pnl_usd"]
            > holdout["sign_flipped_placebo"]["fixed_notional_pnl_usd"]
        ),
        "consolidated_rebuilt_signal_and_execution_positive": (
            consolidated_holdout["fixed_notional_pnl_usd"] > 0
        ),
        "arca_consolidated_signal_agreement_at_least_90_percent": (
            agreement["agreement_fraction"] >= 0.9
        ),
    }
    result["holdout_gate_passed"] = all(result["holdout_gate"].values())


def fmt(value: float) -> str:
    return f"${value:,.2f}"


def render_report(payload: dict[str, Any]) -> str:
    result = payload["candidate"]
    verdict = (
        "**The frozen candidate cleared its historical gates, but remains "
        "paper-only because the research history is not independent.**"
        if result["holdout_gate_passed"]
        else "**The persistent odd-mode hypothesis is rejected unchanged.**"
    )
    lines = [
        "# UPRO/SPXU Persistent Leverage-Spectrum Odd Mode v14",
        "",
        "## Verdict",
        "",
        verdict,
        "",
        "The signal requires the +/-3 versus +/-1 odd residual to retain the "
        "same sign in both completed morning half-hours.",
        "",
        "Implementation audit: the first run accidentally required every "
        "one-minute trade bar inside each block and was superseded. The saved "
        "result uses the frozen exact boundary-return definition. No formula, "
        "clock, sign, or gate changed.",
        "",
    ]
    for period, title in [
        ("development", "Development: 2021-2023"),
        ("holdout", "Secondary holdout: 2024-2025"),
        ("full", "Full retrospective span"),
    ]:
        current = result[period]
        lines.extend(
            [
                f"## {title}",
                "",
                "| Rule | Trades/week | Ending cash | Fixed-$100 P&L | "
                "Mean/trade | PF |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for key, label in [
            ("observed_bbo", "Persistent odd mode"),
            ("low_leverage_market_direction_placebo", "Low-leverage direction"),
            ("sign_flipped_placebo", "Sign-flipped residual"),
        ]:
            summary = current[key]
            lines.append(
                f"| {label} | {summary['trades_per_week']:.2f} | "
                f"{fmt(summary['ending_cash_usd'])} | "
                f"{fmt(summary['fixed_notional_pnl_usd'])} | "
                f"{fmt(summary['mean_session_pnl_usd'])} | "
                f"{summary['profit_factor']:.3f} |"
            )
        lines.extend(
            [
                "",
                "Price-only SPY ending cash: "
                f"{fmt(current['spy_price_only_hurdle']['ending_cash_usd'])}.",
                "",
            ]
        )
    development = result["development"]
    audit = result["consolidated_rebuild"]
    agreement = result["signal_agreement_audit"]
    lines.extend(
        [
            "## Robustness and identification",
            "",
            f"- Development with one extra cent at each fill: "
            f"{fmt(development['one_extra_cent_each_fill']['fixed_notional_pnl_usd'])}.",
            f"- Development with five-minute entry delay: "
            f"{fmt(development['five_minute_entry_delay']['fixed_notional_pnl_usd'])}.",
            f"- Development after removing ten best sessions: "
            f"{fmt(development['observed_bbo']['pnl_without_best_10_sessions_usd'])}.",
            f"- Consolidated rebuilt 2024-2025 P&L: "
            f"{fmt(audit['holdout']['fixed_notional_pnl_usd'])}.",
            f"- ARCA/consolidated identical-action rate: "
            f"{agreement['agreement_fraction']:.1%} "
            f"over {agreement['common_complete_sessions']} common sessions.",
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
    lines.extend(
        [
            "",
            "Preimplementation critique: "
            "`research_scout/UPRO_SPXU_LEVERAGE_SPECTRUM_PREIMPLEMENTATION_CRITIQUE_V14.md`.",
            "",
            "Machine-readable results: "
            "`research_scout/upro_spxu_leverage_spectrum_results_v14.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def load_condition_dates(path: Path) -> set[pd.Timestamp]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        pd.Timestamp(row["date"])
        for row in payload["conditions"]
        if row["condition"] == "degraded"
    }


def main() -> None:
    primary_sessions = symbol_sessions(analog.OLD_SPY, analog.OLD_PAIR_BARS)
    primary_bbo = pair_bbo_sessions(analog.OLD_PAIR_BBO)
    primary_excluded = load_condition_dates(analog.OLD_CONDITIONS)
    primary_states = build_states(primary_sessions, primary_excluded)
    spy_sessions = {
        day: instruments["SPY"]
        for day, instruments in primary_sessions.items()
        if "SPY" in instruments
    }
    result = evaluate(
        primary_states,
        primary_bbo,
        spy_sessions,
        primary_excluded,
    )

    consolidated_sessions = symbol_sessions(
        EQUS_FRACTIONAL_BARS, EQUS_PAIR_BARS
    )
    consolidated_bbo = pair_bbo_sessions(EQUS_PAIR_BBO)
    consolidated_excluded = load_condition_dates(EQUS_CONDITIONS)
    consolidated_states = build_states(
        consolidated_sessions, consolidated_excluded
    )
    audit_start = pd.Timestamp("2023-03-28")
    audit_end = pd.Timestamp("2025-12-31")
    consolidated_rows = make_rows(
        consolidated_states, consolidated_bbo, "actual"
    )
    result["consolidated_rebuild"] = {
        "full_overlap": common.summarize(
            common.subset(
                consolidated_rows, audit_start, audit_end
            ),
            remove_best=5,
        ),
        "holdout": common.summarize(
            common.subset(
                consolidated_rows, common.HOLDOUT_START, common.HOLDOUT_END
            ),
            remove_best=5,
        ),
    }
    result["signal_agreement_audit"] = signal_agreement(
        primary_states,
        consolidated_states,
        audit_start,
        audit_end,
    )
    add_holdout_gate(
        result,
        result["consolidated_rebuild"]["holdout"],
        result["signal_agreement_audit"],
    )
    payload = {
        "specification": (
            "research_scout/upro_spxu_leverage_spectrum_prereg_v14.json"
        ),
        "status": (
            "candidate_survived"
            if result["holdout_gate_passed"]
            else "candidate_rejected"
        ),
        "primary_complete_spectrum_sessions": len(primary_states),
        "consolidated_complete_spectrum_sessions": len(consolidated_states),
        "candidate": result,
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    REPORT.write_text(render_report(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
