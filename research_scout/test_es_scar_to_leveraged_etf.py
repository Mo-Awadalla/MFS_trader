"""Transport the frozen ES prior-close scar signal to UPRO/SPXU execution."""

from __future__ import annotations

import json
from datetime import time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import test_es_prior_close_volume_scar_handoff as scar
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16
from research_scout import test_upro_spxu_variance_state as common

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "es_scar_to_leveraged_etf_results_v20.json"
REPORT = ROOT / "research_scout" / "ES_SCAR_TO_LEVERAGED_ETF_REPORT_V20.md"


def states() -> dict[pd.Timestamp, dict[str, Any]]:
    sessions = scar.load_sessions()
    scars = {day: scar.closing_scar(day) for day, _ in sessions}
    result = {}
    for index in range(1, len(sessions)):
        day, bars = sessions[index]
        prior = scars.get(sessions[index - 1][0])
        if prior is None:
            continue
        anchor, instrument = prior
        ids = pd.unique(bars.iloc[:30].instrument_id)
        if len(ids) != 1 or int(ids[0]) != instrument:
            continue
        opening = bars.iloc[:30]
        center = scar.center(opening)
        close = float(opening.iloc[-1].close)
        side = 1 if center > anchor and close > anchor else -1 if center < anchor and close < anchor else 0
        if side:
            result[day] = {
                "side": side,
                "center": center,
                "anchor": anchor,
                "bars": bars,
            }
    return result


def make_rows(
    signal_states: dict[pd.Timestamp, dict[str, Any]],
    bbo: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    cents: float = 0.0,
    delay: int = 0,
) -> list[dict[str, Any]]:
    rows = []
    for day, state in sorted(signal_states.items()):
        if day in excluded or not start <= day <= end:
            continue
        side = state["side"]
        symbol = "UPRO" if side > 0 else "SPXU"
        quotes = bbo.get(day, {}).get(symbol)
        if quotes is None:
            continue
        es = state["bars"]
        stop = state["center"] - side * scar.TICK_SIZE
        entry_index = 31 + delay
        preentry = es.iloc[30:entry_index]
        touched = (preentry.low <= stop).any() if side > 0 else (preentry.high >= stop).any()
        if touched:
            continue
        entry_stamp = v16.stamp(day, time(10, 1), quotes.index.tz) + timedelta(minutes=delay)
        exit_stamp = v16.stamp(day, time(15, 30), quotes.index.tz)
        scan = es.iloc[entry_index:360]
        hits = scan.index[scan.low <= stop] if side > 0 else scan.index[scan.high >= stop]
        if len(hits):
            exit_stamp = hits[0] + timedelta(minutes=1)
        entry = base.quote_at(quotes, entry_stamp, 0)
        exit_quote = base.quote_at(quotes, exit_stamp, 2)
        if entry is None or exit_quote is None:
            continue
        buy = float(entry.ask_px_00) + cents
        sell = float(exit_quote.bid_px_00) - cents
        realized = sell / buy - 1.0
        rows.append({"date": day, "symbol": symbol, "return": realized, "pnl_usd": 100 * realized})
    return rows


def evaluate(signal_states, bbo, spy, excluded, start, end, remove_best):
    args = (signal_states, bbo, excluded, start, end)
    return {
        "observed_bbo": common.summarize(make_rows(*args), remove_best),
        "extra_cent": common.summarize(make_rows(*args, cents=0.01), remove_best),
        "five_minute_delay": common.summarize(make_rows(*args, delay=5), remove_best),
        "spy": common.spy_hurdle(spy, excluded, start, end),
    }


def gate(result, years, remove_best):
    observed = result["observed_bbo"]
    annual = observed.get("year_pnl_usd", {})
    instruments = observed.get("instrument_pnl_usd", {})
    return {
        "frequency": observed["trades_per_week"] >= 2,
        "profit_factor": observed["profit_factor"] > 1,
        "each_year": all(annual.get(str(y), 0) > 0 for y in years),
        "both_actuators": all(instruments.get(s, 0) > 0 for s in ["UPRO", "SPXU"]),
        "beat_spy": observed["ending_cash_usd"] > result["spy"]["ending_cash_usd"],
        "extra_cent": result["extra_cent"]["fixed_notional_pnl_usd"] > 0,
        "delay": result["five_minute_delay"]["fixed_notional_pnl_usd"] > 0,
        "concentration": observed[f"pnl_without_best_{remove_best}_sessions_usd"] > 0,
    }


def main() -> None:
    signal_states = states()
    spy, arca, equs, arca_excluded, equs_excluded = v16.load_old()
    dev = evaluate(signal_states, arca, spy, arca_excluded, v16.START, v16.DEVELOPMENT_END, 10)
    dev["gate"] = gate(dev, [2021, 2022, 2023], 10)
    dev["gate_passed"] = all(dev["gate"].values())
    payload = {"status": "development_survivor" if dev["gate_passed"] else "rejected_development_holdout_locked", "development": dev}
    if dev["gate_passed"]:
        holdout = evaluate(signal_states, arca, spy, arca_excluded, v16.HOLDOUT_START, v16.HOLDOUT_END, 5)
        consolidated = evaluate(signal_states, equs, spy, equs_excluded, v16.HOLDOUT_START, v16.HOLDOUT_END, 5)
        holdout["gate"] = gate(holdout, [2024, 2025], 5)
        holdout["gate"]["consolidated_positive"] = consolidated["observed_bbo"]["fixed_notional_pnl_usd"] > 0
        holdout["gate_passed"] = all(holdout["gate"].values())
        full = evaluate(signal_states, arca, spy, arca_excluded, v16.START, v16.HOLDOUT_END, 10)
        payload.update({"status": "historical_survivor" if holdout["gate_passed"] else "rejected_holdout", "holdout": holdout, "consolidated_holdout": consolidated, "full": full})
    OUTPUT.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    REPORT.write_text("# ES Scar to Leveraged ETF v20\n\n" + json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
