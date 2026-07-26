"""Test preregistered creative UPRO/SPXU intraday hypotheses with BBO fills."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import time, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import databento as db  # noqa: E402, I001
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


SPY_PATH = (
    ROOT
    / "external_artifacts"
    / "databento_fractional_etf"
    / "ARCX.PILLAR"
    / "bars"
    / "spy_sh_ohlcv_1m_2021-01-01_2026-01-01.dbn.zst"
)
ARCA_BBO_PATH = (
    ROOT
    / "external_artifacts"
    / "databento_leveraged_etf"
    / "ARCX.PILLAR"
    / "bbo"
    / "upro_spxu_bbo_1m_2021-01-01_2026-01-01.dbn.zst"
)
MINI_BBO_PATH = (
    ROOT
    / "external_artifacts"
    / "databento_leveraged_etf"
    / "EQUS.MINI"
    / "bbo"
    / "upro_spxu_bbo_1m_2023-03-28_2026-01-01.dbn.zst"
)
CONDITION_PATH = (
    ROOT
    / "external_artifacts"
    / "databento_fractional_etf"
    / "ARCX.PILLAR"
    / "dataset_condition_2021_2025.json"
)
DEFAULT_OUTPUT = (
    ROOT / "research_scout" / "upro_spxu_creative_hypotheses_results_v1.json"
)

ACCOUNT_CASH = 100.0
RISK_BUDGET = 10.0
LEVERAGE_MULTIPLE = 3.0
WEEKS = {"development": 156.0, "holdout": 104.0}


@dataclass(frozen=True)
class Signal:
    hypothesis: str
    date: pd.Timestamp
    direction: int
    stop: float
    decision_time: time
    entry_time: time
    exit_time: time


def load_dbn(path: Path, symbol: str | None = None) -> pd.DataFrame:
    frame = db.DBNStore.from_file(path).to_df()
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    frame = frame.tz_convert("America/New_York").sort_index()
    if symbol is not None:
        frame = frame[frame.symbol == symbol]
    return frame


def split_sessions(frame: pd.DataFrame) -> dict[pd.Timestamp, pd.DataFrame]:
    sessions: dict[pd.Timestamp, pd.DataFrame] = {}
    for day, bars in frame.groupby(frame.index.normalize()):
        sessions[day.tz_localize(None)] = bars.sort_index()
    return sessions


def load_inputs() -> tuple[
    dict[pd.Timestamp, pd.DataFrame],
    dict[str, dict[pd.Timestamp, dict[str, pd.DataFrame]]],
]:
    spy_sessions = split_sessions(load_dbn(SPY_PATH, "SPY"))
    feeds: dict[str, dict[pd.Timestamp, dict[str, pd.DataFrame]]] = {}
    for feed_name, path in {"arca": ARCA_BBO_PATH, "consolidated": MINI_BBO_PATH}.items():
        frame = load_dbn(path)
        feed_sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]] = {}
        for symbol in ["UPRO", "SPXU"]:
            for day, quotes in split_sessions(frame[frame.symbol == symbol]).items():
                feed_sessions.setdefault(day, {})[symbol] = quotes
        feeds[feed_name] = feed_sessions
    return spy_sessions, feeds


def degraded_dates() -> set[pd.Timestamp]:
    payload = json.loads(CONDITION_PATH.read_text(encoding="utf-8"))
    return {
        pd.Timestamp(row["date"])
        for row in payload["conditions"]
        if row["condition"] == "degraded"
    }


def between(frame: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return frame.between_time(start, end, inclusive="both")


def typical(frame: pd.DataFrame) -> pd.Series:
    return (frame.high + frame.low + frame.close) / 3.0


def volume_center(frame: pd.DataFrame) -> float:
    volume = frame.volume.astype(float)
    if frame.empty or float(volume.sum()) <= 0:
        return math.nan
    return float((typical(frame) * volume).sum() / volume.sum())


def sign(value: float) -> int:
    return int(value > 0) - int(value < 0)


def clock_timestamp(day: pd.Timestamp, clock: time, tz: Any) -> pd.Timestamp:
    return pd.Timestamp.combine(day.date(), clock).tz_localize(tz)


def exact_row(frame: pd.DataFrame, stamp: pd.Timestamp) -> pd.Series | None:
    try:
        row = frame.loc[stamp]
    except KeyError:
        return None
    return row.iloc[-1] if isinstance(row, pd.DataFrame) else row


def valid_quote(row: pd.Series | None) -> bool:
    if row is None:
        return False
    bid = float(row.bid_px_00)
    ask = float(row.ask_px_00)
    return bid > 0 and ask > 0 and ask >= bid


def quote_at(
    frame: pd.DataFrame,
    stamp: pd.Timestamp,
    max_lag_minutes: int = 0,
) -> pd.Series | None:
    for offset in range(max_lag_minutes + 1):
        row = exact_row(frame, stamp + timedelta(minutes=offset))
        if valid_quote(row):
            return row
    return None


def midpoint(row: pd.Series) -> float:
    return (float(row.bid_px_00) + float(row.ask_px_00)) / 2.0


def proportional_spread(row: pd.Series) -> float:
    return (float(row.ask_px_00) - float(row.bid_px_00)) / midpoint(row)


def opening_features(bars: pd.DataFrame) -> dict[str, Any] | None:
    opening = between(bars, "09:30", "09:59")
    if len(opening) != 30:
        return None
    cash_open = float(opening.iloc[0].open)
    close = float(opening.iloc[-1].close)
    center = volume_center(opening)
    if not np.isfinite(center):
        return None
    direction = sign(close - cash_open)
    migration = (
        0
        if direction == 0 or sign(center - cash_open) != direction
        else direction
    )
    return {
        "opening": opening,
        "cash_open": cash_open,
        "close": close,
        "center": center,
        "high": float(opening.high.max()),
        "low": float(opening.low.min()),
        "migration": migration,
    }


def prior_close(
    day: pd.Timestamp,
    ordered_days: list[pd.Timestamp],
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
) -> float | None:
    position = ordered_days.index(day)
    if position == 0:
        return None
    previous_day = ordered_days[position - 1]
    if previous_day in excluded:
        return None
    previous = spy_sessions[previous_day]
    row = exact_row(
        previous,
        clock_timestamp(previous_day, time(15, 59), previous.index.tz),
    )
    return float(row.close) if row is not None else None


def daily_reset_recoil(
    day: pd.Timestamp,
    bars: pd.DataFrame,
    previous_close: float | None,
    quotes: dict[str, pd.DataFrame],
) -> Signal | None:
    del quotes
    f = opening_features(bars)
    if f is None or previous_close is None:
        return None
    gap_direction = sign(float(f["cash_open"]) - previous_close)
    counter_direction = sign(float(f["close"]) - float(f["cash_open"]))
    if gap_direction == 0 or counter_direction != -gap_direction:
        return None
    if sign(float(f["close"]) - previous_close) != gap_direction:
        return None
    return Signal(
        "daily_reset_recoil",
        day,
        gap_direction,
        previous_close,
        time(10, 0),
        time(10, 1),
        time(15, 30),
    )


def second_auction_lease(
    day: pd.Timestamp,
    bars: pd.DataFrame,
    previous_close: float | None,
    quotes: dict[str, pd.DataFrame],
) -> Signal | None:
    del previous_close, quotes
    f = opening_features(bars)
    if f is None or int(f["migration"]) == 0:
        return None
    second = between(bars, "10:00", "10:14")
    if len(second) != 15:
        return None
    direction = int(f["migration"])
    second_center = volume_center(second)
    second_close = float(second.iloc[-1].close)
    if sign(second_center - float(f["center"])) != direction:
        return None
    if sign(second_close - float(f["center"])) != direction:
        return None
    return Signal(
        "second_auction_ownership_lease",
        day,
        direction,
        float(f["center"]),
        time(10, 15),
        time(10, 16),
        time(15, 30),
    )


def liquidity_seesaw(
    day: pd.Timestamp,
    bars: pd.DataFrame,
    previous_close: float | None,
    quotes: dict[str, pd.DataFrame],
) -> Signal | None:
    del previous_close
    f = opening_features(bars)
    if f is None or int(f["migration"]) == 0:
        return None
    direction = int(f["migration"])
    chosen = "UPRO" if direction == 1 else "SPXU"
    opposite = "SPXU" if direction == 1 else "UPRO"
    ratios: dict[str, float] = {}
    for symbol in [chosen, opposite]:
        frame = quotes.get(symbol)
        if frame is None:
            return None
        window = between(frame, "09:31", "10:00")
        valid_rows = window[
            (window.bid_px_00 > 0)
            & (window.ask_px_00 > 0)
            & (window.ask_px_00 >= window.bid_px_00)
        ]
        if len(valid_rows) != 30:
            return None
        spreads = (
            (valid_rows.ask_px_00 - valid_rows.bid_px_00)
            / ((valid_rows.ask_px_00 + valid_rows.bid_px_00) / 2.0)
        )
        current = exact_row(
            frame,
            clock_timestamp(day, time(10, 0), frame.index.tz),
        )
        if not valid_quote(current) or float(spreads.median()) <= 0:
            return None
        ratios[symbol] = proportional_spread(current) / float(spreads.median())
    if not ratios[chosen] < ratios[opposite]:
        return None
    return Signal(
        "opening_liquidity_seesaw",
        day,
        direction,
        float(f["center"]),
        time(10, 0),
        time(10, 1),
        time(15, 30),
    )


def path_hysteresis(
    day: pd.Timestamp,
    bars: pd.DataFrame,
    previous_close: float | None,
    quotes: dict[str, pd.DataFrame],
) -> Signal | None:
    del previous_close
    f = opening_features(bars)
    if f is None or int(f["migration"]) == 0:
        return None
    pair_return = 0.0
    for symbol in ["UPRO", "SPXU"]:
        frame = quotes.get(symbol)
        if frame is None:
            return None
        start = exact_row(
            frame,
            clock_timestamp(day, time(9, 30), frame.index.tz),
        )
        end = exact_row(
            frame,
            clock_timestamp(day, time(10, 0), frame.index.tz),
        )
        if not valid_quote(start) or not valid_quote(end):
            return None
        pair_return += midpoint(end) / midpoint(start) - 1.0
    if pair_return <= 0:
        return None
    return Signal(
        "dual_etf_path_hysteresis",
        day,
        int(f["migration"]),
        float(f["center"]),
        time(10, 0),
        time(10, 1),
        time(15, 30),
    )


def corridor_escape(
    day: pd.Timestamp,
    bars: pd.DataFrame,
    previous_close: float | None,
    quotes: dict[str, pd.DataFrame],
) -> Signal | None:
    del quotes
    f = opening_features(bars)
    if f is None or previous_close is None:
        return None
    lower = min(previous_close, float(f["center"]))
    upper = max(previous_close, float(f["center"]))
    if float(f["low"]) > lower or float(f["high"]) < upper:
        return None
    close = float(f["close"])
    direction = 1 if close > upper else -1 if close < lower else 0
    if direction == 0:
        return None
    stop = lower if direction == 1 else upper
    return Signal(
        "reset_corridor_escape",
        day,
        direction,
        stop,
        time(10, 0),
        time(10, 1),
        time(15, 30),
    )


def closing_torque(
    day: pd.Timestamp,
    bars: pd.DataFrame,
    previous_close: float | None,
    quotes: dict[str, pd.DataFrame],
) -> Signal | None:
    del quotes
    if previous_close is None:
        return None
    tz = bars.index.tz
    start = exact_row(bars, clock_timestamp(day, time(13, 30), tz))
    end = exact_row(bars, clock_timestamp(day, time(14, 29), tz))
    if start is None or end is None:
        return None
    day_direction = sign(float(end.close) - previous_close)
    late_direction = sign(float(end.close) - float(start.open))
    if day_direction == 0 or late_direction != day_direction:
        return None
    return Signal(
        "closing_rebalance_torque",
        day,
        day_direction,
        float(start.open),
        time(14, 30),
        time(14, 31),
        time(15, 55),
    )


def benchmark(
    day: pd.Timestamp,
    bars: pd.DataFrame,
    previous_close: float | None,
    quotes: dict[str, pd.DataFrame],
) -> Signal | None:
    del previous_close, quotes
    f = opening_features(bars)
    if f is None or int(f["migration"]) == 0:
        return None
    return Signal(
        "opening_center_migration_bbo_benchmark",
        day,
        int(f["migration"]),
        float(f["center"]),
        time(10, 0),
        time(10, 1),
        time(15, 30),
    )


Builder = Callable[
    [pd.Timestamp, pd.DataFrame, float | None, dict[str, pd.DataFrame]],
    Signal | None,
]
BUILDERS: dict[str, Builder] = {
    "daily_reset_recoil": daily_reset_recoil,
    "second_auction_ownership_lease": second_auction_lease,
    "opening_liquidity_seesaw": liquidity_seesaw,
    "dual_etf_path_hysteresis": path_hysteresis,
    "reset_corridor_escape": corridor_escape,
    "closing_rebalance_torque": closing_torque,
    "opening_center_migration_bbo_benchmark": benchmark,
}


def stop_touched(
    bars: pd.DataFrame,
    start: pd.Timestamp,
    end_exclusive: pd.Timestamp,
    direction: int,
    stop: float,
) -> bool:
    scan = bars[(bars.index >= start) & (bars.index < end_exclusive)]
    if direction == 1:
        return bool((scan.low <= stop).any())
    return bool((scan.high >= stop).any())


def simulate_signal(
    signal: Signal,
    spy: pd.DataFrame,
    quotes: pd.DataFrame,
    additional_delay_minutes: int = 0,
) -> dict[str, Any] | None:
    tz = spy.index.tz
    decision_stamp = clock_timestamp(signal.date, signal.decision_time, tz)
    frozen_entry_stamp = clock_timestamp(signal.date, signal.entry_time, tz)
    entry_stamp = frozen_entry_stamp + timedelta(minutes=additional_delay_minutes)
    exit_stamp = clock_timestamp(signal.date, signal.exit_time, tz)

    if stop_touched(
        spy,
        decision_stamp,
        entry_stamp,
        signal.direction,
        signal.stop,
    ):
        return None
    entry_quote = quote_at(quotes, entry_stamp)
    signal_entry_bar = exact_row(spy, entry_stamp)
    if entry_quote is None or signal_entry_bar is None:
        return None
    signal_entry = float(signal_entry_bar.open)
    if signal.direction == 1 and signal.stop >= signal_entry:
        return None
    if signal.direction == -1 and signal.stop <= signal_entry:
        return None

    stop_pct = abs(signal_entry - signal.stop) / signal_entry
    planned_notional = min(
        ACCOUNT_CASH,
        RISK_BUDGET / max(LEVERAGE_MULTIPLE * stop_pct, 1e-12),
    )
    scan = spy[(spy.index >= entry_stamp) & (spy.index < exit_stamp)]
    trigger_stamp: pd.Timestamp | None = None
    for idx, row in scan.iterrows():
        hit = row.low <= signal.stop if signal.direction == 1 else row.high >= signal.stop
        if hit:
            trigger_stamp = idx + timedelta(minutes=1)
            break

    reason = "stop" if trigger_stamp is not None else "time"
    desired_exit = trigger_stamp if trigger_stamp is not None else exit_stamp
    exit_quote = quote_at(quotes, desired_exit, max_lag_minutes=2)
    if exit_quote is None:
        return None
    symbol = "UPRO" if signal.direction == 1 else "SPXU"
    return {
        "hypothesis": signal.hypothesis,
        "date": signal.date,
        "direction": "bullish" if signal.direction == 1 else "bearish",
        "symbol": symbol,
        "planned_notional": planned_notional,
        "signal_entry": signal_entry,
        "stop": signal.stop,
        "entry_time": entry_stamp,
        "exit_time": exit_quote.name,
        "entry_ask": float(entry_quote.ask_px_00),
        "entry_bid": float(entry_quote.bid_px_00),
        "exit_bid": float(exit_quote.bid_px_00),
        "exit_ask": float(exit_quote.ask_px_00),
        "reason": reason,
        "additional_delay_minutes": additional_delay_minutes,
    }


def run_period(
    builder: Builder,
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    feed_sessions: dict[pd.Timestamp, dict[str, pd.DataFrame]],
    excluded: set[pd.Timestamp],
    years: range,
    additional_delay_minutes: int = 0,
) -> pd.DataFrame:
    ordered_days = sorted(spy_sessions)
    records: list[dict[str, Any]] = []
    for day in ordered_days:
        if day.year not in years or day in excluded:
            continue
        day_quotes = feed_sessions.get(day)
        if day_quotes is None or not {"UPRO", "SPXU"}.issubset(day_quotes):
            continue
        spy = spy_sessions[day]
        previous = prior_close(day, ordered_days, spy_sessions, excluded)
        signal = builder(day, spy, previous, day_quotes)
        if signal is None:
            continue
        symbol = "UPRO" if signal.direction == 1 else "SPXU"
        trade = simulate_signal(
            signal,
            spy,
            day_quotes[symbol],
            additional_delay_minutes=additional_delay_minutes,
        )
        if trade is not None:
            records.append(trade)
    return pd.DataFrame(records)


def trade_pnl(
    trades: pd.DataFrame,
    extra_cents_each_fill: float = 0.0,
    midpoint_execution: bool = False,
) -> pd.Series:
    if midpoint_execution:
        entry = (trades.entry_ask + trades.entry_bid) / 2.0
        exit_price = (trades.exit_ask + trades.exit_bid) / 2.0
    else:
        entry = trades.entry_ask + extra_cents_each_fill
        exit_price = trades.exit_bid - extra_cents_each_fill
    quantity = trades.planned_notional / entry
    return quantity * (exit_price - entry)


def profit_factor(pnl: pd.Series) -> float:
    gains = float(pnl[pnl > 0].sum())
    losses = float(-pnl[pnl < 0].sum())
    return gains / losses if losses else math.inf


def fixed_notional_drawdown(pnl: pd.Series, dates: pd.Series) -> float:
    daily = pnl.groupby(dates).sum().sort_index()
    equity = daily.cumsum()
    return float((equity - equity.cummax()).min())


def cash_path(trades: pd.DataFrame, pnl: pd.Series) -> dict[str, float]:
    equity = ACCOUNT_CASH
    peak = equity
    maximum_drawdown = 0.0
    ordered = trades.sort_values(["date", "entry_time"])
    for idx in ordered.index:
        planned = float(trades.loc[idx, "planned_notional"])
        deployed = min(equity, planned)
        equity += deployed * float(pnl.loc[idx]) / planned
        peak = max(peak, equity)
        maximum_drawdown = min(maximum_drawdown, equity - peak)
    return {
        "starting_equity_usd": ACCOUNT_CASH,
        "ending_equity_usd": round(equity, 4),
        "return_pct": round((equity / ACCOUNT_CASH - 1.0) * 100.0, 4),
        "maximum_drawdown_usd": round(maximum_drawdown, 4),
    }


def summarize(
    trades: pd.DataFrame,
    sample: str,
    extra_cents_each_fill: float = 0.0,
    midpoint_execution: bool = False,
) -> dict[str, Any]:
    pnl = trade_pnl(
        trades,
        extra_cents_each_fill,
        midpoint_execution=midpoint_execution,
    )
    years = trades.date.dt.year
    directions = trades.direction
    without_five = pnl.drop(pnl.nlargest(min(5, len(pnl))).index)
    entry_mid = (trades.entry_ask + trades.entry_bid) / 2.0
    entry_spread_bps = (trades.entry_ask - trades.entry_bid) / entry_mid * 10000.0
    return {
        "trades": int(len(trades)),
        "trades_per_week": round(float(len(trades) / WEEKS[sample]), 3),
        "net_pnl_usd": round(float(pnl.sum()), 4),
        "mean_trade_usd": round(float(pnl.mean()), 5),
        "median_trade_usd": round(float(pnl.median()), 5),
        "win_rate": round(float((pnl > 0).mean()), 4),
        "profit_factor": round(float(profit_factor(pnl)), 4),
        "fixed_notional_max_drawdown_usd": round(
            fixed_notional_drawdown(pnl, trades.date),
            4,
        ),
        "cash_account": cash_path(trades, pnl),
        "worst_trade_usd": round(float(pnl.min()), 4),
        "net_without_five_best_usd": round(float(without_five.sum()), 4),
        "year_pnl_usd": {
            str(int(year)): round(float(pnl[years == year].sum()), 4)
            for year in sorted(years.unique())
        },
        "direction_pnl_usd": {
            direction: round(float(pnl[directions == direction].sum()), 4)
            for direction in sorted(directions.unique())
        },
        "reason_counts": {
            reason: int(count)
            for reason, count in trades.reason.value_counts().sort_index().items()
        },
        "planned_notional_usd": {
            "median": round(float(trades.planned_notional.median()), 4),
            "minimum": round(float(trades.planned_notional.min()), 4),
        },
        "entry_spread_bps": {
            "median": round(float(entry_spread_bps.median()), 4),
            "p95": round(float(entry_spread_bps.quantile(0.95)), 4),
        },
    }


def development_gate(
    base: dict[str, Any],
    extra_cent: dict[str, Any],
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if float(base["trades_per_week"]) < 2.0:
        failures.append("frequency")
    if float(base["net_pnl_usd"]) <= 0:
        failures.append("base_pnl")
    if float(base["profit_factor"]) <= 1.0:
        failures.append("profit_factor")
    years = base["year_pnl_usd"]
    if set(years) != {"2021", "2022", "2023"}:
        failures.append("year_coverage")
    elif any(float(value) <= 0 for value in years.values()):
        failures.append("each_year")
    directions = base["direction_pnl_usd"]
    if set(directions) != {"bearish", "bullish"}:
        failures.append("direction_coverage")
    elif any(float(value) <= 0 for value in directions.values()):
        failures.append("both_directions")
    if float(extra_cent["net_pnl_usd"]) <= 0:
        failures.append("extra_cent_each_fill")
    return not failures, failures


def moving_block_bootstrap(
    trades: pd.DataFrame,
    session_days: list[pd.Timestamp],
    iterations: int = 5000,
) -> dict[str, Any]:
    pnl = trade_pnl(trades)
    daily = pnl.groupby(trades.date).sum().reindex(session_days, fill_value=0.0)
    values = daily.to_numpy(dtype=float)
    block = 5
    starts = np.arange(max(1, len(values) - block + 1))
    rng = np.random.default_rng(20260726)
    totals = np.empty(iterations)
    max_drawdowns = np.empty(iterations)
    blocks_needed = math.ceil(len(values) / block)
    for iteration in range(iterations):
        selected = rng.choice(starts, size=blocks_needed, replace=True)
        sample = np.concatenate([values[start : start + block] for start in selected])[
            : len(values)
        ]
        totals[iteration] = float(sample.sum())
        curve = np.cumsum(sample)
        max_drawdowns[iteration] = float(np.min(curve - np.maximum.accumulate(curve)))
    return {
        "iterations": iterations,
        "block_sessions": block,
        "probability_total_not_positive": round(float((totals <= 0).mean()), 4),
        "total_pnl_95pct_interval_usd": [
            round(float(np.quantile(totals, 0.025)), 4),
            round(float(np.quantile(totals, 0.975)), 4),
        ],
        "median_max_drawdown_usd": round(float(np.median(max_drawdowns)), 4),
        "five_percent_bad_tail_max_drawdown_usd": round(
            float(np.quantile(max_drawdowns, 0.05)),
            4,
        ),
    }


def stress_table(trades: pd.DataFrame, sample: str) -> dict[str, Any]:
    return {
        "observed_bbo": summarize(trades, sample, 0.0),
        "midpoint_diagnostic": summarize(
            trades,
            sample,
            midpoint_execution=True,
        ),
        "one_extra_cent_each_fill": summarize(trades, sample, 0.01),
        "two_extra_cents_each_fill": summarize(trades, sample, 0.02),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    spy_sessions, feeds = load_inputs()
    excluded = degraded_dates()
    results: dict[str, Any] = {
        "specification": "research_scout/upro_spxu_creative_hypotheses_prereg_v1.json",
        "status": "development_screen_complete",
        "excluded_degraded_dates": len(excluded),
        "candidates": {},
    }
    benchmark_id = "opening_center_migration_bbo_benchmark"

    for name, builder in BUILDERS.items():
        development = run_period(
            builder,
            spy_sessions,
            feeds["arca"],
            excluded,
            range(2021, 2024),
        )
        if development.empty:
            results["candidates"][name] = {
                "development": {"trades": 0},
                "gate_passed": False,
                "gate_failures": ["no_trades"],
                "secondary_holdout": "not_evaluated",
            }
            continue
        development_stress = stress_table(development, "development")
        delayed_one = run_period(
            builder,
            spy_sessions,
            feeds["arca"],
            excluded,
            range(2021, 2024),
            additional_delay_minutes=1,
        )
        delayed_five = run_period(
            builder,
            spy_sessions,
            feeds["arca"],
            excluded,
            range(2021, 2024),
            additional_delay_minutes=5,
        )
        development_stress["one_additional_minute_delay"] = (
            summarize(delayed_one, "development") if not delayed_one.empty else {"trades": 0}
        )
        development_stress["five_additional_minutes_delay"] = (
            summarize(delayed_five, "development")
            if not delayed_five.empty
            else {"trades": 0}
        )
        passed, failures = development_gate(
            development_stress["observed_bbo"],
            development_stress["one_extra_cent_each_fill"],
        )
        candidate: dict[str, Any] = {
            "development": development_stress,
            "gate_passed": passed,
            "gate_failures": failures,
        }

        if passed or name == benchmark_id:
            holdout = run_period(
                builder,
                spy_sessions,
                feeds["arca"],
                excluded,
                range(2024, 2026),
            )
            holdout_stress = stress_table(holdout, "holdout")
            holdout_delay_one = run_period(
                builder,
                spy_sessions,
                feeds["arca"],
                excluded,
                range(2024, 2026),
                additional_delay_minutes=1,
            )
            holdout_delay_five = run_period(
                builder,
                spy_sessions,
                feeds["arca"],
                excluded,
                range(2024, 2026),
                additional_delay_minutes=5,
            )
            holdout_stress["one_additional_minute_delay"] = (
                summarize(holdout_delay_one, "holdout")
                if not holdout_delay_one.empty
                else {"trades": 0}
            )
            holdout_stress["five_additional_minutes_delay"] = (
                summarize(holdout_delay_five, "holdout")
                if not holdout_delay_five.empty
                else {"trades": 0}
            )
            consolidated = run_period(
                builder,
                spy_sessions,
                feeds["consolidated"],
                excluded,
                range(2024, 2026),
            )
            holdout_stress["consolidated_bbo"] = (
                summarize(consolidated, "holdout")
                if not consolidated.empty
                else {"trades": 0}
            )
            holdout_days = [
                day
                for day in sorted(spy_sessions)
                if day.year in range(2024, 2026) and day not in excluded
            ]
            holdout_stress["five_session_block_bootstrap"] = moving_block_bootstrap(
                holdout,
                holdout_days,
            )
            candidate["secondary_holdout"] = holdout_stress
        else:
            candidate["secondary_holdout"] = "not_evaluated"
        results["candidates"][name] = candidate

    args.output.write_text(
        json.dumps(results, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(results, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
