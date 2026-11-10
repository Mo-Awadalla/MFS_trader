"""Evaluate the preregistered UPRO/SPXU variance-state hypotheses."""

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

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "upro_spxu_variance_state_results_v9.json"
REPORT = ROOT / "research_scout" / "UPRO_SPXU_VARIANCE_STATE_REPORT_V9.md"
ENTRY = time(9, 31)
EXIT = time(15, 55)
REBALANCE = time(12, 31)
WARMUP = 20
START = pd.Timestamp("2021-01-04")
DEVELOPMENT_END = pd.Timestamp("2023-12-29")
HOLDOUT_START = pd.Timestamp("2024-01-02")
HOLDOUT_END = pd.Timestamp("2025-12-31")
EXTENSION_START = pd.Timestamp("2026-01-02")
END = pd.Timestamp("2026-07-24")


@dataclass(frozen=True)
class SessionState:
    date: pd.Timestamp
    realized_variance: float
    downside_share: float
    baseline_variance: float | None


def stamp(day: pd.Timestamp, clock: time, tz: Any) -> pd.Timestamp:
    return pd.Timestamp.combine(day.date(), clock).tz_localize(tz)


def quote(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    day: pd.Timestamp,
    symbol: str,
    clock: time,
) -> pd.Series | None:
    frame = sessions.get(day, {}).get(symbol)
    if frame is None:
        return None
    return base.quote_at(frame, stamp(day, clock, frame.index.tz), 0)


def load_consolidated_bbo() -> dict[pd.Timestamp, dict[str, pd.DataFrame]]:
    frame = base.load_dbn(base.MINI_BBO_PATH)
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]] = {}
    for symbol in ["UPRO", "SPXU"]:
        for day, quotes in base.split_sessions(frame[frame.symbol == symbol]).items():
            sessions.setdefault(day, {})[symbol] = quotes
    return sessions


def complete_spy_window(frame: pd.DataFrame) -> pd.DataFrame | None:
    window = base.between(frame, "09:30", "15:59")
    if len(window) != 390:
        return None
    expected = pd.date_range(
        start=window.index[0].normalize() + pd.Timedelta(hours=9, minutes=30),
        periods=390,
        freq="min",
        tz=window.index.tz,
    )
    if not window.index.equals(expected):
        return None
    return window


def build_states(
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
) -> dict[pd.Timestamp, SessionState]:
    raw: list[tuple[pd.Timestamp, float, float]] = []
    for day in sorted(spy_sessions):
        if day in excluded or day < START or day > END:
            continue
        window = complete_spy_window(spy_sessions[day])
        if window is None:
            continue
        close = window.close.astype(float).to_numpy()
        minute_returns = np.diff(np.log(close))
        variance = float(np.square(minute_returns).sum())
        if not math.isfinite(variance) or variance <= 0:
            continue
        downside = float(np.square(minute_returns[minute_returns < 0]).sum())
        raw.append((day, variance, downside / variance))

    states: dict[pd.Timestamp, SessionState] = {}
    variances: list[float] = []
    for day, variance, downside_share in raw:
        baseline = (
            float(np.median(variances[-WARMUP:]))
            if len(variances) >= WARMUP
            else None
        )
        states[day] = SessionState(day, variance, downside_share, baseline)
        variances.append(variance)
    return states


def prior_state(
    day: pd.Timestamp,
    ordered_days: list[pd.Timestamp],
    states: dict[pd.Timestamp, SessionState],
) -> SessionState | None:
    position = ordered_days.index(day)
    for prior_day in reversed(ordered_days[:position]):
        state = states.get(prior_day)
        if state is not None:
            return state
    return None


def single_leg_return(
    bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    day: pd.Timestamp,
    symbol: str,
    *,
    entry_delay_minutes: int = 0,
    adverse_cents: float = 0.0,
) -> float | None:
    entry_clock = (
        pd.Timestamp.combine(day.date(), ENTRY)
        + pd.Timedelta(minutes=entry_delay_minutes)
    ).time()
    entry = quote(bbo, day, symbol, entry_clock)
    exit_row = quote(bbo, day, symbol, EXIT)
    if entry is None or exit_row is None:
        return None
    buy = float(entry.ask_px_00) + adverse_cents
    sell = float(exit_row.bid_px_00) - adverse_cents
    if buy <= 0 or sell <= 0:
        return None
    return sell / buy - 1.0


