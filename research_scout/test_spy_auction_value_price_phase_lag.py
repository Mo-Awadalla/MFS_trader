"""Evaluate preregistered SPY Auction Value/Price Phase-Lag v29."""

from __future__ import annotations

import json
from datetime import time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_spy_auction_value_price_phase_lag as audit
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16
from research_scout import test_upro_spxu_variance_state as common

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research_scout"
    / "spy_auction_value_price_phase_lag_results_v29.json"
)
REPORT = (
    ROOT
    / "research_scout"
    / "SPY_AUCTION_VALUE_PRICE_PHASE_LAG_REPORT_V29.md"
)


def direction(bars: pd.DataFrame, variant: str) -> int:
    first = bars.between_time("09:30", "09:59")
    second = bars.between_time("10:00", "10:29")
    if len(first) != 30 or len(second) != 30:
        return 0
    c1, p1 = audit.block_state(first)
    c2, p2 = audit.block_state(second)
    if variant == "actual":
        value = (c2 - p2) - (c1 - p1)
    elif variant == "flipped":
        value = -((c2 - p2) - (c1 - p1))
    elif variant == "price_momentum":
        value = p2 - float(first.iloc[0].open)
    elif variant == "center_migration":
        value = c2 - c1
    else:
        raise ValueError(f"unknown variant: {variant}")
    return int(value > 0) - int(value < 0)


def make_rows(
    spy: dict[pd.Timestamp, pd.DataFrame],
    pair: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    variant: str = "actual",
    *,
    adverse_cents: float = 0.0,
    delay_minutes: int = 0,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day, bars in sorted(spy.items()):
        if day in excluded or not start <= day <= end:
            continue
        side = direction(bars, variant)
        if side == 0:
            continue
        symbol = "UPRO" if side > 0 else "SPXU"
        quotes = pair.get(day, {}).get(symbol)
        if quotes is None:
            continue
        entry_stamp = v16.stamp(day, time(10, 31), quotes.index.tz) + timedelta(
            minutes=delay_minutes
        )
        exit_stamp = v16.stamp(day, time(15, 30), quotes.index.tz)
        entry = base.quote_at(quotes, entry_stamp, 0)
        exit_quote = base.quote_at(quotes, exit_stamp, 0)
        if entry is None or exit_quote is None:
            continue
        buy = float(entry.ask_px_00) + adverse_cents
        sell = float(exit_quote.bid_px_00) - adverse_cents
        realized = sell / buy - 1.0
        rows.append(
            {
                "date": day,
                "symbol": symbol,
                "return": realized,
                "pnl_usd": 100.0 * realized,
            }
        )
    return rows


def evaluate(
    spy: dict[pd.Timestamp, pd.DataFrame],
    pair: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    remove_best: int,
) -> dict[str, Any]:
    args = (spy, pair, excluded, start, end)
    return {
        "observed_bbo": common.summarize(make_rows(*args), remove_best),
        "extra_cent": common.summarize(
            make_rows(*args, adverse_cents=0.01),
            remove_best,
        ),
        "five_minute_delay": common.summarize(
            make_rows(*args, delay_minutes=5),
            remove_best,
        ),
        "sign_flipped": common.summarize(
            make_rows(*args, variant="flipped"),
            remove_best,
        ),
        "price_momentum": common.summarize(
            make_rows(*args, variant="price_momentum"),
            remove_best,
        ),
        "center_migration": common.summarize(
            make_rows(*args, variant="center_migration"),
            remove_best,
        ),
        "spy": common.spy_hurdle(spy, excluded, start, end),
    }


def gates(result: dict[str, Any], years: list[int], remove_best: int) -> dict[str, bool]:
    observed = result["observed_bbo"]
    pnl = float(observed["fixed_notional_pnl_usd"])
    annual = observed.get("year_pnl_usd", {})
    sleeves = observed.get("instrument_pnl_usd", {})
    return {
        "minimum_four_trades_per_week": observed["trades_per_week"] >= 4.0,
        "profit_factor_above_one": observed["profit_factor"] > 1.0,
        "each_year_positive": all(annual.get(str(y), 0.0) > 0 for y in years),
        "both_actuators_positive": all(
            sleeves.get(symbol, 0.0) > 0 for symbol in ["UPRO", "SPXU"]
        ),
        "ending_cash_above_spy": observed["ending_cash_usd"] > result["spy"]["ending_cash_usd"],
        "extra_cent_positive": result["extra_cent"]["fixed_notional_pnl_usd"] > 0,
        "five_minute_delay_positive": result["five_minute_delay"]["fixed_notional_pnl_usd"] > 0,
        f"remove_best_{remove_best}_positive": observed[
            f"pnl_without_best_{remove_best}_sessions_usd"
        ]
        > 0,
        "outperform_sign_flipped": pnl > result["sign_flipped"]["fixed_notional_pnl_usd"],
        "outperform_price_momentum": pnl > result["price_momentum"]["fixed_notional_pnl_usd"],
        "outperform_center_migration": pnl > result["center_migration"]["fixed_notional_pnl_usd"],
    }


def main() -> None:
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    dev = evaluate(
        spy, arca, arca_excluded, v16.START, v16.DEVELOPMENT_END, 10
    )
    dev["gate"] = gates(dev, [2021, 2022, 2023], 10)
    dev["gate_passed"] = all(dev["gate"].values())
    payload: dict[str, Any] = {
        "status": (
            "development_survivor"
            if dev["gate_passed"]
            else "rejected_development_holdout_locked"
        ),
        "development": dev,
    }
    if dev["gate_passed"]:
        holdout = evaluate(
            spy, arca, arca_excluded, v16.HOLDOUT_START, v16.HOLDOUT_END, 5
        )
        holdout["gate"] = gates(holdout, [2024, 2025], 5)
        consolidated = evaluate(
            spy, equs, equs_excluded, v16.HOLDOUT_START, v16.HOLDOUT_END, 5
        )
        holdout["gate"]["consolidated_execution_positive"] = (
            consolidated["observed_bbo"]["fixed_notional_pnl_usd"] > 0
        )
        holdout["gate_passed"] = all(holdout["gate"].values())
        payload.update(
            {
                "status": (
                    "historical_survivor"
                    if holdout["gate_passed"]
                    else "rejected_holdout"
                ),
                "holdout": holdout,
                "consolidated_holdout": consolidated,
                "full": evaluate(
                    spy,
                    arca,
                    arca_excluded,
                    v16.START,
                    v16.HOLDOUT_END,
                    10,
                ),
            }
        )
    OUTPUT.write_text(
        json.dumps(payload, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    REPORT.write_text(
        "# SPY Auction Value/Price Phase-Lag v29\n\n"
        + json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
