"""Evaluate preregistered UPRO/SPXU temporal flow-geometry hypotheses."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_expanding_analog_memory as analog
from research_scout import test_upro_spxu_variance_state as common

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "upro_spxu_flow_geometry_results_v10.json"
REPORT = ROOT / "research_scout" / "UPRO_SPXU_FLOW_GEOMETRY_REPORT_V10.md"
ENTRY = time(10, 31)
EXIT = time(15, 55)
WARMUP = 20
CANDIDATES = [
    "relative_dollar_flow_surprise",
    "price_volume_phase_compass",
    "lagged_flow_price_transfer",
]
LABELS = {
    "relative_dollar_flow_surprise": "Relative Dollar-Flow Surprise",
    "price_volume_phase_compass": "Price–Volume Phase Compass",
    "lagged_flow_price_transfer": "Lagged Flow–Price Transfer",
}


@dataclass(frozen=True)
class FlowState:
    date: pd.Timestamp
    total_upro: float
    total_spxu: float
    scale_upro: float | None
    scale_spxu: float | None
    normalized_upro: np.ndarray
    normalized_spxu: np.ndarray
    spy_returns: np.ndarray
    upro_midpoints: np.ndarray | None
    spxu_midpoints: np.ndarray | None


def expected_index(day: pd.Timestamp, tz: Any) -> pd.DatetimeIndex:
    return pd.date_range(
        start=pd.Timestamp.combine(day.date(), time(9, 30)).tz_localize(tz),
        periods=60,
        freq="min",
    )


def dollar_flow_array(frame: pd.DataFrame, day: pd.Timestamp) -> np.ndarray:
    values = np.zeros(60, dtype=float)
    window = base.between(frame, "09:30", "10:29")
    if window.empty:
        return values
    start = pd.Timestamp.combine(day.date(), time(9, 30)).tz_localize(
        window.index.tz
    )
    for stamp, row in window.iterrows():
        offset = int((stamp - start).total_seconds() // 60)
        if 0 <= offset < 60:
            typical = (
                float(row.open)
                + float(row.high)
                + float(row.low)
                + float(row.close)
            ) / 4.0
            values[offset] += typical * float(row.volume)
    return values


def spy_return_array(frame: pd.DataFrame, day: pd.Timestamp) -> np.ndarray | None:
    window = base.between(frame, "09:30", "10:29")
    if len(window) != 60 or not window.index.equals(
        expected_index(day, window.index.tz)
    ):
        return None
    prices = np.r_[float(window.iloc[0].open), window.close.astype(float)]
    values = np.diff(np.log(prices))
    return values if np.isfinite(values).all() else None


def midpoint_array(frame: pd.DataFrame, day: pd.Timestamp) -> np.ndarray | None:
    values: list[float] = []
    for timestamp in expected_index(day, frame.index.tz):
        row = base.quote_at(frame, timestamp, 0)
        if row is None:
            return None
        values.append(base.midpoint(row))
    array = np.asarray(values, dtype=float)
    return array if np.isfinite(array).all() and np.all(array > 0) else None


def build_states(
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    pair_bars: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
) -> dict[pd.Timestamp, FlowState]:
    states: dict[pd.Timestamp, FlowState] = {}
    history_upro: list[float] = []
    history_spxu: list[float] = []
    for day in sorted(spy_sessions):
        if day in excluded or not common.START <= day <= common.END:
            continue
        bars = pair_bars.get(day, {})
        quotes = bbo.get(day, {})
        if not {"UPRO", "SPXU"}.issubset(bars):
            continue
        spy_returns = spy_return_array(spy_sessions[day], day)
        if spy_returns is None:
            continue
        upro = dollar_flow_array(bars["UPRO"], day)
        spxu = dollar_flow_array(bars["SPXU"], day)
        total_upro = float(upro.sum())
        total_spxu = float(spxu.sum())
        if total_upro <= 0 or total_spxu <= 0:
            continue
        scale_upro = (
            float(np.median(history_upro[-WARMUP:]))
            if len(history_upro) >= WARMUP
            else None
        )
        scale_spxu = (
            float(np.median(history_spxu[-WARMUP:]))
            if len(history_spxu) >= WARMUP
            else None
        )
        upro_midpoints = None
        spxu_midpoints = None
        if {"UPRO", "SPXU"}.issubset(quotes):
            upro_midpoints = midpoint_array(quotes["UPRO"], day)
            spxu_midpoints = midpoint_array(quotes["SPXU"], day)
        states[day] = FlowState(
            date=day,
            total_upro=total_upro,
            total_spxu=total_spxu,
            scale_upro=scale_upro,
            scale_spxu=scale_spxu,
            normalized_upro=(
                upro / scale_upro if scale_upro is not None else upro * math.nan
            ),
            normalized_spxu=(
                spxu / scale_spxu if scale_spxu is not None else spxu * math.nan
            ),
            spy_returns=spy_returns,
            upro_midpoints=upro_midpoints,
            spxu_midpoints=spxu_midpoints,
        )
        history_upro.append(total_upro)
        history_spxu.append(total_spxu)
    return states


def signed_area(midpoints: np.ndarray, flow: np.ndarray) -> float:
    price_path = np.log(midpoints / midpoints[0])
    flow_path = np.cumsum(flow)
    flow_path /= flow_path[-1]
    return float(
        np.sum(
            price_path[:-1] * np.diff(flow_path)
            - flow_path[:-1] * np.diff(price_path)
        )
    )


def score(candidate: str, state: FlowState) -> float | None:
    if state.scale_upro is None or state.scale_spxu is None:
        return None
    if candidate == "relative_dollar_flow_surprise":
        return (
            state.total_upro / state.scale_upro
            - state.total_spxu / state.scale_spxu
        )
    if candidate == "price_volume_phase_compass":
        if state.upro_midpoints is None or state.spxu_midpoints is None:
            return None
        upro_area = signed_area(state.upro_midpoints, state.normalized_upro)
        spxu_area = signed_area(state.spxu_midpoints, state.normalized_spxu)
        return spxu_area - upro_area
    if candidate == "lagged_flow_price_transfer":
        denominator = state.normalized_upro + state.normalized_spxu
        relative = np.divide(
            state.normalized_upro - state.normalized_spxu,
            denominator,
            out=np.zeros_like(denominator),
            where=denominator > 0,
        )
        return float(np.dot(relative[:-1], state.spy_returns[1:]))
    raise ValueError(f"Unknown candidate: {candidate}")


def trade_return(
    bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    day: pd.Timestamp,
    symbol: str,
    *,
    adverse_cents: float = 0.0,
    entry_delay_minutes: int = 0,
) -> float | None:
    frame = bbo.get(day, {}).get(symbol)
    if frame is None:
        return None
    entry_clock = (
        pd.Timestamp.combine(day.date(), ENTRY)
        + pd.Timedelta(minutes=entry_delay_minutes)
    ).time()
    entry = base.quote_at(frame, common.stamp(day, entry_clock, frame.index.tz), 0)
    exit_row = base.quote_at(frame, common.stamp(day, EXIT, frame.index.tz), 0)
    if entry is None or exit_row is None:
        return None
    buy = float(entry.ask_px_00) + adverse_cents
    sell = float(exit_row.bid_px_00) - adverse_cents
    if buy <= 0 or sell <= 0:
        return None
    return sell / buy - 1.0


def make_rows(
    candidate: str,
    states: dict[pd.Timestamp, FlowState],
    execution_bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    *,
    adverse_cents: float = 0.0,
    entry_delay_minutes: int = 0,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day, state in sorted(states.items()):
        value = score(candidate, state)
        if value is None or not math.isfinite(value) or value == 0:
            continue
        symbol = "UPRO" if value > 0 else "SPXU"
        realized = trade_return(
            execution_bbo,
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


def gate(
    observed: dict[str, Any],
    extra_cent: dict[str, Any],
    delayed: dict[str, Any],
    spy: dict[str, Any],
) -> dict[str, bool]:
    years = observed.get("year_pnl_usd", {})
    instruments = observed.get("instrument_pnl_usd", {})
    return {
        "minimum_two_trades_per_week": observed["trades_per_week"] >= 2.0,
        "profit_factor_at_least_one": observed["profit_factor"] >= 1.0,
        "each_development_year_positive": all(
            years.get(str(year), 0.0) > 0 for year in [2021, 2022, 2023]
        ),
        "bullish_and_bearish_positive": all(
            instruments.get(symbol, 0.0) > 0 for symbol in ["UPRO", "SPXU"]
        ),
        "ending_cash_above_spy": (
            observed["ending_cash_usd"] > spy["ending_cash_usd"]
        ),
        "positive_after_one_extra_cent_each_fill": (
            extra_cent["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_five_minute_entry_delay": (
            delayed["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_removing_ten_best_sessions": (
            observed["pnl_without_best_10_sessions_usd"] > 0
        ),
    }


def evaluate(
    candidate: str,
    states: dict[pd.Timestamp, FlowState],
    bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    hurdles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    observed_rows = make_rows(candidate, states, bbo)
    cent_rows = make_rows(candidate, states, bbo, adverse_cents=0.01)
    delay_rows = make_rows(candidate, states, bbo, entry_delay_minutes=5)
    periods = {
        "development": (common.START, common.DEVELOPMENT_END, 10),
        "holdout": (common.HOLDOUT_START, common.HOLDOUT_END, 5),
        "extension_2026": (common.EXTENSION_START, common.END, 5),
        "full": (common.START, common.END, 10),
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
    result["development_gate"] = gate(
        development["observed_bbo"],
        development["one_extra_cent_each_fill"],
        development["five_minute_entry_delay"],
        hurdles["development"],
    )
    result["development_gate_passed"] = all(result["development_gate"].values())
    holdout = result["holdout"]
    holdout_observed = holdout["observed_bbo"]
    years = holdout_observed.get("year_pnl_usd", {})
    instruments = holdout_observed.get("instrument_pnl_usd", {})
    result["holdout_gate"] = {
        "development_gate_passed": result["development_gate_passed"],
        "each_holdout_year_positive": all(
            years.get(str(year), 0.0) > 0 for year in [2024, 2025]
        ),
        "bullish_and_bearish_positive": all(
            instruments.get(symbol, 0.0) > 0 for symbol in ["UPRO", "SPXU"]
        ),
        "ending_cash_above_spy": (
            holdout_observed["ending_cash_usd"]
            > hurdles["holdout"]["ending_cash_usd"]
        ),
        "positive_after_one_extra_cent_each_fill": (
            holdout["one_extra_cent_each_fill"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_removing_five_best_sessions": (
            holdout_observed["pnl_without_best_5_sessions_usd"] > 0
        ),
    }
    result["holdout_gate_passed"] = all(result["holdout_gate"].values())
    return result


def fmt(value: float) -> str:
    return f"${value:,.2f}"


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# UPRO/SPXU Temporal Flow Geometry v10",
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
        lines.append(
            "**Frozen-rule survivors:** " + ", ".join(survivors) + "."
        )
    else:
        lines.append(
            "**No flow-geometry candidate passed both development and holdout. "
            "None is approved for paper or live trading.**"
        )
    lines.extend(
        [
            "",
            "Rules were frozen before outcome calculation. Each score uses the "
            "completed 09:30–10:29 window, waits through 10:30, buys fractional "
            "UPRO or SPXU at the observed 10:31 ask, and sells at the observed "
            "15:55 bid.",
            "",
        ]
    )
    for period, title in [
        ("development", "Development: 2021–2023"),
        ("holdout", "Secondary holdout: 2024–2025"),
        ("extension_2026", "2026 diagnostic extension"),
        ("full", "Full retrospective span: 2021–2026 YTD"),
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
    lines.extend(["", "## Robustness", ""])
    for name, result in payload["candidates"].items():
        development = result["development"]
        full = result["full"]["observed_bbo"]
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
            f"full-period result without ten best sessions "
            f"{fmt(full['pnl_without_best_10_sessions_usd'])}. "
            f"Failed development gates: {', '.join(failures) if failures else 'none'}."
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "These were deliberately unusual hypotheses: cross-session normalized "
            "capital flow, signed price–volume path area, and lagged flow-to-price "
            "transfer. They were not optimized, sign-flipped, thresholded, or "
            "combined after results.",
            "",
            "A historical pass would still not prove the outcome was not luck. A "
            "survivor would require forward paper validation because the broader "
            "research program has already inspected every historical year.",
            "",
            "Machine-readable results: "
            "`research_scout/upro_spxu_flow_geometry_results_v10.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    spy_sessions, pair_bars, bbo = analog.combined_sessions()
    consolidated_bbo = common.load_consolidated_bbo()
    excluded = analog.excluded_dates()
    states = build_states(spy_sessions, pair_bars, bbo, excluded)
    periods = {
        "development": (common.START, common.DEVELOPMENT_END),
        "holdout": (common.HOLDOUT_START, common.HOLDOUT_END),
        "extension_2026": (common.EXTENSION_START, common.END),
        "full": (common.START, common.END),
    }
    hurdles = {
        name: common.spy_hurdle(spy_sessions, excluded, start, end)
        for name, (start, end) in periods.items()
    }
    candidates = {
        name: evaluate(name, states, bbo, hurdles) for name in CANDIDATES
    }
    audit_start = pd.Timestamp("2023-03-28")
    audit_end = pd.Timestamp("2025-12-31")
    for name, result in candidates.items():
        arca_rows = make_rows(name, states, bbo)
        consolidated_rows = make_rows(name, states, consolidated_bbo)
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
    always_upro: list[dict[str, Any]] = []
    for day in sorted(states):
        realized = trade_return(bbo, day, "UPRO")
        if realized is not None:
            always_upro.append(
                {
                    "date": day,
                    "symbol": "UPRO",
                    "return": realized,
                    "pnl_usd": 100.0 * realized,
                }
            )
    payload = {
        "specification": "research_scout/upro_spxu_flow_geometry_prereg_v10.json",
        "status": (
            "candidate_survived"
            if any(result["holdout_gate_passed"] for result in candidates.values())
            else "all_candidates_rejected"
        ),
        "eligible_signal_sessions": len(states),
        "spy_price_only_hurdles": hurdles,
        "always_upro_same_window": {
            name: common.summarize(
                common.subset(always_upro, start, end), remove_best=10
            )
            for name, (start, end) in periods.items()
        },
        "candidates": candidates,
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    REPORT.write_text(render_report(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
