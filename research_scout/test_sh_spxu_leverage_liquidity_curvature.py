"""Evaluate preregistered SH/SPXU leverage-liquidity curvature v33."""

from __future__ import annotations

import json
from datetime import time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_sh_spxu_leverage_liquidity_curvature as audit
from research_scout import test_upro_sh_sensor_actuator as shdata
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16
from research_scout import test_upro_spxu_variance_state as common

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research_scout"
    / "sh_spxu_leverage_liquidity_curvature_results_v33.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "SH_SPXU_LEVERAGE_LIQUIDITY_CURVATURE_REPORT_V33.md"
)


def direction_for(state: dict[str, Any], variant: str) -> int:
    actual = int(state["direction"])
    if variant == "actual":
        return actual
    if variant == "sign_flipped":
        return -actual
    if variant == "raw_sh_spread_change":
        first = float(state["sh_first_spread"])
        second = float(state["sh_second_spread"])
        return 1 if second < first else -1 if second > first else 0
    if variant == "raw_spxu_spread_change":
        first = float(state["spxu_first_spread"])
        second = float(state["spxu_second_spread"])
        return 1 if second < first else -1 if second > first else 0
    raise ValueError(f"unknown variant: {variant}")


def make_rows(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    sh_sessions: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    variant: str = "actual",
    *,
    adverse_cents: float = 0.0,
    delay_minutes: int = 0,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day in sorted(set(sessions).intersection(sh_sessions)):
        if day in excluded or not start <= day <= end:
            continue
        state = audit.session_signal(
            sh_sessions.get(day),
            sessions[day].get("SPXU"),
        )
        if state is None:
            continue
        direction = direction_for(state, variant)
        if direction == 0:
            continue
        symbol = "UPRO" if direction > 0 else "SPXU"
        quotes = sessions[day].get(symbol)
        if quotes is None:
            continue
        entry_stamp = v16.stamp(day, time(10, 16), quotes.index.tz) + timedelta(
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
    sh_sessions: dict[pd.Timestamp, pd.DataFrame],
    spy: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    remove_best: int,
) -> dict[str, Any]:
    args = (sessions, sh_sessions, excluded, start, end)
    return {
        "observed_bbo": common.summarize(
            make_rows(*args),
            remove_best,
        ),
        "extra_cent_each_fill": common.summarize(
            make_rows(*args, adverse_cents=0.01),
            remove_best,
        ),
        "five_minute_entry_delay": common.summarize(
            make_rows(*args, delay_minutes=5),
            remove_best,
        ),
        "sign_flipped": common.summarize(
            make_rows(*args, variant="sign_flipped"),
            remove_best,
        ),
        "raw_sh_spread_change": common.summarize(
            make_rows(*args, variant="raw_sh_spread_change"),
            remove_best,
        ),
        "raw_spxu_spread_change": common.summarize(
            make_rows(*args, variant="raw_spxu_spread_change"),
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
            actual_pnl > result["sign_flipped"]["fixed_notional_pnl_usd"]
        ),
        "outperform_raw_sh_spread_change": (
            actual_pnl
            > result["raw_sh_spread_change"]["fixed_notional_pnl_usd"]
        ),
        "outperform_raw_spxu_spread_change": (
            actual_pnl
            > result["raw_spxu_spread_change"]["fixed_notional_pnl_usd"]
        ),
    }


def render(payload: dict[str, Any]) -> str:
    development = payload["development"]
    observed = development["observed_bbo"]
    lines = [
        "# SH/SPXU Inverse-Leverage Liquidity Curvature v33",
        "",
        "## Verdict",
        "",
        f"**{payload['status'].replace('_', ' ').upper()}**",
        "",
        "The signal and actuator use cash ETFs only. No futures, margin, short "
        "sale, or passive-fill assumption is used.",
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
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    arca_sh = shdata.sh_sessions(shdata.SH_ARCA)
    equs_sh = shdata.sh_sessions(shdata.SH_EQUS)
    development = evaluate(
        arca,
        arca_sh,
        spy,
        arca_excluded,
        v16.START,
        v16.DEVELOPMENT_END,
        10,
    )
    development["gate"] = gate(development, [2021, 2022, 2023], 10)
    independent_development = evaluate(
        equs,
        equs_sh,
        spy,
        equs_excluded,
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
            arca_sh,
            spy,
            arca_excluded,
            v16.HOLDOUT_START,
            v16.HOLDOUT_END,
            5,
        )
        holdout["gate"] = gate(holdout, [2024, 2025], 5)
        independent_holdout = evaluate(
            equs,
            equs_sh,
            spy,
            equs_excluded,
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
            arca_sh,
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
