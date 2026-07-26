"""Test preregistered slow UPRO/SPXU pair-geometry hypotheses."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Callable
from datetime import time, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base

ROOT = Path(__file__).resolve().parents[1]
PAIR_BARS_PATH = (
    ROOT
    / "external_artifacts"
    / "databento_leveraged_etf"
    / "ARCX.PILLAR"
    / "bars"
    / "upro_spxu_ohlcv_1m_2021-01-01_2026-01-01.dbn.zst"
)
DEFAULT_OUTPUT = ROOT / "research_scout" / "upro_spxu_pair_geometry_results_v2.json"
HYPOTHESES = [
    "late_volume_clock_compass",
    "friction_work_acceleration",
    "same_sign_anomaly_ledger",
    "oriented_path_tortuosity",
    "unmatched_record_topology",
    "creation_redemption_residual_compass",
    "volume_price_gravity_tilt",
]


def load_pair_bars() -> dict[pd.Timestamp, dict[str, pd.DataFrame]]:
    frame = base.load_dbn(PAIR_BARS_PATH)
    result: dict[pd.Timestamp, dict[str, pd.DataFrame]] = {}
    for symbol in ["UPRO", "SPXU"]:
        for day, bars in base.split_sessions(frame[frame.symbol == symbol]).items():
            result.setdefault(day, {})[symbol] = bars
    return result


def exact_window(
    frame: pd.DataFrame,
    day: pd.Timestamp,
    start: time,
    periods: int,
) -> pd.DataFrame | None:
    tz = frame.index.tz
    first = base.clock_timestamp(day, start, tz)
    wanted = pd.date_range(first, periods=periods, freq="min")
    window = frame.reindex(wanted)
    if len(window) != periods or window.isna().all(axis=1).any():
        return None
    return window


def quote_midpoints(frame: pd.DataFrame) -> np.ndarray | None:
    bids = frame.bid_px_00.astype(float).to_numpy()
    asks = frame.ask_px_00.astype(float).to_numpy()
    if np.any(bids <= 0) or np.any(asks < bids):
        return None
    return (bids + asks) / 2.0


def quote_spreads(frame: pd.DataFrame) -> np.ndarray | None:
    mids = quote_midpoints(frame)
    if mids is None:
        return None
    return (
        frame.ask_px_00.astype(float).to_numpy()
        - frame.bid_px_00.astype(float).to_numpy()
    ) / mids


def bar_typical(frame: pd.DataFrame) -> np.ndarray:
    return (
        frame.high.astype(float).to_numpy()
        + frame.low.astype(float).to_numpy()
        + frame.close.astype(float).to_numpy()
    ) / 3.0


def valid_bar_windows(
    day: pd.Timestamp,
    pair_bars: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame] | None:
    if not {"UPRO", "SPXU"}.issubset(pair_bars):
        return None
    bars: dict[str, pd.DataFrame] = {}
    for symbol in ["UPRO", "SPXU"]:
        bar_window = exact_window(pair_bars[symbol], day, time(9, 30), 90)
        if bar_window is None:
            return None
        volumes = bar_window.volume.astype(float).to_numpy()
        if np.any(volumes < 0) or float(volumes.sum()) <= 0:
            return None
        bars[symbol] = bar_window
    return bars


def valid_bbo_windows(
    day: pd.Timestamp,
    quotes: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame] | None:
    if not {"UPRO", "SPXU"}.issubset(quotes):
        return None
    bbo: dict[str, pd.DataFrame] = {}
    for symbol in ["UPRO", "SPXU"]:
        bbo_window = exact_window(quotes[symbol], day, time(9, 31), 90)
        if bbo_window is None or quote_midpoints(bbo_window) is None:
            return None
        bbo[symbol] = bbo_window
    return bbo


def late_volume_clock(
    bars: dict[str, pd.DataFrame],
    bbo: dict[str, pd.DataFrame],
    spy: pd.DataFrame,
) -> float:
    del bbo, spy
    centroids: dict[str, float] = {}
    clock = np.arange(90, dtype=float)
    for symbol in ["UPRO", "SPXU"]:
        volume = bars[symbol].volume.astype(float).to_numpy()
        centroids[symbol] = float(np.dot(clock, volume) / volume.sum())
    return centroids["UPRO"] - centroids["SPXU"]


def friction_work(
    bars: dict[str, pd.DataFrame],
    bbo: dict[str, pd.DataFrame],
    spy: pd.DataFrame,
) -> float:
    del spy
    accelerations: dict[str, float] = {}
    for symbol in ["UPRO", "SPXU"]:
        spreads = quote_spreads(bbo[symbol])
        if spreads is None:
            return math.nan
        dollar_volume = (
            bar_typical(bars[symbol])
            * bars[symbol].volume.astype(float).to_numpy()
        )

        early_weight = dollar_volume[:30]
        late_weight = dollar_volume[60:90]
        early = float(np.dot(spreads[:30], early_weight) / early_weight.sum())
        late = float(np.dot(spreads[60:90], late_weight) / late_weight.sum())
        if early <= 0:
            return math.nan
        accelerations[symbol] = late / early
    return accelerations["UPRO"] - accelerations["SPXU"]


def same_sign_ledger(
    bars: dict[str, pd.DataFrame],
    bbo: dict[str, pd.DataFrame],
    spy: pd.DataFrame,
) -> float:
    del bars, spy
    u = np.diff(np.log(quote_midpoints(bbo["UPRO"])))
    s = np.diff(np.log(quote_midpoints(bbo["SPXU"])))
    same = np.sign(u) == np.sign(s)
    nonzero = (np.sign(u) != 0) & (np.sign(s) != 0)
    usable = same & nonzero
    return float(np.sum(np.sign(u[usable]) * np.minimum(np.abs(u[usable]), np.abs(s[usable]))))


def path_tortuosity(
    bars: dict[str, pd.DataFrame],
    bbo: dict[str, pd.DataFrame],
    spy: pd.DataFrame,
) -> float:
    del bars, spy
    efficiencies: dict[str, float] = {}
    for symbol in ["UPRO", "SPXU"]:
        returns = np.diff(np.log(quote_midpoints(bbo[symbol])))
        distance = float(np.abs(returns).sum())
        if distance <= 0:
            return math.nan
        efficiencies[symbol] = float(returns.sum() / distance)
    return efficiencies["UPRO"] - efficiencies["SPXU"]


def record_topology(
    bars: dict[str, pd.DataFrame],
    bbo: dict[str, pd.DataFrame],
    spy: pd.DataFrame,
) -> float:
    del bars, spy
    u = quote_midpoints(bbo["UPRO"])
    s = quote_midpoints(bbo["SPXU"])
    u_prev_high = np.maximum.accumulate(u)[:-1]
    u_prev_low = np.minimum.accumulate(u)[:-1]
    s_prev_high = np.maximum.accumulate(s)[:-1]
    s_prev_low = np.minimum.accumulate(s)[:-1]
    u_high = u[1:] > u_prev_high
    u_low = u[1:] < u_prev_low
    s_high = s[1:] > s_prev_high
    s_low = s[1:] < s_prev_low
    bullish = np.logical_xor(u_high, s_low).sum()
    bearish = np.logical_xor(s_high, u_low).sum()
    return float(bullish - bearish)


def creation_residual(
    bars: dict[str, pd.DataFrame],
    bbo: dict[str, pd.DataFrame],
    spy: pd.DataFrame,
) -> float:
    del bars
    day = pd.Timestamp(spy.index[0].date())
    spy_window = exact_window(spy, day, time(9, 30), 90)
    if spy_window is None:
        return math.nan
    x = math.log(float(spy_window.close.iloc[-1]) / float(spy_window.open.iloc[0]))
    u_mid = quote_midpoints(bbo["UPRO"])
    s_mid = quote_midpoints(bbo["SPXU"])
    u = math.log(float(u_mid[-1]) / float(u_mid[0]))
    s = math.log(float(s_mid[-1]) / float(s_mid[0]))
    return (u - 3.0 * x) - (s + 3.0 * x)


def gravity_tilt(
    bars: dict[str, pd.DataFrame],
    bbo: dict[str, pd.DataFrame],
    spy: pd.DataFrame,
) -> float:
    del bbo, spy
    tilts: dict[str, float] = {}
    for symbol in ["UPRO", "SPXU"]:
        prices = bar_typical(bars[symbol])
        volume = bars[symbol].volume.astype(float).to_numpy()
        unweighted = float(prices.mean())
        weighted = float(np.dot(prices, volume) / volume.sum())
        if unweighted <= 0:
            return math.nan
        tilts[symbol] = weighted / unweighted - 1.0
    return tilts["UPRO"] - tilts["SPXU"]


SCORERS: dict[
    str,
    Callable[[dict[str, pd.DataFrame], dict[str, pd.DataFrame], pd.DataFrame], float],
] = {
    "late_volume_clock_compass": late_volume_clock,
    "friction_work_acceleration": friction_work,
    "same_sign_anomaly_ledger": same_sign_ledger,
    "oriented_path_tortuosity": path_tortuosity,
    "unmatched_record_topology": record_topology,
    "creation_redemption_residual_compass": creation_residual,
    "volume_price_gravity_tilt": gravity_tilt,
}
BBO_REQUIRED = {
    "friction_work_acceleration",
    "same_sign_anomaly_ledger",
    "oriented_path_tortuosity",
    "unmatched_record_topology",
    "creation_redemption_residual_compass",
}
BAR_REQUIRED = {
    "late_volume_clock_compass",
    "friction_work_acceleration",
    "volume_price_gravity_tilt",
}


def direction(value: float) -> int:
    if not math.isfinite(value):
        return 0
    return int(value > 0) - int(value < 0)


def make_signal(
    hypothesis: str,
    day: pd.Timestamp,
    spy: pd.DataFrame,
    pair_bars: dict[str, pd.DataFrame],
    quotes: dict[str, pd.DataFrame],
) -> dict[str, Any] | None:
    if hypothesis in BAR_REQUIRED:
        bars = valid_bar_windows(day, pair_bars)
        if bars is None:
            return None
    else:
        bars = {}
    if hypothesis in BBO_REQUIRED:
        bbo = valid_bbo_windows(day, quotes)
        if bbo is None:
            return None
    else:
        bbo = {}
    score = SCORERS[hypothesis](bars, bbo, spy)
    signal_direction = direction(score)
    if signal_direction == 0:
        return None
    return {
        "hypothesis": hypothesis,
        "date": day,
        "direction": signal_direction,
        "score": score,
    }


def simulate(
    signal: dict[str, Any],
    spy: pd.DataFrame,
    quotes: pd.DataFrame,
    additional_delay_minutes: int = 0,
) -> dict[str, Any] | None:
    day = signal["date"]
    tz = spy.index.tz
    anchor_stamp = base.clock_timestamp(day, time(11, 1), tz)
    entry_stamp = anchor_stamp + timedelta(minutes=additional_delay_minutes)
    exit_stamp = base.clock_timestamp(day, time(15, 30), tz)
    anchor_bar = base.exact_row(spy, anchor_stamp)
    entry_quote = base.quote_at(quotes, entry_stamp)
    if anchor_bar is None or entry_quote is None:
        return None
    anchor = float(anchor_bar.open)
    signal_direction = int(signal["direction"])
    stop = anchor * (1.0 - signal_direction / 30.0)
    if additional_delay_minutes and base.stop_touched(
        spy,
        anchor_stamp,
        entry_stamp,
        signal_direction,
        stop,
    ):
        return None
    scan = spy[(spy.index >= entry_stamp) & (spy.index < exit_stamp)]
    trigger_stamp = None
    for idx, row in scan.iterrows():
        touched = row.low <= stop if signal_direction == 1 else row.high >= stop
        if touched:
            trigger_stamp = idx + timedelta(minutes=1)
            break
    desired_exit = trigger_stamp if trigger_stamp is not None else exit_stamp
    exit_quote = base.quote_at(quotes, desired_exit, max_lag_minutes=2)
    if exit_quote is None:
        return None
    return {
        "hypothesis": signal["hypothesis"],
        "date": day,
        "direction": "bullish" if signal_direction == 1 else "bearish",
        "symbol": "UPRO" if signal_direction == 1 else "SPXU",
        "score": float(signal["score"]),
        "planned_notional": 100.0,
        "signal_entry": anchor,
        "stop": stop,
        "entry_time": entry_stamp,
        "exit_time": exit_quote.name,
        "entry_ask": float(entry_quote.ask_px_00),
        "entry_bid": float(entry_quote.bid_px_00),
        "exit_bid": float(exit_quote.bid_px_00),
        "exit_ask": float(exit_quote.ask_px_00),
        "reason": "stop" if trigger_stamp is not None else "time",
        "additional_delay_minutes": additional_delay_minutes,
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
        signal = make_signal(hypothesis, day, spy_sessions[day], pair_bars, quotes)
        if signal is None:
            continue
        symbol = "UPRO" if signal["direction"] == 1 else "SPXU"
        trade = simulate(
            signal,
            spy_sessions[day],
            quotes[symbol],
            additional_delay_minutes,
        )
        if trade is not None:
            records.append(trade)
    return pd.DataFrame(records)


def summary_or_empty(trades: pd.DataFrame, sample: str, cents: float = 0.0) -> dict[str, Any]:
    if trades.empty:
        return {"trades": 0}
    return base.summarize(trades, sample, cents)


def midpoint_or_empty(trades: pd.DataFrame, sample: str) -> dict[str, Any]:
    if trades.empty:
        return {"trades": 0}
    return base.summarize(trades, sample, midpoint_execution=True)


def development_gate(stress: dict[str, Any]) -> tuple[bool, list[str]]:
    observed = stress["observed_bbo"]
    one_cent = stress["one_extra_cent_each_fill"]
    delay_five = stress["five_additional_minutes_delay"]
    failures: list[str] = []
    if observed.get("trades_per_week", 0.0) < 2.0:
        failures.append("frequency")
    if observed.get("net_pnl_usd", 0.0) <= 0:
        failures.append("base_pnl")
    if observed.get("profit_factor", 0.0) <= 1.0:
        failures.append("profit_factor")
    if not all(value > 0 for value in observed.get("year_pnl_usd", {}).values()):
        failures.append("each_year")
    directions = observed.get("direction_pnl_usd", {})
    if set(directions) != {"bullish", "bearish"} or not all(
        value > 0 for value in directions.values()
    ):
        failures.append("both_directions")
    if one_cent.get("net_pnl_usd", 0.0) <= 0:
        failures.append("extra_cent_each_fill")
    if delay_five.get("net_pnl_usd", 0.0) <= 0:
        failures.append("five_minute_delay")
    if observed.get("net_without_five_best_usd", 0.0) <= 0:
        failures.append("remove_five_best")
    return not failures, failures


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
        "observed_bbo": summary_or_empty(trades, sample),
        "midpoint_diagnostic": midpoint_or_empty(trades, sample),
        "one_extra_cent_each_fill": summary_or_empty(trades, sample, 0.01),
        "two_extra_cents_each_fill": summary_or_empty(trades, sample, 0.02),
        "one_additional_minute_delay": summary_or_empty(delayed_one, sample),
        "five_additional_minutes_delay": summary_or_empty(delayed_five, sample),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    spy_sessions, feeds = base.load_inputs()
    pair_sessions = load_pair_bars()
    excluded = base.degraded_dates()
    results: dict[str, Any] = {
        "specification": "research_scout/upro_spxu_pair_geometry_prereg_v2.json",
        "status": "development_screen_complete",
        "excluded_degraded_dates": len(excluded),
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
        passed, failures = development_gate(development_stress)
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
            holdout_stress["consolidated_bbo"] = summary_or_empty(
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
            candidate["secondary_holdout"] = holdout_stress
        results["candidates"][hypothesis] = candidate
    args.output.write_text(
        json.dumps(results, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    compact = {
        name: {
            "trades_per_week": row["development"]["observed_bbo"].get(
                "trades_per_week"
            ),
            "net_pnl_usd": row["development"]["observed_bbo"].get("net_pnl_usd"),
            "profit_factor": row["development"]["observed_bbo"].get(
                "profit_factor"
            ),
            "gate_passed": row["gate_passed"],
            "gate_failures": row["gate_failures"],
        }
        for name, row in results["candidates"].items()
    }
    print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
