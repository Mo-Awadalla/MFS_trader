"""Evaluate preregistered SPY BTC-perpetual fresh-position risk transfer v44."""

from __future__ import annotations

import json
from datetime import time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_spy_btc_perpetual_fresh_position_v44 as audit
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16
from research_scout import test_upro_spxu_variance_state as common

ROOT = Path(__file__).resolve().parents[1]
PREREG = audit.PREREG
ADJUSTED_SPY = ROOT / "data" / "parquet" / "equity" / "alpaca_sip" / "SPY_1d.parquet"
OUTPUT = ROOT / "research_scout" / "spy_btc_perpetual_fresh_position_results_v44.json"
REPORT = ROOT / "research_scout" / "SPY_BTC_PERPETUAL_FRESH_POSITION_REPORT_V44.md"
ENTRY = time(9, 31)
EXIT = time(15, 30)


def build_states(
    perp: pd.DataFrame,
    metrics: pd.DataFrame,
    ordered_days: list[pd.Timestamp],
) -> dict[pd.Timestamp, dict[str, Any]]:
    states: dict[pd.Timestamp, dict[str, Any]] = {}
    for index, day in enumerate(ordered_days):
        if index == 0:
            continue
        state = audit.signal_for(perp, metrics, ordered_days[index - 1], day)
        if state is not None:
            states[day] = state
    return states


def variant_directions(
    states: dict[pd.Timestamp, dict[str, Any]],
    ordered_days: list[pd.Timestamp],
    variant: str,
) -> dict[pd.Timestamp, int]:
    result: dict[pd.Timestamp, int] = {}
    for index, day in enumerate(ordered_days):
        state = states.get(day)
        if state is None:
            result[day] = 0
            continue
        price_direction = int(state["price_direction"])
        oi_change = float(state["oi_change"])
        actual = int(state["direction"])
        if variant == "actual":
            direction = actual
        elif variant == "price_only":
            direction = price_direction
        elif variant == "oi_decreasing":
            direction = price_direction if oi_change < 0 else 0
        elif variant == "shifted_expansion":
            prior_state = states.get(ordered_days[index - 1]) if index else None
            prior_expanded = prior_state is not None and float(prior_state["oi_change"]) > 0
            direction = price_direction if prior_expanded else 0
        elif variant == "flipped":
            direction = -actual
        else:
            raise ValueError(f"unknown variant: {variant}")
        result[day] = direction
    return result


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
        quotes = sessions.get(day, {}).get(symbol)
        if quotes is None:
            continue
        entry_stamp = v16.stamp(day, ENTRY, quotes.index.tz) + timedelta(
            minutes=delay_minutes
        )
        exit_stamp = v16.stamp(day, EXIT, quotes.index.tz)
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


def adjusted_spy_hurdle(start: pd.Timestamp, end: pd.Timestamp) -> dict[str, Any]:
    frame = pd.read_parquet(ADJUSTED_SPY).copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        if "timestamp" not in frame:
            raise ValueError("adjusted SPY daily data has no datetime index or timestamp column")
        frame["timestamp"] = pd.to_datetime(frame.timestamp, utc=True)
        frame = frame.set_index("timestamp")
    elif frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    frame = frame.sort_index()
    dates = frame.index.tz_convert("America/New_York").tz_localize(None).normalize()
    scoped = frame.loc[(dates >= start) & (dates <= end)].copy()
    if scoped.empty:
        raise ValueError("no adjusted SPY daily bars in requested partition")
    first_open = float(scoped.iloc[0].open)
    last_close = float(scoped.iloc[-1].close)
    if min(first_open, last_close) <= 0:
        raise ValueError("invalid adjusted SPY prices")
    ending = 100.0 * last_close / first_open
    return {
        "first_timestamp": str(scoped.index[0]),
        "last_timestamp": str(scoped.index[-1]),
        "ending_cash_usd": ending,
        "return_pct": ending - 100.0,
        "split_and_dividend_adjusted": True,
        "source": str(ADJUSTED_SPY.relative_to(ROOT)).replace("\\", "/"),
    }


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
    actual_rows = make_rows(sessions, excluded, actual, start, end)
    result = {
        "observed_bbo": common.summarize(actual_rows, remove_best),
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
        "controls": {
            variant: common.summarize(
                make_rows(sessions, excluded, directions[variant], start, end),
                remove_best,
            )
            for variant in ["price_only", "oi_decreasing", "shifted_expansion", "flipped"]
        },
        "spy_price_only_hurdle": common.spy_hurdle(spy, excluded, start, end),
        "spy_total_return_hurdle": adjusted_spy_hurdle(start, end),
    }
    return result