def paired_return(
    bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    day: pd.Timestamp,
    *,
    entry_delay_minutes: int = 0,
    adverse_cents: float = 0.0,
) -> float | None:
    entry_clock = (
        pd.Timestamp.combine(day.date(), ENTRY)
        + pd.Timedelta(minutes=entry_delay_minutes)
    ).time()
    rows: dict[str, tuple[pd.Series, pd.Series, pd.Series]] = {}
    for symbol in ["UPRO", "SPXU"]:
        entry = quote(bbo, day, symbol, entry_clock)
        middle = quote(bbo, day, symbol, REBALANCE)
        exit_row = quote(bbo, day, symbol, EXIT)
        if entry is None or middle is None or exit_row is None:
            return None
        rows[symbol] = (entry, middle, exit_row)

    shares: dict[str, float] = {}
    for symbol in ["UPRO", "SPXU"]:
        buy = float(rows[symbol][0].ask_px_00) + adverse_cents
        if buy <= 0:
            return None
        shares[symbol] = 50.0 / buy

    u_bid = float(rows["UPRO"][1].bid_px_00) - adverse_cents
    u_ask = float(rows["UPRO"][1].ask_px_00) + adverse_cents
    s_bid = float(rows["SPXU"][1].bid_px_00) - adverse_cents
    s_ask = float(rows["SPXU"][1].ask_px_00) + adverse_cents
    if min(u_bid, u_ask, s_bid, s_ask) <= 0:
        return None
    u_value = shares["UPRO"] * u_bid
    s_value = shares["SPXU"] * s_bid
    if u_value > s_value:
        proceeds = (u_value - s_value) / (1.0 + s_bid / s_ask)
        shares["UPRO"] -= proceeds / u_bid
        shares["SPXU"] += proceeds / s_ask
    elif s_value > u_value:
        proceeds = (s_value - u_value) / (1.0 + u_bid / u_ask)
        shares["SPXU"] -= proceeds / s_bid
        shares["UPRO"] += proceeds / u_ask

    ending = 0.0
    for symbol in ["UPRO", "SPXU"]:
        sell = float(rows[symbol][2].bid_px_00) - adverse_cents
        if sell <= 0:
            return None
        ending += shares[symbol] * sell
    return ending / 100.0 - 1.0


def candidate_symbol(candidate: str, state: SessionState) -> str | None:
    quiet = state.realized_variance <= float(state.baseline_variance)
    if candidate == "quiet_variance_carry":
        return "UPRO" if quiet else None
    if candidate == "downside_variance_handoff":
        stressed_downside = (
            not quiet
            and state.downside_share > 0.5
        )
        return "SPXU" if stressed_downside else "UPRO"
    raise ValueError(f"Unknown directional candidate: {candidate}")


def make_rows(
    candidate: str,
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    states: dict[pd.Timestamp, SessionState],
    excluded: set[pd.Timestamp],
    *,
    entry_delay_minutes: int = 0,
    adverse_cents: float = 0.0,
) -> list[dict[str, Any]]:
    ordered_days = sorted(
        day
        for day in spy_sessions
        if START <= day <= END and day not in excluded
    )
    rows: list[dict[str, Any]] = []
    for day in ordered_days:
        state = prior_state(day, ordered_days, states)
        if state is None or state.baseline_variance is None:
            continue
        if candidate == "paired_variance_harvest":
            value = paired_return(
                bbo,
                day,
                entry_delay_minutes=entry_delay_minutes,
                adverse_cents=adverse_cents,
            )
            symbol = "UPRO+SPXU"
        else:
            symbol = candidate_symbol(candidate, state)
            if symbol is None:
                continue
            value = single_leg_return(
                bbo,
                day,
                symbol,
                entry_delay_minutes=entry_delay_minutes,
                adverse_cents=adverse_cents,
            )
        if value is None:
            continue
        rows.append(
            {
                "date": day,
                "symbol": symbol,
                "return": float(value),
                "pnl_usd": 100.0 * float(value),
                "prior_realized_variance": state.realized_variance,
                "prior_downside_share": state.downside_share,
                "prior_baseline_variance": state.baseline_variance,
            }
        )
    return rows


