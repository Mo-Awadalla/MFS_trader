"""Evaluate preregistered persistent premarket wrapper premium."""

from __future__ import annotations

import json
from datetime import time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from research_scout import audit_upro_spxu_premarket_wrapper_premium as audit
from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_cross_inverse_aggressor_relay as v16
from research_scout import test_upro_spxu_variance_state as common

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "research_scout" / "upro_spxu_premarket_wrapper_premium_prereg_v19.json"
OUTPUT = ROOT / "research_scout" / "upro_spxu_premarket_wrapper_premium_results_v19.json"
REPORT = ROOT / "research_scout" / "UPRO_SPXU_PREMARKET_WRAPPER_PREMIUM_REPORT_V19.md"
ENTRY = time(9, 31)
EXIT = time(11, 30)


def directions(frame: pd.DataFrame) -> dict[pd.Timestamp, int]:
    return {row.date: int(row.direction) for row in frame.itertuples()}


def trade(
    day: pd.Timestamp,
    direction: int,
    pair: dict[str, pd.DataFrame],
    *,
    adverse_cents: float = 0.0,
    delay: int = 0,
) -> dict[str, Any] | None:
    symbol = "UPRO" if direction > 0 else "SPXU"
    quotes = pair.get(symbol)
    if quotes is None:
        return None
    entry_stamp = v16.stamp(day, ENTRY, quotes.index.tz) + timedelta(minutes=delay)
    exit_stamp = v16.stamp(day, EXIT, quotes.index.tz)
    entry = base.quote_at(quotes, entry_stamp, 0)
    exit_quote = base.quote_at(quotes, exit_stamp, 0)
    if entry is None or exit_quote is None:
        return None
    buy = float(entry.ask_px_00) + adverse_cents
    sell = float(exit_quote.bid_px_00) - adverse_cents
    if min(buy, sell) <= 0:
        return None
    realized = sell / buy - 1.0
    return {
        "date": day,
        "symbol": symbol,
        "return": realized,
        "pnl_usd": 100.0 * realized,
    }


def rows(
    signals: dict[pd.Timestamp, int],
    pair: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    flipped: bool = False,
    adverse_cents: float = 0.0,
    delay: int = 0,
) -> list[dict[str, Any]]:
    result = []
    for day, direction in sorted(signals.items()):
        if direction == 0 or day in excluded or not start <= day <= end:
            continue
        item = trade(
            day,
            -direction if flipped else direction,
            pair.get(day, {}),
            adverse_cents=adverse_cents,
            delay=delay,
        )
        if item is not None:
            result.append(item)
    return result


def evaluate(
    signals: dict[pd.Timestamp, int],
    pair: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    spy: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
    remove_best: int,
) -> dict[str, Any]:
    arguments = (signals, pair, excluded, start, end)
    return {
        "observed_bbo": common.summarize(rows(*arguments), remove_best),
        "one_extra_cent_each_fill": common.summarize(
            rows(*arguments, adverse_cents=0.01), remove_best
        ),
        "five_minute_entry_delay": common.summarize(
            rows(*arguments, delay=5), remove_best
        ),
        "sign_flipped_placebo": common.summarize(
            rows(*arguments, flipped=True), remove_best
        ),
        "spy_price_only_hurdle": common.spy_hurdle(
            spy, excluded, start, end
        ),
    }


def development_gate(result: dict[str, Any]) -> dict[str, bool]:
    observed = result["observed_bbo"]
    years = observed.get("year_pnl_usd", {})
    instruments = observed.get("instrument_pnl_usd", {})
    return {
        "minimum_two_trades_per_week": observed["trades_per_week"] >= 2,
        "profit_factor_above_one": observed["profit_factor"] > 1,
        "each_year_positive": all(years.get(str(y), 0) > 0 for y in [2021, 2022, 2023]),
        "both_wrappers_positive": all(instruments.get(s, 0) > 0 for s in ["UPRO", "SPXU"]),
        "ending_cash_above_spy": observed["ending_cash_usd"] > result["spy_price_only_hurdle"]["ending_cash_usd"],
        "extra_cent_positive": result["one_extra_cent_each_fill"]["fixed_notional_pnl_usd"] > 0,
        "five_minute_delay_positive": result["five_minute_entry_delay"]["fixed_notional_pnl_usd"] > 0,
        "without_ten_best_positive": observed["pnl_without_best_10_sessions_usd"] > 0,
        "outperform_flipped": observed["fixed_notional_pnl_usd"] > result["sign_flipped_placebo"]["fixed_notional_pnl_usd"]
    }


