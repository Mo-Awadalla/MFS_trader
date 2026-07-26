"""Test preregistered $100 SPY/SH fractional-share intraday hypotheses."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import databento as db  # noqa: E402, I001
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


DATA_PATH = (
    ROOT
    / "external_artifacts"
    / "databento_fractional_etf"
    / "ARCX.PILLAR"
    / "bars"
    / "spy_sh_ohlcv_1m_2021-01-01_2026-01-01.dbn.zst"
)
CONDITION_PATH = (
    ROOT
    / "external_artifacts"
    / "databento_fractional_etf"
    / "ARCX.PILLAR"
    / "dataset_condition_2021_2025.json"
)
DEFAULT_OUTPUT = ROOT / "research_scout" / "spy_sh_fractional_hypotheses_results_v1.json"

ACCOUNT_CASH = 100.0
RISK_BUDGET = 10.0
BASE_BPS = {"SPY": 3.0, "SH": 10.0}
WEEKS = {"development": 156.0, "holdout": 104.0}


@dataclass(frozen=True)
class Signal:
    hypothesis: str
    date: pd.Timestamp
    direction: int
    stop: float
    target: float | None
    entry_time: time
    exit_time: time


def load_data() -> tuple[dict[pd.Timestamp, pd.DataFrame], dict[pd.Timestamp, pd.DataFrame]]:
    frame = db.DBNStore.from_file(DATA_PATH).to_df()
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    frame = frame.tz_convert("America/New_York").sort_index()
    sessions: dict[str, dict[pd.Timestamp, pd.DataFrame]] = {"SPY": {}, "SH": {}}
    for symbol in sessions:
        symbol_frame = frame[frame.symbol == symbol]
        for session_date, bars in symbol_frame.groupby(symbol_frame.index.normalize()):
            sessions[symbol][session_date.tz_localize(None)] = bars.sort_index()
    return sessions["SPY"], sessions["SH"]


def degraded_dates() -> set[pd.Timestamp]:
    payload = json.loads(CONDITION_PATH.read_text(encoding="utf-8"))
    return {
        pd.Timestamp(row["date"])
        for row in payload["conditions"]
        if row["condition"] == "degraded"
    }


def between(bars: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return bars.between_time(start, end, inclusive="both")


def typical(bars: pd.DataFrame) -> pd.Series:
    return (bars.high + bars.low + bars.close) / 3.0


def center(bars: pd.DataFrame) -> float:
    volume = bars.volume.astype(float)
    if float(volume.sum()) <= 0:
        return math.nan
    return float((typical(bars) * volume).sum() / volume.sum())


def opening_features(bars: pd.DataFrame) -> dict[str, object] | None:
    opening = between(bars, "09:30", "09:59")
    if len(opening) != 30:
        return None
    cash_open = float(opening.iloc[0].open)
    opening_close = float(opening.iloc[-1].close)
    opening_center = center(opening)
    if not np.isfinite(opening_center):
        return None
    first = opening.iloc[:15]
    second = opening.iloc[15:]
    scar_row = opening.iloc[int(np.argmax(opening.volume.to_numpy()))]
    return {
        "opening": opening,
        "cash_open": cash_open,
        "close": opening_close,
        "center": opening_center,
        "high": float(opening.high.max()),
        "low": float(opening.low.min()),
        "a_move": float(first.iloc[-1].close - cash_open),
        "b_move": float(second.iloc[-1].close - first.iloc[-1].close),
        "a_volume": float(first.volume.sum()),
        "b_volume": float(second.volume.sum()),
        "scar": float((scar_row.high + scar_row.low + scar_row.close) / 3.0),
    }


def sign(value: float) -> int:
    return int(value > 0) - int(value < 0)


def counterauction(day: pd.Timestamp, bars: pd.DataFrame) -> Signal | None:
    f = opening_features(bars)
    if f is None:
        return None
    a_move = float(f["a_move"])
    b_move = float(f["b_move"])
    direction = sign(a_move)
    if direction == 0 or sign(b_move) != -direction:
        return None
    if sign(float(f["close"]) - float(f["cash_open"])) != direction:
        return None
    a_effort = float(f["a_volume"]) / abs(a_move)
    b_effort = float(f["b_volume"]) / abs(b_move)
    if not b_effort > a_effort:
        return None
    return Signal(
        "counterauction_effort_failure",
        day,
        direction,
        float(f["cash_open"]),
        None,
        time(10, 0),
        time(15, 30),
    )


def scar_parallax(day: pd.Timestamp, bars: pd.DataFrame) -> Signal | None:
    f = opening_features(bars)
    if f is None:
        return None
    close_side = sign(float(f["close"]) - float(f["cash_open"]))
    center_side = sign(float(f["center"]) - float(f["cash_open"]))
    scar_side = sign(float(f["scar"]) - float(f["cash_open"]))
    if close_side == 0 or center_side != close_side or scar_side != -close_side:
        return None
    return Signal(
        "opening_volume_scar_parallax",
        day,
        close_side,
        float(f["scar"]),
        None,
        time(10, 0),
        time(15, 30),
    )


def premarket_relay(day: pd.Timestamp, bars: pd.DataFrame) -> Signal | None:
    f = opening_features(bars)
    if f is None:
        return None
    premarket = between(bars, "08:00", "09:29")
    if len(premarket) < 60:
        return None
    premarket_center = center(premarket)
    direction = sign(float(f["center"]) - premarket_center)
    if direction == 0 or sign(float(f["close"]) - premarket_center) != direction:
        return None
    probed_other_side = (
        float(f["low"]) < premarket_center
        if direction == 1
        else float(f["high"]) > premarket_center
    )
    if not probed_other_side:
        return None
    return Signal(
        "premarket_false_probe_relay",
        day,
        direction,
        premarket_center,
        None,
        time(10, 0),
        time(15, 30),
    )


def excursion_transfer(day: pd.Timestamp, bars: pd.DataFrame) -> Signal | None:
    f = opening_features(bars)
    if f is None:
        return None
    up = float(f["high"]) - float(f["cash_open"])
    down = float(f["cash_open"]) - float(f["low"])
    direction = 1 if down > up else -1 if up > down else 0
    if direction == 0:
        return None
    if sign(float(f["center"]) - float(f["cash_open"])) != direction:
        return None
    if sign(float(f["close"]) - float(f["cash_open"])) != direction:
        return None
    return Signal(
        "rejected_excursion_transfer",
        day,
        direction,
        float(f["cash_open"]),
        None,
        time(10, 0),
        time(15, 30),
    )


def snapback(day: pd.Timestamp, bars: pd.DataFrame) -> Signal | None:
    f = opening_features(bars)
    if f is None:
        return None
    close_side = sign(float(f["close"]) - float(f["cash_open"]))
    center_side = sign(float(f["center"]) - float(f["cash_open"]))
    if close_side == 0 or center_side != -close_side:
        return None
    direction = -close_side
    stop = float(f["low"]) if direction == 1 else float(f["high"])
    return Signal(
        "center_close_disagreement_snapback",
        day,
        direction,
        stop,
        float(f["center"]),
        time(10, 0),
        time(12, 0),
    )


def benchmark(day: pd.Timestamp, bars: pd.DataFrame) -> Signal | None:
    f = opening_features(bars)
    if f is None:
        return None
    direction = sign(float(f["close"]) - float(f["cash_open"]))
    if direction == 0:
        return None
    if sign(float(f["center"]) - float(f["cash_open"])) != direction:
        return None
    return Signal(
        "opening_center_migration_translation",
        day,
        direction,
        float(f["center"]),
        None,
        time(10, 0),
        time(15, 30),
    )


BUILDERS: dict[str, Callable[[pd.Timestamp, pd.DataFrame], Signal | None]] = {
    "counterauction_effort_failure": counterauction,
    "opening_volume_scar_parallax": scar_parallax,
    "premarket_false_probe_relay": premarket_relay,
    "rejected_excursion_transfer": excursion_transfer,
    "center_close_disagreement_snapback": snapback,
    "opening_center_migration_translation": benchmark,
}


def timestamp_for(day: pd.Timestamp, clock: time, timezone: object) -> pd.Timestamp:
    return pd.Timestamp.combine(day.date(), clock).tz_localize(timezone)


def execution_bar(
    bars: pd.DataFrame,
    at_or_after: pd.Timestamp,
    max_minutes: int | None,
    strictly_after: bool = False,
) -> pd.Series | None:
    eligible = bars[bars.index > at_or_after] if strictly_after else bars[bars.index >= at_or_after]
    if eligible.empty:
        return None
    row = eligible.iloc[0]
    if max_minutes is not None:
        delay = (row.name - at_or_after).total_seconds() / 60.0
        if delay > max_minutes:
            return None
    return row


def simulate_signal(
    signal: Signal,
    spy: pd.DataFrame,
    execution: pd.DataFrame,
) -> dict[str, object] | None:
    timezone = spy.index.tz
    desired_entry = timestamp_for(signal.date, signal.entry_time, timezone)
    signal_entry_bar = execution_bar(spy, desired_entry, max_minutes=0)
    entry_bar = execution_bar(execution, desired_entry, max_minutes=5)
    if signal_entry_bar is None or entry_bar is None:
        return None
    signal_entry = float(signal_entry_bar.open)
    valid_stop = (
        signal.stop < signal_entry if signal.direction == 1 else signal.stop > signal_entry
    )
    if not valid_stop:
        return None

    stop_pct = abs(signal_entry - signal.stop) / signal_entry
    notional = min(ACCOUNT_CASH, RISK_BUDGET / max(stop_pct, 1e-12))
    desired_exit = timestamp_for(signal.date, signal.exit_time, timezone)
    scan = spy[(spy.index >= entry_bar.name) & (spy.index < desired_exit)]
    trigger_reason: str | None = None
    trigger_time: pd.Timestamp | None = None
    for idx, row in scan.iterrows():
        stop_hit = row.low <= signal.stop if signal.direction == 1 else row.high >= signal.stop
        target_hit = False
        if signal.target is not None:
            target_hit = (
                row.high >= signal.target
                if signal.direction == 1
                else row.low <= signal.target
            )
        if stop_hit:
            trigger_reason = "stop"
            trigger_time = idx
            break
        if target_hit:
            trigger_reason = "target"
            trigger_time = idx
            break

    if trigger_time is None:
        exit_bar = execution_bar(execution, desired_exit, max_minutes=None)
        reason = "time"
    else:
        exit_bar = execution_bar(
            execution,
            trigger_time,
            max_minutes=None,
            strictly_after=True,
        )
        reason = str(trigger_reason)
    if exit_bar is None or exit_bar.name.normalize() != entry_bar.name.normalize():
        return None

    symbol = "SPY" if signal.direction == 1 else "SH"
    return {
        "hypothesis": signal.hypothesis,
        "date": signal.date,
        "direction": "bullish" if signal.direction == 1 else "bearish",
        "symbol": symbol,
        "signal_entry": signal_entry,
        "stop": signal.stop,
        "target": signal.target,
        "notional": notional,
        "entry_time": entry_bar.name,
        "exit_time": exit_bar.name,
        "entry_delay_minutes": (entry_bar.name - desired_entry).total_seconds() / 60.0,
        "exit_delay_minutes": (
            (exit_bar.name - (trigger_time if trigger_time is not None else desired_exit))
            .total_seconds()
            / 60.0
        ),
        "entry_raw": float(entry_bar.open),
        "exit_raw": float(exit_bar.open),
        "reason": reason,
    }


def pnl_at_bps(trades: pd.DataFrame, bps_by_symbol: dict[str, float]) -> pd.Series:
    bps = trades.symbol.map(bps_by_symbol).astype(float) / 10000.0
    entry = trades.entry_raw * (1.0 + bps)
    exit_price = trades.exit_raw * (1.0 - bps)
    quantity = trades.notional / entry
    return quantity * (exit_price - entry)


def profit_factor(pnl: pd.Series) -> float:
    gains = float(pnl[pnl > 0].sum())
    losses = float(-pnl[pnl < 0].sum())
    return gains / losses if losses else math.inf


def max_drawdown(pnl: pd.Series, dates: pd.Series) -> float:
    daily = pnl.groupby(dates).sum().sort_index()
    equity = daily.cumsum()
    return float((equity - equity.cummax()).min())


def cash_account_path(trades: pd.DataFrame, pnl: pd.Series) -> dict[str, float]:
    equity = ACCOUNT_CASH
    peak = equity
    maximum_drawdown = 0.0
    for idx in trades.sort_values(["date", "entry_time"]).index:
        planned_notional = float(trades.loc[idx, "notional"])
        deployed = min(equity, planned_notional)
        trade_return = float(pnl.loc[idx]) / planned_notional
        equity += deployed * trade_return
        peak = max(peak, equity)
        maximum_drawdown = min(maximum_drawdown, equity - peak)
    return {
        "starting_equity_usd": ACCOUNT_CASH,
        "ending_equity_usd": round(equity, 4),
        "return_pct": round((equity / ACCOUNT_CASH - 1.0) * 100.0, 4),
        "maximum_drawdown_usd": round(maximum_drawdown, 4),
    }


def summary(trades: pd.DataFrame, sample: str, bps: dict[str, float]) -> dict[str, object]:
    pnl = pnl_at_bps(trades, bps)
    years = trades.date.dt.year
    directions = trades.direction
    symbols = trades.symbol
    without_five = pnl.drop(pnl.nlargest(min(5, len(pnl))).index)
    return {
        "trades": int(len(trades)),
        "trades_per_week": round(float(len(trades) / WEEKS[sample]), 3),
        "net_pnl_usd": round(float(pnl.sum()), 4),
        "mean_trade_usd": round(float(pnl.mean()), 5),
        "median_trade_usd": round(float(pnl.median()), 5),
        "win_rate": round(float((pnl > 0).mean()), 4),
        "profit_factor": round(float(profit_factor(pnl)), 4),
        "max_drawdown_usd": round(max_drawdown(pnl, trades.date), 4),
        "cash_account": cash_account_path(trades, pnl),
        "worst_fixed_notional_trade_usd": round(float(pnl.min()), 4),
        "net_without_five_best_usd": round(float(without_five.sum()), 4),
        "year_pnl_usd": {
            str(int(year)): round(float(pnl[years == year].sum()), 4)
            for year in sorted(years.unique())
        },
        "direction_pnl_usd": {
            direction: round(float(pnl[directions == direction].sum()), 4)
            for direction in sorted(directions.unique())
        },
        "symbol_pnl_usd": {
            symbol: round(float(pnl[symbols == symbol].sum()), 4)
            for symbol in sorted(symbols.unique())
        },
        "reason_counts": {
            reason: int(count)
            for reason, count in trades.reason.value_counts().sort_index().items()
        },
        "entry_delay_minutes": {
            "median": round(float(trades.entry_delay_minutes.median()), 3),
            "p95": round(float(trades.entry_delay_minutes.quantile(0.95)), 3),
            "maximum": round(float(trades.entry_delay_minutes.max()), 3),
        },
        "exit_delay_minutes": {
            "median": round(float(trades.exit_delay_minutes.median()), 3),
            "p95": round(float(trades.exit_delay_minutes.quantile(0.95)), 3),
            "maximum": round(float(trades.exit_delay_minutes.max()), 3),
        },
        "notional_usd": {
            "median": round(float(trades.notional.median()), 4),
            "minimum": round(float(trades.notional.min()), 4),
        },
    }


def development_gate(stats: dict[str, object]) -> tuple[bool, list[str]]:
    failures = []
    if float(stats["trades_per_week"]) < 2.0:
        failures.append("frequency")
    if float(stats["net_pnl_usd"]) <= 0:
        failures.append("aggregate_pnl")
    if float(stats["profit_factor"]) <= 1.0:
        failures.append("profit_factor")
    year_pnl = stats["year_pnl_usd"]
    if not isinstance(year_pnl, dict) or set(year_pnl) != {"2021", "2022", "2023"}:
        failures.append("year_coverage")
    elif any(float(value) <= 0 for value in year_pnl.values()):
        failures.append("each_year")
    direction_pnl = stats["direction_pnl_usd"]
    if not isinstance(direction_pnl, dict) or set(direction_pnl) != {"bearish", "bullish"}:
        failures.append("direction_coverage")
    elif any(float(value) <= 0 for value in direction_pnl.values()):
        failures.append("both_directions")
    return not failures, failures


def run_period(
    hypothesis: str,
    builder: Callable[[pd.Timestamp, pd.DataFrame], Signal | None],
    spy_sessions: dict[pd.Timestamp, pd.DataFrame],
    sh_sessions: dict[pd.Timestamp, pd.DataFrame],
    excluded: set[pd.Timestamp],
    years: range,
) -> pd.DataFrame:
    records = []
    for day in sorted(spy_sessions):
        if day.year not in years or day in excluded:
            continue
        spy = spy_sessions[day]
        signal = builder(day, spy)
        if signal is None:
            continue
        symbol = "SPY" if signal.direction == 1 else "SH"
        execution = spy if symbol == "SPY" else sh_sessions.get(day)
        if execution is None:
            continue
        trade = simulate_signal(signal, spy, execution)
        if trade is not None:
            records.append(trade)
    return pd.DataFrame(records)


def stress_tables(trades: pd.DataFrame, sample: str) -> dict[str, object]:
    return {
        "base": summary(trades, sample, BASE_BPS),
        "double_symbol_slippage": summary(
            trades,
            sample,
            {symbol: value * 2 for symbol, value in BASE_BPS.items()},
        ),
        "twenty_five_bps_each_fill": summary(
            trades,
            sample,
            {"SPY": 25.0, "SH": 25.0},
        ),
        "zero_slippage": summary(trades, sample, {"SPY": 0.0, "SH": 0.0}),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    spy_sessions, sh_sessions = load_data()
    excluded = degraded_dates()
    results: dict[str, object] = {
        "specification": "research_scout/spy_sh_fractional_hypotheses_prereg_v1.json",
        "data": str(DATA_PATH.relative_to(ROOT)).replace("\\", "/"),
        "excluded_degraded_dates": len(excluded),
        "base_slippage_each_fill_bps": BASE_BPS,
        "candidates": {},
    }

    for name, builder in BUILDERS.items():
        development = run_period(
            name,
            builder,
            spy_sessions,
            sh_sessions,
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
        development_stress = stress_tables(development, "development")
        passed, failures = development_gate(development_stress["base"])
        candidate: dict[str, object] = {
            "development": development_stress,
            "gate_passed": passed,
            "gate_failures": failures,
        }
        if passed or name == "opening_center_migration_translation":
            holdout = run_period(
                name,
                builder,
                spy_sessions,
                sh_sessions,
                excluded,
                range(2024, 2026),
            )
            candidate["secondary_holdout"] = (
                stress_tables(holdout, "holdout")
                if not holdout.empty
                else {"trades": 0}
            )
        else:
            candidate["secondary_holdout"] = "not_evaluated"
        results["candidates"][name] = candidate

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(results, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(results, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