def gate(
    result: dict[str, Any],
    years: list[int],
    remove_best: int,
) -> dict[str, bool]:
    observed = result["observed_bbo"]
    annual = observed.get("year_pnl_usd", {})
    sleeves = observed.get("instrument_pnl_usd", {})
    controls = result["controls"]
    deleted = f"pnl_without_best_{remove_best}_sessions_usd"
    price_only = controls["price_only"]
    return {
        "minimum_two_trades_per_week": observed["trades_per_week"] >= 2.0,
        "profit_factor_strictly_above_one": observed["profit_factor"] > 1.0,
        "each_year_positive": all(annual.get(str(year), 0.0) > 0 for year in years),
        "both_actuators_positive": all(
            sleeves.get(symbol, 0.0) > 0 for symbol in ["UPRO", "SPXU"]
        ),
        "ending_cash_above_spy_price_only": (
            observed["ending_cash_usd"]
            > result["spy_price_only_hurdle"]["ending_cash_usd"]
        ),
        "ending_cash_above_spy_total_return": (
            observed["ending_cash_usd"]
            > result["spy_total_return_hurdle"]["ending_cash_usd"]
        ),
        "positive_after_extra_cent_each_fill": (
            result["extra_cent_each_fill"]["fixed_notional_pnl_usd"] > 0
        ),
        "positive_after_five_minute_entry_delay": (
            result["five_minute_entry_delay"]["fixed_notional_pnl_usd"] > 0
        ),
        f"positive_after_removing_best_{remove_best}": observed[deleted] > 0,
        "mean_trade_above_btc_price_only_control": (
            observed["mean_session_pnl_usd"] > price_only["mean_session_pnl_usd"]
        ),
        "winner_deleted_pnl_above_btc_price_only_control": (
            observed[deleted] > price_only[deleted]
        ),
        "pnl_above_oi_decreasing_control": (
            observed["fixed_notional_pnl_usd"]
            > controls["oi_decreasing"]["fixed_notional_pnl_usd"]
        ),
        "pnl_above_shifted_expansion_control": (
            observed["fixed_notional_pnl_usd"]
            > controls["shifted_expansion"]["fixed_notional_pnl_usd"]
        ),
        "pnl_above_sign_flipped_control": (
            observed["fixed_notional_pnl_usd"]
            > controls["flipped"]["fixed_notional_pnl_usd"]
        ),
    }


