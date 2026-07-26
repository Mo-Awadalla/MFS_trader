"""Test preregistered UPRO/SPXU inventory-state hypotheses."""

from __future__ import annotations

import argparse
import json
import math
from datetime import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_pair_geometry as geo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "research_scout" / "upro_spxu_inventory_state_results_v4.json"
HYPOTHESES = [
    "paired_depth_reciprocity",
    "depth_migration_torque",
    "quote_size_memory",
    "depth_impedance_relief",
    "first_synchronization_pulse",
    "event_density_acceleration",
    "volume_share_acceleration",
]
BBO_HYPOTHESES = set(HYPOTHESES[:4])


def bbo_window(
    day: pd.Timestamp,
    quotes: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame] | None:
    windows = geo.valid_bbo_windows(day, quotes)
    if windows is None:
        return None
    for frame in windows.values():
        if (
            (frame.bid_sz_00.astype(float) <= 0).any()
            or (frame.ask_sz_00.astype(float) <= 0).any()
        ):
            return None
    return windows


def imbalance(frame: pd.DataFrame) -> np.ndarray:
    bid = frame.bid_sz_00.astype(float).to_numpy()
    ask = frame.ask_sz_00.astype(float).to_numpy()
    return (bid - ask) / (bid + ask)


def paired_depth_reciprocity(windows: dict[str, pd.DataFrame]) -> float:
    u = imbalance(windows["UPRO"])
    s = imbalance(windows["SPXU"])
    bullish = ((u > 0) & (s < 0)).sum()
    bearish = ((s > 0) & (u < 0)).sum()
    return float(bullish - bearish)


def depth_migration(windows: dict[str, pd.DataFrame]) -> float:
    migrations: dict[str, float] = {}
    for symbol in ["UPRO", "SPXU"]:
        values = imbalance(windows[symbol])
        migrations[symbol] = float(np.median(values[60:90]) - np.median(values[:30]))
    return migrations["UPRO"] - migrations["SPXU"]


def quote_memory(windows: dict[str, pd.DataFrame]) -> float:
    memories: dict[str, float] = {}
    for symbol in ["UPRO", "SPXU"]:
        values = imbalance(windows[symbol])
        signs = np.sign(values)
        flicker = float((signs[1:] != signs[:-1]).mean())
        memories[symbol] = float(np.median(values) * (1.0 - flicker))
    return memories["UPRO"] - memories["SPXU"]


def impedance(frame: pd.DataFrame) -> np.ndarray:
    bid_price = frame.bid_px_00.astype(float).to_numpy()
    ask_price = frame.ask_px_00.astype(float).to_numpy()
    bid_notional = bid_price * frame.bid_sz_00.astype(float).to_numpy()
    ask_notional = ask_price * frame.ask_sz_00.astype(float).to_numpy()
    midpoint = (bid_price + ask_price) / 2.0
    spread = (ask_price - bid_price) / midpoint
    return spread / np.sqrt(bid_notional * ask_notional)


def depth_impedance(windows: dict[str, pd.DataFrame]) -> float:
    ratios: dict[str, float] = {}
    for symbol in ["UPRO", "SPXU"]:
        values = impedance(windows[symbol])
        early = float(np.median(values[:30]))
        late = float(np.median(values[60:90]))
        if early <= 0:
            return math.nan
        ratios[symbol] = late / early
    return ratios["SPXU"] - ratios["UPRO"]


BBO_SCORERS = {
    "paired_depth_reciprocity": paired_depth_reciprocity,
    "depth_migration_torque": depth_migration,
    "quote_size_memory": quote_memory,
    "depth_impedance_relief": depth_impedance,
}


def observed_bar_window(bars: pd.DataFrame) -> pd.DataFrame:
    return base.between(bars, "09:30", "10:59")


def first_sync_score(
    day: pd.Timestamp,
    pair_bars: dict[str, pd.DataFrame],
) -> float:
    blocks = [time(9, 30), time(10, 0), time(10, 30)]
    for start in blocks:
        windows: dict[str, pd.DataFrame] = {}
        for symbol in ["UPRO", "SPXU"]:
            window = geo.exact_window(pair_bars[symbol], day, start, 30)
            if window is None:
                break
            windows[symbol] = window
        if len(windows) != 2:
            continue
        centroids: dict[str, float] = {}
        clock = np.arange(30, dtype=float)
        for symbol in ["UPRO", "SPXU"]:
            volume = windows[symbol].volume.astype(float).to_numpy()
            if float(volume.sum()) <= 0:
                return math.nan
            centroids[symbol] = float(np.dot(clock, volume) / volume.sum())
        return centroids["UPRO"] - centroids["SPXU"]
    return math.nan


