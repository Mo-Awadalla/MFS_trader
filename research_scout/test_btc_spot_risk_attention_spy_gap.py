"""Evaluate preregistered BTC risk-attention × SPY gap v32."""

from __future__ import annotations

import json
from datetime import time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_btc_spot_flow_baton_to_leveraged_etf as btc_v26
from research_scout import audit_btc_spot_risk_attention_spy_gap as audit
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16
from research_scout import test_upro_spxu_variance_state as common

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research_scout"
    / "btc_spot_risk_attention_spy_gap_results_v32.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "BTC_SPOT_RISK_ATTENTION_SPY_GAP_REPORT_V32.md"
)


def attention_states(
    btc: pd.DataFrame,
    days: list[pd.Timestamp],
) -> dict[pd.Timestamp, bool]:
    states: dict[pd.Timestamp, bool] = {}
    for day in days:
        state = btc_v26.signal_for(btc, day)
        states[day] = state is not None and int(state["direction"]) != 0
    return states


def variant_directions(
    gap: dict[pd.Timestamp, int],
    attention: dict[pd.Timestamp, bool],
    days: list[pd.Timestamp],
    variant: str,
) -> dict[pd.Timestamp, int]:
    if variant == "actual":
        return {
            day: gap.get(day, 0) if attention.get(day, False) else 0
            for day in days
        }
    if variant == "unfiltered_gap":
        return {day: gap.get(day, 0) for day in days}
    if variant == "shifted_attention":
        shifted: dict[pd.Timestamp, int] = {}
        for index, day in enumerate(days):
            prior_attention = (
                attention.get(days[index - 1], False) if index else False
            )
            shifted[day] = gap.get(day, 0) if prior_attention else 0
        return shifted
    raise ValueError(f"unknown variant: {variant}")


