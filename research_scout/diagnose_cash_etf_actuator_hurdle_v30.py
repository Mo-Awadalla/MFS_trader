"""Diagnose the observed UPRO/SPXU actuator hurdle without a trading signal."""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16
from research_scout import test_upro_spxu_variance_state as common

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "cash_etf_actuator_hurdle_v30.json"


def rows(
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    midpoint: bool,
) -> dict[str, list[dict[str, Any]]]:
    output = {"UPRO": [], "SPXU": []}
    for day in sorted(sessions):
        if day in excluded or not start <= day <= end:
            continue
        for symbol in output:
            quotes = sessions[day].get(symbol)
            if quotes is None:
                continue
            entry_stamp = v16.stamp(day, time(10, 31), quotes.index.tz)
            exit_stamp = v16.stamp(day, time(15, 30), quotes.index.tz)
            entry = base.quote_at(quotes, entry_stamp, 0)
            exit_quote = base.quote_at(quotes, exit_stamp, 0)
            if entry is None or exit_quote is None:
                continue
            if midpoint:
                buy = (
                    float(entry.bid_px_00) + float(entry.ask_px_00)
                ) / 2.0
                sell = (
                    float(exit_quote.bid_px_00)
                    + float(exit_quote.ask_px_00)
                ) / 2.0
            else:
                buy = float(entry.ask_px_00)
                sell = float(exit_quote.bid_px_00)
            realized = sell / buy - 1.0
            output[symbol].append(
                {
                    "date": day,
                    "symbol": symbol,
                    "return": realized,
                    "pnl_usd": 100.0 * realized,
                }
            )
    return output


def oracle(
    sleeves: dict[str, list[dict[str, Any]]],
    *,
    cash_allowed: bool,
) -> list[dict[str, Any]]:
    by_day: dict[pd.Timestamp, list[dict[str, Any]]] = {}
    for values in sleeves.values():
        for row in values:
            by_day.setdefault(row["date"], []).append(row)
    selected = []
    for _day, candidates in sorted(by_day.items()):
        best = max(candidates, key=lambda row: row["return"])
        if cash_allowed and float(best["return"]) <= 0:
            continue
        selected.append(best)
    return selected


def period(
    spy: dict[pd.Timestamp, pd.DataFrame],
    sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    bbo = rows(sessions, excluded, start, end, midpoint=False)
    mids = rows(sessions, excluded, start, end, midpoint=True)
    output: dict[str, Any] = {
        "spy": common.spy_hurdle(spy, excluded, start, end),
        "sleeves": {},
    }
    for symbol in ["UPRO", "SPXU"]:
        observed = common.summarize(bbo[symbol], 10)
        midpoint = common.summarize(mids[symbol], 10)
        output["sleeves"][symbol] = {
            "observed_bbo": observed,
            "midpoint": midpoint,
            "fixed_notional_spread_drag_usd": (
                midpoint["fixed_notional_pnl_usd"]
                - observed["fixed_notional_pnl_usd"]
            ),
            "mean_roundtrip_spread_drag_bps": (
                (
                    midpoint["fixed_notional_pnl_usd"]
                    - observed["fixed_notional_pnl_usd"]
                )
                / max(observed["sessions"], 1)
                * 100.0
            ),
        }
    output["perfect_daily_wrapper_choice"] = common.summarize(
        oracle(bbo, cash_allowed=False),
        10,
    )
    output["perfect_daily_wrapper_or_cash"] = common.summarize(
        oracle(bbo, cash_allowed=True),
        10,
    )
    return output


def main() -> None:
    spy, arca, _, excluded, _ = v16.load_old()
    payload = {
        "purpose": (
            "actuator diagnostic only; perfect-choice results are impossible "
            "look-ahead upper bounds, not strategies"
        ),
        "window": "10:31 observed entry to 15:30 observed exit",
        "development": period(
            spy,
            arca,
            excluded,
            v16.START,
            v16.DEVELOPMENT_END,
        ),
        "holdout": period(
            spy,
            arca,
            excluded,
            v16.HOLDOUT_START,
            v16.HOLDOUT_END,
        ),
        "full": period(
            spy,
            arca,
            excluded,
            v16.START,
            v16.HOLDOUT_END,
        ),
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