def event_density_score(pair_bars: dict[str, pd.DataFrame]) -> float:
    accelerations: dict[str, int] = {}
    for symbol in ["UPRO", "SPXU"]:
        window = observed_bar_window(pair_bars[symbol])
        early = len(base.between(window, "09:30", "10:14"))
        late = len(base.between(window, "10:15", "10:59"))
        accelerations[symbol] = late - early
    return float(accelerations["UPRO"] - accelerations["SPXU"])


def volume_share_score(pair_bars: dict[str, pd.DataFrame]) -> float:
    shares: dict[str, float] = {}
    for symbol in ["UPRO", "SPXU"]:
        window = observed_bar_window(pair_bars[symbol])
        total = float(window.volume.astype(float).sum())
        if total <= 0:
            return math.nan
        late = float(
            base.between(window, "10:15", "10:59").volume.astype(float).sum()
        )
        shares[symbol] = late / total
    return shares["UPRO"] - shares["SPXU"]


def make_signal(
    hypothesis: str,
    day: pd.Timestamp,
    pair_bars: dict[str, pd.DataFrame],
    quotes: dict[str, pd.DataFrame],
) -> dict[str, Any] | None:
    if not {"UPRO", "SPXU"}.issubset(pair_bars):
        return None
    if hypothesis in BBO_HYPOTHESES:
        windows = bbo_window(day, quotes)
        if windows is None:
            return None
        score = BBO_SCORERS[hypothesis](windows)
    elif hypothesis == "first_synchronization_pulse":
        score = first_sync_score(day, pair_bars)
    elif hypothesis == "event_density_acceleration":
        score = event_density_score(pair_bars)
    else:
        score = volume_share_score(pair_bars)
    if not math.isfinite(score):
        return None
    signal_direction = int(score > 0) - int(score < 0)
    if signal_direction == 0:
        return None
    return {
        "hypothesis": hypothesis,
        "date": day,
        "direction": signal_direction,
        "score": score,
    }