def make_rows(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    directions: dict[pd.Timestamp, int],
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    adverse_cents: float = 0.0,
    delay_minutes: int = 0,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day in sorted(sessions):
        if day in excluded or not start <= day <= end:
            continue
        direction = directions.get(day, 0)
        if direction == 0:
            continue
        symbol = "UPRO" if direction > 0 else "SPXU"
        quotes = sessions[day].get(symbol)
        if quotes is None:
            continue
        entry_stamp = v16.stamp(day, time(9, 31), quotes.index.tz) + timedelta(
            minutes=delay_minutes
        )
        exit_stamp = v16.stamp(day, time(15, 30), quotes.index.tz)
        entry = base.quote_at(quotes, entry_stamp, 0)
        exit_quote = base.quote_at(quotes, exit_stamp, 0)
        if entry is None or exit_quote is None:
            continue
        buy = float(entry.ask_px_00) + adverse_cents
        sell = float(exit_quote.bid_px_00) - adverse_cents
        if buy <= 0 or sell <= 0:
            continue
        realized = sell / buy - 1.0
        rows.append(
            {
                "date": day,
                "symbol": symbol,
                "direction": direction,
                "entry_time": entry_stamp,
                "exit_time": exit_stamp,
                "entry_ask": buy,
                "exit_bid": sell,
                "return": realized,
                "pnl_usd": 100.0 * realized,
            }
        )
    return rows


def evaluate(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    spy: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
    directions: dict[str, dict[pd.Timestamp, int]],
    start: pd.Timestamp,
    end: pd.Timestamp,
    remove_best: int,
) -> dict[str, Any]:
    actual = directions["actual"]
    return {
        "observed_bbo": common.summarize(
            make_rows(sessions, excluded, actual, start, end),
            remove_best,
        ),
        "extra_cent_each_fill": common.summarize(
            make_rows(
                sessions,
                excluded,
                actual,
                start,
                end,
                adverse_cents=0.01,
            ),
            remove_best,
        ),
        "five_minute_entry_delay": common.summarize(
            make_rows(
                sessions,
                excluded,
                actual,
                start,
                end,
                delay_minutes=5,
            ),
            remove_best,
        ),
        "unfiltered_spy_gap": common.summarize(
            make_rows(
                sessions,
                excluded,
                directions["unfiltered_gap"],
                start,
                end,
            ),
            remove_best,
        ),
        "one_session_shifted_attention": common.summarize(
            make_rows(
                sessions,
                excluded,
                directions["shifted_attention"],
                start,
                end,
            ),
            remove_best,
        ),
        "spy_price_only_hurdle": common.spy_hurdle(
            spy,
            excluded,
            start,
            end,
        ),
    }


def gate(
    result: dict[str, Any],
    years: list[int],
    remove_best: int,
) -> dict[str, bool]:
    observed = result["observed_bbo"]
    annual = observed.get("year_pnl_usd", {})
    instruments = observed.get("instrument_pnl_usd", {})
    unfiltered = result["unfiltered_spy_gap"]
    shifted = result["one_session_shifted_attention"]
    deleted_key = f"pnl_without_best_{remove_best}_sessions_usd"
    return {
        "minimum_two_trades_per_week": observed["trades_per_week"] >= 2.0,
        "profit_factor_strictly_above_one": observed["profit_factor"] > 1.0,
        "each_year_positive": all(
            annual.get(str(year), 0.0) > 0 for year in years
        ),
        "both_actuators_positive": all(
            instruments.get(symbol, 0.0) > 0
            for symbol in ["UPRO", "SPXU"]
        ),
        "ending_cash_above_spy": (
            observed["ending_cash_usd"]
            > result["spy_price_only_hurdle"]["ending_cash_usd"]
        ),
        "positive_after_extra_cent_each_fill": (
            result["extra_cent_each_fill"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_five_minute_delay": (
            result["five_minute_entry_delay"]["fixed_notional_pnl_usd"] > 0
        ),
        f"positive_after_removing_best_{remove_best}": (
            observed[deleted_key] > 0
        ),
        "mean_trade_above_unfiltered_spy_gap": (
            observed["mean_session_pnl_usd"]
            > unfiltered["mean_session_pnl_usd"]
        ),
        "winner_deleted_pnl_above_unfiltered_spy_gap": (
            observed[deleted_key] > unfiltered[deleted_key]
        ),
        "fixed_pnl_above_one_session_shifted_attention": (
            observed["fixed_notional_pnl_usd"]
            > shifted["fixed_notional_pnl_usd"]
        ),
    }


def render(payload: dict[str, Any]) -> str:
    development = payload["development"]
    observed = development["observed_bbo"]
    lines = [
        "# BTC Spot Risk-Attention Gate × SPY Gap v32",
        "",
        "## Verdict",
        "",
        f"**{payload['status'].replace('_', ' ').upper()}**",
        "",
        "The state sensor uses Binance BTCUSDT spot flow only. Direction comes "
        "from SPY's official cash gap. No futures, margin, or crypto "
        "derivative field is used.",
        "",
        "## Development",
        "",
        "| Trades/week | Fixed-$100 P&L | Ending cash | PF | SPY ending cash |",
        "|---:|---:|---:|---:|---:|",
        (
            f"| {observed['trades_per_week']:.3f} | "
            f"${observed['fixed_notional_pnl_usd']:.2f} | "
            f"${observed['ending_cash_usd']:.2f} | "
            f"{observed['profit_factor']:.3f} | "
            f"${development['spy_price_only_hurdle']['ending_cash_usd']:.2f} |"
        ),
        "",
        "## Frozen development gates",
        "",
    ]
    lines.extend(
        f"- {'PASS' if passed else 'FAIL'} — {name}"
        for name, passed in development["gate"].items()
    )
    if "holdout" in payload:
        holdout = payload["holdout"]
        h = holdout["observed_bbo"]
        lines.extend(
            [
                "",
                "## Secondary holdout",
                "",
                "| Trades/week | Fixed-$100 P&L | Ending cash | PF | SPY ending cash |",
                "|---:|---:|---:|---:|---:|",
                (
                    f"| {h['trades_per_week']:.3f} | "
                    f"${h['fixed_notional_pnl_usd']:.2f} | "
                    f"${h['ending_cash_usd']:.2f} | "
                    f"{h['profit_factor']:.3f} | "
                    f"${holdout['spy_price_only_hurdle']['ending_cash_usd']:.2f} |"
                ),
                "",
                "## Frozen holdout gates",
                "",
            ]
        )
        lines.extend(
            f"- {'PASS' if passed else 'FAIL'} — {name}"
            for name, passed in holdout["gate"].items()
        )
    lines.extend(
        [
            "",
            "Historical results are research evidence, not a profit guarantee "
            "or authorization for live capital.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    btc = btc_v26.load_btc()
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    equs_spy = base.split_sessions(base.load_dbn(audit.EQUS_SPY, "SPY"))
    arca_gap = audit.gap_directions(spy)
    equs_gap = audit.gap_directions(equs_spy)
    days = sorted(spy)
    attention = attention_states(btc, days)
    arca_directions = {
        variant: variant_directions(arca_gap, attention, days, variant)
        for variant in ["actual", "unfiltered_gap", "shifted_attention"]
    }
    equs_directions = {
        variant: variant_directions(equs_gap, attention, days, variant)
        for variant in ["actual", "unfiltered_gap", "shifted_attention"]
    }

    development = evaluate(
        arca,
        spy,
        arca_excluded,
        arca_directions,
        v16.START,
        v16.DEVELOPMENT_END,
        10,
    )
    development["gate"] = gate(development, [2021, 2022, 2023], 10)
    independent_development = evaluate(
        equs,
        spy,
        equs_excluded,
        equs_directions,
        pd.Timestamp("2023-03-28"),
        v16.DEVELOPMENT_END,
        5,
    )
    development["gate"]["independent_feed_overlap_pnl_positive"] = (
        independent_development["observed_bbo"]["fixed_notional_pnl_usd"] > 0
    )
    development["gate_passed"] = all(development["gate"].values())
    payload: dict[str, Any] = {
        "status": (
            "development_survivor"
            if development["gate_passed"]
            else "rejected_development_holdout_locked"
        ),
        "development": development,
        "independent_development_overlap": independent_development,
    }
    if development["gate_passed"]:
        holdout = evaluate(
            arca,
            spy,
            arca_excluded,
            arca_directions,
            v16.HOLDOUT_START,
            v16.HOLDOUT_END,
            5,
        )
        holdout["gate"] = gate(holdout, [2024, 2025], 5)
        independent_holdout = evaluate(
            equs,
            spy,
            equs_excluded,
            equs_directions,
            v16.HOLDOUT_START,
            v16.HOLDOUT_END,
            5,
        )
        holdout["gate"]["independent_feed_pnl_positive"] = (
            independent_holdout["observed_bbo"]["fixed_notional_pnl_usd"] > 0
        )
        holdout["gate_passed"] = all(holdout["gate"].values())
        full = evaluate(
            arca,
            spy,
            arca_excluded,
            arca_directions,
            v16.START,
            v16.HOLDOUT_END,
            10,
        )
        payload.update(
            {
                "status": (
                    "historical_survivor"
                    if holdout["gate_passed"]
                    else "rejected_holdout"
                ),
                "holdout": holdout,
                "independent_holdout": independent_holdout,
                "full": full,
            }
        )
    OUTPUT.write_text(
        json.dumps(payload, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    REPORT.write_text(render(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
