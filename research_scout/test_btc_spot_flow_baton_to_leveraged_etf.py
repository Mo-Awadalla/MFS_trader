"""Evaluate the preregistered BTC spot flow baton on UPRO/SPXU."""

from __future__ import annotations

import json
from datetime import time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_btc_spot_flow_baton_to_leveraged_etf as audit
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16
from research_scout import test_upro_spxu_variance_state as common

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research_scout"
    / "btc_spot_flow_baton_to_leveraged_etf_results_v26.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "BTC_SPOT_FLOW_BATON_TO_LEVERAGED_ETF_REPORT_V26.md"
)


def direction_for(state: dict[str, Any], variant: str) -> int:
    actual = int(state["direction"])
    if variant == "actual":
        return actual
    if variant == "flipped":
        return -actual
    if variant == "price_persistence":
        asia = float(state["asia"]["price_return"])
        europe = float(state["europe"]["price_return"])
        return (
            1
            if asia > 0 and europe > 0
            else -1
            if asia < 0 and europe < 0
            else 0
        )
    if variant == "europe_only":
        value = float(state["europe"]["imbalance"])
        return int(value > 0) - int(value < 0)
    raise ValueError(f"unknown variant: {variant}")


def make_rows(
    btc: pd.DataFrame,
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    variant: str = "actual",
    *,
    adverse_cents: float = 0.0,
    delay_minutes: int = 0,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day in sorted(sessions):
        if day in excluded or not start <= day <= end:
            continue
        state = audit.signal_for(btc, day)
        if state is None:
            continue
        direction = direction_for(state, variant)
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
    btc: pd.DataFrame,
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    spy: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    remove_best: int,
) -> dict[str, Any]:
    args = (btc, sessions, excluded, start, end)
    actual = common.summarize(make_rows(*args), remove_best)
    return {
        "observed_bbo": actual,
        "extra_cent_each_fill": common.summarize(
            make_rows(*args, adverse_cents=0.01),
            remove_best,
        ),
        "five_minute_entry_delay": common.summarize(
            make_rows(*args, delay_minutes=5),
            remove_best,
        ),
        "sign_flipped": common.summarize(
            make_rows(*args, variant="flipped"),
            remove_best,
        ),
        "btc_price_persistence": common.summarize(
            make_rows(*args, variant="price_persistence"),
            remove_best,
        ),
        "europe_flow_only": common.summarize(
            make_rows(*args, variant="europe_only"),
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
    actual_pnl = float(observed["fixed_notional_pnl_usd"])
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
            observed[f"pnl_without_best_{remove_best}_sessions_usd"] > 0
        ),
        "outperform_sign_flipped": (
            actual_pnl
            > result["sign_flipped"]["fixed_notional_pnl_usd"]
        ),
        "outperform_btc_price_persistence": (
            actual_pnl
            > result["btc_price_persistence"]["fixed_notional_pnl_usd"]
        ),
        "outperform_europe_flow_only": (
            actual_pnl
            > result["europe_flow_only"]["fixed_notional_pnl_usd"]
        ),
    }


def render(payload: dict[str, Any]) -> str:
    development = payload["development"]
    observed = development["observed_bbo"]
    lines = [
        "# BTC Spot Flow Baton to UPRO/SPXU v26",
        "",
        "## Verdict",
        "",
        f"**{payload['status'].replace('_', ' ').upper()}**",
        "",
        "The signal uses BTCUSDT spot taker flow only. No futures, perpetual, "
        "funding, margin, or crypto derivative field is used.",
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
    btc = audit.load_btc()
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    development = evaluate(
        btc,
        arca,
        spy,
        arca_excluded,
        v16.START,
        v16.DEVELOPMENT_END,
        10,
    )
    development["gate"] = gate(development, [2021, 2022, 2023], 10)
    development["gate_passed"] = all(development["gate"].values())
    payload: dict[str, Any] = {
        "status": (
            "development_survivor"
            if development["gate_passed"]
            else "rejected_development_holdout_locked"
        ),
        "development": development,
    }
    if development["gate_passed"]:
        holdout = evaluate(
            btc,
            arca,
            spy,
            arca_excluded,
            v16.HOLDOUT_START,
            v16.HOLDOUT_END,
            5,
        )
        holdout["gate"] = gate(holdout, [2024, 2025], 5)
        consolidated = evaluate(
            btc,
            equs,
            spy,
            equs_excluded,
            v16.HOLDOUT_START,
            v16.HOLDOUT_END,
            5,
        )
        holdout["gate"]["consolidated_execution_positive"] = (
            consolidated["observed_bbo"]["fixed_notional_pnl_usd"] > 0
        )
        holdout["gate_passed"] = all(holdout["gate"].values())
        full = evaluate(
            btc,
            arca,
            spy,
            arca_excluded,
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
                "consolidated_holdout": consolidated,
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