def run_period(
    hypothesis: str,
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    pair_sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    feed_sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    years: range,
    additional_delay_minutes: int = 0,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for day in sorted(spy_sessions):
        if day.year not in years or day in excluded:
            continue
        pair_bars = pair_sessions.get(day)
        quotes = feed_sessions.get(day)
        if pair_bars is None or quotes is None:
            continue
        signal = make_signal(hypothesis, day, pair_bars, quotes)
        if signal is None:
            continue
        symbol = "UPRO" if signal["direction"] == 1 else "SPXU"
        if symbol not in quotes:
            continue
        trade = geo.simulate(
            signal,
            spy_sessions[day],
            quotes[symbol],
            additional_delay_minutes,
        )
        if trade is not None:
            records.append(trade)
    return pd.DataFrame(records)


def spy_price_hurdle(
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
    years: range,
) -> dict[str, Any]:
    eligible = [
        day for day in sorted(spy_sessions) if day.year in years and day not in excluded
    ]
    start_price = None
    start_day = None
    for day in eligible:
        row = base.exact_row(
            spy_sessions[day],
            base.clock_timestamp(day, time(9, 30), spy_sessions[day].index.tz),
        )
        if row is not None:
            start_price = float(row.open)
            start_day = day
            break
    end_price = None
    end_day = None
    for day in reversed(eligible):
        row = base.exact_row(
            spy_sessions[day],
            base.clock_timestamp(day, time(15, 59), spy_sessions[day].index.tz),
        )
        if row is not None:
            end_price = float(row.close)
            end_day = day
            break
    if start_price is None or end_price is None:
        raise RuntimeError("Unable to construct SPY price hurdle")
    ending = 100.0 * end_price / start_price
    return {
        "start_date": str(start_day.date()),
        "end_date": str(end_day.date()),
        "start_price": round(start_price, 6),
        "end_price": round(end_price, 6),
        "starting_cash_usd": 100.0,
        "ending_value_usd": round(ending, 4),
        "price_return_pct": round(ending - 100.0, 4),
        "dividends_included": False,
    }


def stress_table(
    hypothesis: str,
    trades: pd.DataFrame,
    sample: str,
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    pair_sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    feed_sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    years: range,
) -> dict[str, Any]:
    delayed_one = run_period(
        hypothesis,
        spy_sessions,
        pair_sessions,
        feed_sessions,
        excluded,
        years,
        1,
    )
    delayed_five = run_period(
        hypothesis,
        spy_sessions,
        pair_sessions,
        feed_sessions,
        excluded,
        years,
        5,
    )
    return {
        "observed_bbo": geo.summary_or_empty(trades, sample),
        "midpoint_diagnostic": geo.midpoint_or_empty(trades, sample),
        "one_extra_cent_each_fill": geo.summary_or_empty(trades, sample, 0.01),
        "two_extra_cents_each_fill": geo.summary_or_empty(trades, sample, 0.02),
        "one_additional_minute_delay": geo.summary_or_empty(delayed_one, sample),
        "five_additional_minutes_delay": geo.summary_or_empty(delayed_five, sample),
    }


def development_gate(
    stress: dict[str, Any],
    spy_hurdle: dict[str, Any],
) -> tuple[bool, list[str]]:
    passed, failures = geo.development_gate(stress)
    ending = stress["observed_bbo"].get("cash_account", {}).get(
        "ending_equity_usd",
        0.0,
    )
    if ending <= spy_hurdle["ending_value_usd"]:
        failures.append("underperforms_spy_price_only")
    return not failures, failures


def full_cash_path(trades: pd.DataFrame) -> dict[str, float]:
    if trades.empty:
        return {
            "starting_equity_usd": 100.0,
            "ending_equity_usd": 100.0,
            "return_pct": 0.0,
            "maximum_drawdown_usd": 0.0,
        }
    return base.cash_path(trades, base.trade_pnl(trades))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    spy_sessions, feeds = base.load_inputs()
    pair_sessions = geo.load_pair_bars()
    excluded = base.degraded_dates()
    development_hurdle = spy_price_hurdle(
        spy_sessions,
        excluded,
        range(2021, 2024),
    )
    results: dict[str, Any] = {
        "specification": "research_scout/upro_spxu_inventory_state_prereg_v4.json",
        "status": "development_screen_complete",
        "development_spy_price_hurdle": development_hurdle,
        "candidates": {},
    }
    for hypothesis in HYPOTHESES:
        development = run_period(
            hypothesis,
            spy_sessions,
            pair_sessions,
            feeds["arca"],
            excluded,
            range(2021, 2024),
        )
        development_stress = stress_table(
            hypothesis,
            development,
            "development",
            spy_sessions,
            pair_sessions,
            feeds["arca"],
            excluded,
            range(2021, 2024),
        )
        passed, failures = development_gate(
            development_stress,
            development_hurdle,
        )
        candidate: dict[str, Any] = {
            "development": development_stress,
            "gate_passed": passed,
            "gate_failures": failures,
            "secondary_holdout": "not_evaluated",
        }
        if passed:
            holdout = run_period(
                hypothesis,
                spy_sessions,
                pair_sessions,
                feeds["arca"],
                excluded,
                range(2024, 2026),
            )
            holdout_stress = stress_table(
                hypothesis,
                holdout,
                "holdout",
                spy_sessions,
                pair_sessions,
                feeds["arca"],
                excluded,
                range(2024, 2026),
            )
            consolidated = run_period(
                hypothesis,
                spy_sessions,
                pair_sessions,
                feeds["consolidated"],
                excluded,
                range(2024, 2026),
            )
            holdout_stress["consolidated_bbo"] = geo.summary_or_empty(
                consolidated,
                "holdout",
            )
            holdout_days = [
                day
                for day in sorted(spy_sessions)
                if day.year in range(2024, 2026) and day not in excluded
            ]
            holdout_stress["five_session_block_bootstrap"] = (
                base.moving_block_bootstrap(holdout, holdout_days)
                if not holdout.empty
                else {"trades": 0}
            )
            full = run_period(
                hypothesis,
                spy_sessions,
                pair_sessions,
                feeds["arca"],
                excluded,
                range(2021, 2026),
            )
            full_hurdle = spy_price_hurdle(
                spy_sessions,
                excluded,
                range(2021, 2026),
            )
            holdout_stress["five_year_comparison"] = {
                "strategy_cash_account": full_cash_path(full),
                "spy_price_only": full_hurdle,
            }
            candidate["secondary_holdout"] = holdout_stress
        results["candidates"][hypothesis] = candidate
    args.output.write_text(
        json.dumps(results, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    compact = {
        "development_spy_ending_value_usd": development_hurdle["ending_value_usd"],
        "candidates": {
            name: {
                "trades_per_week": row["development"]["observed_bbo"].get(
                    "trades_per_week"
                ),
                "ending_cash_usd": row["development"]["observed_bbo"]
                .get("cash_account", {})
                .get("ending_equity_usd"),
                "net_pnl_usd": row["development"]["observed_bbo"].get("net_pnl_usd"),
                "profit_factor": row["development"]["observed_bbo"].get(
                    "profit_factor"
                ),
                "gate_passed": row["gate_passed"],
                "gate_failures": row["gate_failures"],
            }
            for name, row in results["candidates"].items()
        },
    }
    print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