def render(payload: dict[str, Any]) -> str:
    development = payload["development"]
    observed = development["observed_bbo"]
    controls = development["controls"]
    lines = [
        "# SPY BTC-Perpetual Fresh-Position Risk Transfer v44",
        "",
        "## Verdict",
        "",
        f"**{payload['status'].replace('_', ' ').upper()}**",
        "",
        "V44 uses the sign of the 16:00-to-09:00 BTCUSDT perpetual move only when BTC-denominated Binance open interest expands. It enters UPRO or SPXU at the observed 09:31 ask and exits at the observed 15:30 bid.",
        "",
        "## Development: 2021–2023",
        "",
        "| Trades/week | Fixed-$100 P&L | Ending cash | PF | SPY price-only | SPY total-return |",
        "|---:|---:|---:|---:|---:|---:|",
        (
            f"| {observed['trades_per_week']:.3f} | "
            f"${observed['fixed_notional_pnl_usd']:.2f} | "
            f"${observed['ending_cash_usd']:.2f} | "
            f"{observed['profit_factor']:.3f} | "
            f"${development['spy_price_only_hurdle']['ending_cash_usd']:.2f} | "
            f"${development['spy_total_return_hurdle']['ending_cash_usd']:.2f} |"
        ),
        "",
        "## Identification and stress results",
        "",
        f"- Extra cent at each fill: ${development['extra_cent_each_fill']['fixed_notional_pnl_usd']:.2f}.",
        f"- Five-minute entry delay: ${development['five_minute_entry_delay']['fixed_notional_pnl_usd']:.2f}.",
        f"- Delete ten best sessions: ${observed['pnl_without_best_10_sessions_usd']:.2f}.",
        f"- BTC price-only control: ${controls['price_only']['fixed_notional_pnl_usd']:.2f}.",
        f"- OI-decreasing control: ${controls['oi_decreasing']['fixed_notional_pnl_usd']:.2f}.",
        f"- Shifted-expansion control: ${controls['shifted_expansion']['fixed_notional_pnl_usd']:.2f}.",
        f"- Sign-flipped control: ${controls['flipped']['fixed_notional_pnl_usd']:.2f}.",
        f"- Independent EQUS development-overlap P&L: ${payload['independent_development_overlap']['observed_bbo']['fixed_notional_pnl_usd']:.2f}.",
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
                "## Secondary holdout: 2024–2025",
                "",
                "| Trades/week | Fixed-$100 P&L | Ending cash | PF | SPY total-return |",
                "|---:|---:|---:|---:|---:|",
                (
                    f"| {h['trades_per_week']:.3f} | "
                    f"${h['fixed_notional_pnl_usd']:.2f} | "
                    f"${h['ending_cash_usd']:.2f} | "
                    f"{h['profit_factor']:.3f} | "
                    f"${holdout['spy_total_return_hurdle']['ending_cash_usd']:.2f} |"
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
            "No failed direction, threshold, clock, sleeve, or control was selected as a repair. Historical results are research evidence, not authorization for live capital.",
            "",
            "Preimplementation critique: `research_scout/SPY_BTC_PERPETUAL_FRESH_POSITION_RISK_TRANSFER_PREIMPLEMENTATION_CRITIQUE_V44.md`.",
            "",
            "Machine result: `research_scout/spy_btc_perpetual_fresh_position_results_v44.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    if not PREREG.exists():
        raise FileNotFoundError("V44 preregistration is required before return test")
    feasibility = json.loads(audit.OUTPUT.read_text(encoding="utf-8"))
    if not feasibility.get("feasibility_passed", False):
        raise RuntimeError("V44 returns-blind feasibility did not pass")

    perp, metrics = audit.load_btc()
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    ordered_days = sorted(
        day
        for day in spy
        if v16.START <= day <= v16.HOLDOUT_END and day not in arca_excluded
    )
    states = build_states(perp, metrics, ordered_days)
    directions = {
        variant: variant_directions(states, ordered_days, variant)
        for variant in ["actual", "price_only", "oi_decreasing", "shifted_expansion", "flipped"]
    }

    development = evaluate(
        arca,
        spy,
        arca_excluded,
        directions,
        v16.START,
        v16.DEVELOPMENT_END,
        10,
    )
    development["gate"] = gate(development, [2021, 2022, 2023], 10)
    independent_development = evaluate(
        equs,
        spy,
        equs_excluded,
        directions,
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
        "specification": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
        "returns_blind_audit": feasibility,
        "development": development,
        "independent_development_overlap": independent_development,
        "holdout_return_status": (
            "unlocked" if development["gate_passed"] else "not_calculated"
        ),
    }
    if development["gate_passed"]:
        holdout = evaluate(
            arca,
            spy,
            arca_excluded,
            directions,
            v16.HOLDOUT_START,
            v16.HOLDOUT_END,
            5,
        )
        holdout["gate"] = gate(holdout, [2024, 2025], 5)
        independent_holdout = evaluate(
            equs,
            spy,
            equs_excluded,
            directions,
            v16.HOLDOUT_START,
            v16.HOLDOUT_END,
            5,
        )
        holdout["gate"]["independent_feed_pnl_positive"] = (
            independent_holdout["observed_bbo"]["fixed_notional_pnl_usd"] > 0
        )
        holdout["gate_passed"] = all(holdout["gate"].values())
        payload.update(
            {
                "status": (
                    "historical_survivor_requires_forward_validation"
                    if holdout["gate_passed"]
                    else "rejected_holdout"
                ),
                "holdout": holdout,
                "independent_holdout": independent_holdout,
                "holdout_return_status": "calculated_after_complete_development_pass",
            }
        )
    OUTPUT.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    REPORT.write_text(render(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