def holdout_gate(result: dict[str, Any], consolidated: dict[str, Any]) -> dict[str, bool]:
    observed = result["observed_bbo"]
    years = observed.get("year_pnl_usd", {})
    instruments = observed.get("instrument_pnl_usd", {})
    return {
        "each_year_positive": all(years.get(str(y), 0) > 0 for y in [2024, 2025]),
        "both_wrappers_positive": all(instruments.get(s, 0) > 0 for s in ["UPRO", "SPXU"]),
        "ending_cash_above_spy": observed["ending_cash_usd"] > result["spy_price_only_hurdle"]["ending_cash_usd"],
        "extra_cent_positive": result["one_extra_cent_each_fill"]["fixed_notional_pnl_usd"] > 0,
        "without_five_best_positive": observed["pnl_without_best_5_sessions_usd"] > 0,
        "consolidated_positive": consolidated["observed_bbo"]["fixed_notional_pnl_usd"] > 0
    }


def main() -> None:
    if not PREREG.exists():
        raise FileNotFoundError("Missing preregistration")
    spy, arca_pair, equs_pair, arca_excluded, equs_excluded = v16.load_old()
    arca_signal = directions(audit.signal_frame(spy, arca_pair, arca_excluded))
    dev = evaluate(arca_signal, arca_pair, spy, arca_excluded, v16.START, v16.DEVELOPMENT_END, 10)
    dev["gate"] = development_gate(dev)
    dev["gate_passed"] = all(dev["gate"].values())
    payload: dict[str, Any] = {
        "specification": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
        "status": "development_survivor" if dev["gate_passed"] else "rejected_in_development_holdout_locked",
        "development": dev,
        "holdout_return_status": "unlocked" if dev["gate_passed"] else "not_calculated"
    }
    if dev["gate_passed"]:
        holdout = evaluate(arca_signal, arca_pair, spy, arca_excluded, v16.HOLDOUT_START, v16.HOLDOUT_END, 5)
        equs_spy = audit.spy_sessions(audit.EQUS_SPY)
        equs_signal = directions(audit.signal_frame(equs_spy, equs_pair, equs_excluded))
        consolidated = evaluate(equs_signal, equs_pair, equs_spy, equs_excluded, v16.HOLDOUT_START, v16.HOLDOUT_END, 5)
        holdout["gate"] = holdout_gate(holdout, consolidated)
        holdout["gate_passed"] = all(holdout["gate"].values())
        full = evaluate(arca_signal, arca_pair, spy, arca_excluded, v16.START, v16.HOLDOUT_END, 10)
        payload.update({
            "status": "historical_survivor_requires_forward_validation" if holdout["gate_passed"] else "rejected_on_secondary_holdout",
            "holdout": holdout,
            "consolidated_holdout": consolidated,
            "full_2021_2025": full
        })
    OUTPUT.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    observed = dev["observed_bbo"]
    failures = [k for k, passed in dev["gate"].items() if not passed]
    report = (
        "# Persistent Premarket Wrapper Premium v19\n\n"
        "## Verdict\n\n"
        + ("**Development survivor.**" if dev["gate_passed"] else "**Rejected in development; holdout locked.**")
        + f"\n\nDevelopment: {observed['trades_per_week']:.2f} trades/week, "
        f"$100 to ${observed['ending_cash_usd']:.2f}, fixed P&L "
        f"${observed['fixed_notional_pnl_usd']:.2f}, PF {observed['profit_factor']:.3f}; "
        f"SPY ${dev['spy_price_only_hurdle']['ending_cash_usd']:.2f}.\n\n"
        + "Failures: " + (", ".join(failures) or "none") + ".\n"
    )
    REPORT.write_text(report, encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