def profit_factor(pnl: np.ndarray) -> float:
    gains = float(pnl[pnl > 0].sum())
    losses = -float(pnl[pnl < 0].sum())
    return gains / losses if losses > 0 else math.inf


def period_weeks(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return max((rows[-1]["date"] - rows[0]["date"]).days / 7.0, 1.0)


def summarize(rows: list[dict[str, Any]], remove_best: int = 0) -> dict[str, Any]:
    if not rows:
        return {
            "sessions": 0,
            "trades_per_week": 0.0,
            "fixed_notional_pnl_usd": 0.0,
            "ending_cash_usd": 100.0,
            "profit_factor": 0.0,
        }
    returns = np.array([row["return"] for row in rows], dtype=float)
    pnl = 100.0 * returns
    cash_curve = 100.0 * np.cumprod(1.0 + returns)
    peaks = np.maximum.accumulate(np.r_[100.0, cash_curve])
    drawdowns = np.r_[100.0, cash_curve] - peaks
    years: dict[str, float] = {}
    symbols: dict[str, float] = {}
    for row in rows:
        years.setdefault(str(row["date"].year), 0.0)
        years[str(row["date"].year)] += float(row["pnl_usd"])
        symbols.setdefault(row["symbol"], 0.0)
        symbols[row["symbol"]] += float(row["pnl_usd"])
    without_best = pnl
    if remove_best > 0 and len(pnl) > remove_best:
        without_best = np.sort(pnl)[:-remove_best]
    return {
        "sessions": len(rows),
        "trades_per_week": len(rows) / period_weeks(rows),
        "fixed_notional_pnl_usd": float(pnl.sum()),
        "ending_cash_usd": float(cash_curve[-1]),
        "return_pct": float(cash_curve[-1] - 100.0),
        "mean_session_pnl_usd": float(pnl.mean()),
        "win_rate": float(np.mean(pnl > 0)),
        "profit_factor": float(profit_factor(pnl)),
        "maximum_drawdown_usd": float(drawdowns.min()),
        "worst_session_usd": float(pnl.min()),
        f"pnl_without_best_{remove_best}_sessions_usd": float(without_best.sum()),
        "year_pnl_usd": years,
        "instrument_pnl_usd": symbols,
    }


def subset(
    rows: list[dict[str, Any]],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[dict[str, Any]]:
    return [row for row in rows if start <= row["date"] <= end]


def spy_hurdle(
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    days = sorted(
        day
        for day in spy_sessions
        if start <= day <= end
        and day not in excluded
        and complete_spy_window(spy_sessions[day]) is not None
    )
    first = complete_spy_window(spy_sessions[days[0]])
    last = complete_spy_window(spy_sessions[days[-1]])
    assert first is not None and last is not None
    ending = 100.0 * float(last.iloc[-1].close) / float(first.iloc[0].open)
    return {
        "first_date": str(days[0].date()),
        "last_date": str(days[-1].date()),
        "ending_cash_usd": ending,
        "return_pct": ending - 100.0,
        "price_only": True,
    }


def development_gate(
    summary: dict[str, Any],
    extra_cent: dict[str, Any],
    delay: dict[str, Any],
    spy: dict[str, Any],
) -> dict[str, bool]:
    years = summary.get("year_pnl_usd", {})
    return {
        "minimum_two_trades_per_week": summary["trades_per_week"] >= 2.0,
        "profit_factor_at_least_one": summary["profit_factor"] >= 1.0,
        "each_development_year_positive": all(
            years.get(str(year), 0.0) > 0 for year in [2021, 2022, 2023]
        ),
        "ending_cash_above_spy": (
            summary["ending_cash_usd"] > spy["ending_cash_usd"]
        ),
        "positive_after_one_extra_cent_each_fill": (
            extra_cent["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_five_minute_entry_delay": (
            delay["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_removing_ten_best_sessions": (
            summary["pnl_without_best_10_sessions_usd"] > 0
        ),
    }


def evaluate_candidate(
    candidate: str,
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    states: dict[pd.Timestamp, SessionState],
    excluded: set[pd.Timestamp],
    spy_hurdles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    base_rows = make_rows(candidate, spy_sessions, bbo, states, excluded)
    cent_rows = make_rows(
        candidate,
        spy_sessions,
        bbo,
        states,
        excluded,
        adverse_cents=0.01,
    )
    delay_rows = make_rows(
        candidate,
        spy_sessions,
        bbo,
        states,
        excluded,
        entry_delay_minutes=5,
    )
    periods = {
        "development": (START, DEVELOPMENT_END, 10),
        "holdout": (HOLDOUT_START, HOLDOUT_END, 5),
        "extension_2026": (EXTENSION_START, END, 5),
        "full": (START, END, 10),
    }
    result: dict[str, Any] = {}
    for name, (start, end, remove_best) in periods.items():
        period_rows = subset(base_rows, start, end)
        period_cent = subset(cent_rows, start, end)
        period_delay = subset(delay_rows, start, end)
        result[name] = {
            "observed_bbo": summarize(period_rows, remove_best=remove_best),
            "one_extra_cent_each_fill": summarize(
                period_cent, remove_best=remove_best
            ),
            "five_minute_entry_delay": summarize(
                period_delay, remove_best=remove_best
            ),
            "spy_price_only_hurdle": spy_hurdles[name],
        }
    gate = development_gate(
        result["development"]["observed_bbo"],
        result["development"]["one_extra_cent_each_fill"],
        result["development"]["five_minute_entry_delay"],
        spy_hurdles["development"],
    )
    result["development_gate"] = gate
    result["development_gate_passed"] = all(gate.values())
    holdout = result["holdout"]["observed_bbo"]
    holdout_cent = result["holdout"]["one_extra_cent_each_fill"]
    holdout_years = holdout.get("year_pnl_usd", {})
    holdout_gate = {
        "development_gate_passed": result["development_gate_passed"],
        "each_holdout_year_positive": all(
            holdout_years.get(str(year), 0.0) > 0 for year in [2024, 2025]
        ),
        "ending_cash_above_spy": (
            holdout["ending_cash_usd"]
            > spy_hurdles["holdout"]["ending_cash_usd"]
        ),
        "positive_after_one_extra_cent_each_fill": (
            holdout_cent["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_removing_five_best_sessions": (
            holdout["pnl_without_best_5_sessions_usd"] > 0
        ),
    }
    result["holdout_gate"] = holdout_gate
    result["holdout_gate_passed"] = all(holdout_gate.values())
    return result


def fmt(value: float) -> str:
    return f"${value:,.2f}"


def render_report(payload: dict[str, Any]) -> str:
    labels = {
        "quiet_variance_carry": "Quiet-Variance Carry",
        "downside_variance_handoff": "Downside-Variance Handoff",
        "paired_variance_harvest": "Paired Variance Harvest",
    }
    lines = [
        "# UPRO/SPXU Variance-State Research v9",
        "",
        "## Verdict",
        "",
    ]
    survivors = [
        name
        for name, result in payload["candidates"].items()
        if result["holdout_gate_passed"]
    ]
    if survivors:
        lines.append(
            "The following candidates passed the frozen development and holdout "
            f"gates: {', '.join(labels[name] for name in survivors)}."
        )
    else:
        lines.append(
            "**No candidate passed both the frozen development and secondary-"
            "holdout gates. None is suitable for paper or live trading.**"
        )
    lines.extend(
        [
            "",
            "The rules were saved in "
            "`research_scout/upro_spxu_variance_state_prereg_v9.json` before "
            "outcomes were calculated. Results use observed asks for buys and "
            "observed bids for sells, fractional shares, a $100 starting account, "
            "full reinvestment, no overnight position, and no parameter search.",
            "",
            "## Development: 2021-2023",
            "",
            "| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | PF | "
            "SPY ending cash | Gate |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for name, result in payload["candidates"].items():
        summary = result["development"]["observed_bbo"]
        spy = result["development"]["spy_price_only_hurdle"]
        lines.append(
            f"| {labels[name]} | {summary['trades_per_week']:.2f} | "
            f"{fmt(summary['ending_cash_usd'])} | "
            f"{fmt(summary['fixed_notional_pnl_usd'])} | "
            f"{summary['profit_factor']:.3f} | "
            f"{fmt(spy['ending_cash_usd'])} | "
            f"{'Pass' if result['development_gate_passed'] else 'Fail'} |"
        )
    lines.extend(
        [
            "",
            "## Secondary holdout: 2024-2025",
            "",
            "| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | PF | "
            "SPY ending cash | Holdout gate |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for name, result in payload["candidates"].items():
        summary = result["holdout"]["observed_bbo"]
        spy = result["holdout"]["spy_price_only_hurdle"]
        lines.append(
            f"| {labels[name]} | {summary['trades_per_week']:.2f} | "
            f"{fmt(summary['ending_cash_usd'])} | "
            f"{fmt(summary['fixed_notional_pnl_usd'])} | "
            f"{summary['profit_factor']:.3f} | "
            f"{fmt(spy['ending_cash_usd'])} | "
            f"{'Pass' if result['holdout_gate_passed'] else 'Fail'} |"
        )
    lines.extend(
        [
            "",
            "## Full retrospective span: 2021-2026 YTD",
            "",
            "| Candidate | Sessions | Ending cash | Fixed-$100 P&L | PF | "
            "Max drawdown | SPY ending cash |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for name, result in payload["candidates"].items():
        summary = result["full"]["observed_bbo"]
        spy = result["full"]["spy_price_only_hurdle"]
        lines.append(
            f"| {labels[name]} | {summary['sessions']} | "
            f"{fmt(summary['ending_cash_usd'])} | "
            f"{fmt(summary['fixed_notional_pnl_usd'])} | "
            f"{summary['profit_factor']:.3f} | "
            f"{fmt(summary['maximum_drawdown_usd'])} | "
            f"{fmt(spy['ending_cash_usd'])} |"
        )
    lines.extend(
        [
            "",
            "## Consolidated execution audit: 2023-03-28 through 2025-12-31",
            "",
            "| Candidate | ARCA BBO P&L | Consolidated BBO P&L |",
            "|---|---:|---:|",
        ]
    )
    for name, result in payload["candidates"].items():
        audit = result["consolidated_execution_audit"]
        lines.append(
            f"| {labels[name]} | "
            f"{fmt(audit['arca']['fixed_notional_pnl_usd'])} | "
            f"{fmt(audit['consolidated']['fixed_notional_pnl_usd'])} |"
        )
    lines.extend(
        [
            "",
            "## Frozen-rule explanations",
            "",
            "### Quiet-Variance Carry",
            "",
            "Buy UPRO for the next cash session only when the prior session's "
            "realized one-minute variance is no greater than the median of the "
            "prior 20 completed sessions. The claim is a volatility-drag gate on "
            "the positive equity risk premium, not a price-trend signal.",
            "",
            "### Downside-Variance Handoff",
            "",
            "Buy SPXU only after an above-median-variance session in which negative "
            "minute returns contributed more than half of realized variance; buy "
            "UPRO otherwise. The claim is persistence of deleveraging pressure, "
            "measured from semivariance rather than return direction.",
            "",
            "### Paired Variance Harvest",
            "",
            "Buy $50 each of UPRO and SPXU, rebalance their liquidation values to "
            "50/50 at 12:31 by crossing the observed quotes, and liquidate at "
            "15:55. The claim is constant-mix harvesting of oscillation without "
            "forecasting SPY direction.",
            "",
            "## Robustness and interpretation",
            "",
        ]
    )
    for name, result in payload["candidates"].items():
        dev = result["development"]
        full = result["full"]
        failed = [
            key.replace("_", " ")
            for key, passed in result["development_gate"].items()
            if not passed
        ]
        lines.append(
            f"- **{labels[name]}:** development +1-cent stress "
            f"{fmt(dev['one_extra_cent_each_fill']['fixed_notional_pnl_usd'])}; "
            f"five-minute delay "
            f"{fmt(dev['five_minute_entry_delay']['fixed_notional_pnl_usd'])}; "
            f"full-period P&L without ten best sessions "
            f"{fmt(full['observed_bbo']['pnl_without_best_10_sessions_usd'])}. "
            f"Failed development gates: {', '.join(failed) if failed else 'none'}."
        )
    lines.extend(
        [
            "",
            "A backtest cannot establish that an outcome was “not luck.” The "
            "pre-registration, untouched rule application, year splits, cost "
            "stress, delayed execution, winner deletion, and SPY hurdle reduce "
            "the chance of fooling ourselves; they do not eliminate it.",
            "",
            "The simulation also assumes the full account can be redeployed each "
            "eligible session. A literal US cash account can be constrained by "
            "settlement and good-faith-violation rules, so operational feasibility "
            "is separate from signal performance.",
            "",
            "Machine-readable results: "
            "`research_scout/upro_spxu_variance_state_results_v9.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    spy_sessions, _, bbo = analog.combined_sessions()
    consolidated_bbo = load_consolidated_bbo()
    excluded = analog.excluded_dates()
    states = build_states(spy_sessions, excluded)
    periods = {
        "development": (START, DEVELOPMENT_END),
        "holdout": (HOLDOUT_START, HOLDOUT_END),
        "extension_2026": (EXTENSION_START, END),
        "full": (START, END),
    }
    hurdles = {
        name: spy_hurdle(spy_sessions, excluded, start, end)
        for name, (start, end) in periods.items()
    }
    candidates = {
        name: evaluate_candidate(
            name, spy_sessions, bbo, states, excluded, hurdles
        )
        for name in [
            "quiet_variance_carry",
            "downside_variance_handoff",
            "paired_variance_harvest",
        ]
    }
    consolidated_start = pd.Timestamp("2023-03-28")
    consolidated_end = pd.Timestamp("2025-12-31")
    for name, result in candidates.items():
        arca_rows = make_rows(name, spy_sessions, bbo, states, excluded)
        consolidated_rows = make_rows(
            name, spy_sessions, consolidated_bbo, states, excluded
        )
        result["consolidated_execution_audit"] = {
            "period": "2023-03-28 through 2025-12-31",
            "arca": summarize(
                subset(arca_rows, consolidated_start, consolidated_end),
                remove_best=5,
            ),
            "consolidated": summarize(
                subset(
                    consolidated_rows,
                    consolidated_start,
                    consolidated_end,
                ),
                remove_best=5,
            ),
        }
    always_rows: list[dict[str, Any]] = []
    for day in sorted(bbo):
        if day in excluded or not START <= day <= END:
            continue
        value = single_leg_return(bbo, day, "UPRO")
        if value is not None:
            always_rows.append(
                {
                    "date": day,
                    "symbol": "UPRO",
                    "return": value,
                    "pnl_usd": 100.0 * value,
                }
            )
    payload = {
        "specification": "research_scout/upro_spxu_variance_state_prereg_v9.json",
        "status": (
            "candidate_survived"
            if any(result["holdout_gate_passed"] for result in candidates.values())
            else "all_candidates_rejected"
        ),
        "eligible_spy_state_sessions": len(states),
        "excluded_degraded_sessions": len(excluded),
        "spy_price_only_hurdles": hurdles,
        "always_upro_intraday_benchmark": {
            name: summarize(subset(always_rows, start, end), remove_best=10)
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
