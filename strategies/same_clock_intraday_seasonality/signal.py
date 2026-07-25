"""SameClockIntradaySeasonalityETF-v1 signal construction.

Frozen hypothesis: an ETF's recent returns in the same intraday clock slot can
forecast returns in that slot on later sessions. Version 1 is long/flat only,
uses prior 20 completed sessions, skips the opening slot because open execution
is not modeled, and exits before close.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from strategies.cross_sectional import (
    empty_signal_result,
    panel_symbols,
    validate_panel_inputs,
    write_signal_details,
    write_weights,
)


@dataclass(frozen=True)
class SameClockIntradaySeasonalityParams:
    """Frozen SameClockIntradaySeasonalityETF-v1 parameters."""

    bars_per_session: int = 13
    lookback_sessions: int = 20
    min_same_clock_mean_return: float = 0.0
    skip_opening_bars: int = 1
    exit_before_close_bars: int = 1
    min_price: float = 5.0
    min_bar_volume: float = 100_000.0
    max_gross: float = 1.0
    max_symbol_weight: float = 0.50
    allow_short: bool = False


def generate_signals(
    df: pd.DataFrame,
    params: SameClockIntradaySeasonalityParams,
) -> pd.DataFrame:
    """Generate long/flat same-clock intraday seasonality target weights.

    Target weights written at timestamp ``t`` are held by the shared vectorized
    backtester from ``t + 1``. The decision for slot ``k`` is therefore written
    at slot ``k - 1`` using only prior completed sessions' returns for slot ``k``.
    """

    validate_inputs(df, params)
    symbols = panel_symbols(df)
    result = empty_signal_result(df.index, symbols)
    current_weights = pd.Series(0.0, index=symbols, dtype=float)

    close = df.xs("close", axis=1, level=1).astype(float)
    volume = df.xs("volume", axis=1, level=1).astype(float)
    history: dict[int, list[pd.Series]] = {slot: [] for slot in range(params.bars_per_session)}

    for _session, session_index in _session_groups(df.index):
        if len(session_index) < _minimum_session_bars(params):
            for ts in session_index:
                result.loc[ts, ("portfolio", "is_rebalance")] = True
                result.loc[ts, ("portfolio", "rebalance_skipped")] = True
                result.loc[ts, ("portfolio", "skip_reason")] = "incomplete_session"
                write_weights(result, ts, current_weights * 0.0, current_weights * -1.0)
                current_weights = current_weights * 0.0
            continue

        session_slot_returns = _session_slot_returns(close, session_index, symbols)
        for bar_no, ts in enumerate(session_index):
            result.loc[ts, ("portfolio", "is_rebalance")] = True
            target_bar_no = bar_no + 1
            should_flatten = target_bar_no >= len(session_index) - params.exit_before_close_bars
            if target_bar_no < params.skip_opening_bars or should_flatten:
                next_weights = pd.Series(0.0, index=symbols, dtype=float)
                trades = next_weights - current_weights
                write_weights(result, ts, next_weights, trades)
                current_weights = next_weights
                continue

            prior_slot_returns = history.get(target_bar_no, [])
            if len(prior_slot_returns) < params.lookback_sessions:
                next_weights = pd.Series(0.0, index=symbols, dtype=float)
                trades = next_weights - current_weights
                write_weights(result, ts, next_weights, trades)
                result.loc[ts, ("portfolio", "rebalance_skipped")] = True
                result.loc[ts, ("portfolio", "skip_reason")] = "insufficient_same_clock_history"
                current_weights = next_weights
                continue

            same_clock_mean = pd.concat(prior_slot_returns[-params.lookback_sessions :], axis=1).mean(axis=1)
            same_clock_mean = same_clock_mean.reindex(symbols).astype(float)
            eligible = _eligible_symbols(close.loc[ts], volume.loc[ts], params)
            positive = same_clock_mean[(same_clock_mean > params.min_same_clock_mean_return) & eligible]
            positive = positive.sort_values(ascending=False, kind="mergesort")
            selected = tuple(str(symbol) for symbol in positive.index)
            next_weights, ranks, buckets = _target_weights(selected, same_clock_mean, symbols, params)
            trades = next_weights - current_weights
            write_weights(result, ts, next_weights, trades)
            write_signal_details(result, ts, symbols, same_clock_mean, positive, ranks, buckets)
            result.loc[ts, ("portfolio", "eligible_count")] = int(len(positive))
            current_weights = next_weights

        for slot_no, slot_return in session_slot_returns.items():
            history.setdefault(slot_no, []).append(slot_return)

    return result


def validate_inputs(df: pd.DataFrame, params: SameClockIntradaySeasonalityParams | None = None) -> None:
    validate_panel_inputs(df, "SameClockIntradaySeasonality")
    if params is None:
        return
    if params.bars_per_session <= 2:
        raise ValueError("bars_per_session must be > 2")
    if params.lookback_sessions < 1:
        raise ValueError("lookback_sessions must be >= 1")
    if params.skip_opening_bars < 1:
        raise ValueError("skip_opening_bars must be >= 1")
    if params.exit_before_close_bars < 1:
        raise ValueError("exit_before_close_bars must be >= 1")
    if params.skip_opening_bars + params.exit_before_close_bars >= params.bars_per_session:
        raise ValueError("opening/exit skips leave no tradable intraday slots")
    if params.allow_short:
        raise ValueError("SameClockIntradaySeasonalityETF-v1 is frozen as long/flat only")


def default_params() -> SameClockIntradaySeasonalityParams:
    return SameClockIntradaySeasonalityParams()


def sweep_grid() -> list[SameClockIntradaySeasonalityParams]:
    """No tuning grid for v1; the candidate is source-frozen."""
    return [default_params()]


def compact_sweep_grid() -> list[SameClockIntradaySeasonalityParams]:
    return [default_params()]


def params_to_dict(params: SameClockIntradaySeasonalityParams) -> dict[str, int | float | bool]:
    return {
        "bars_per_session": params.bars_per_session,
        "lookback_sessions": params.lookback_sessions,
        "min_same_clock_mean_return": params.min_same_clock_mean_return,
        "skip_opening_bars": params.skip_opening_bars,
        "exit_before_close_bars": params.exit_before_close_bars,
        "min_price": params.min_price,
        "min_bar_volume": params.min_bar_volume,
        "max_gross": params.max_gross,
        "max_symbol_weight": params.max_symbol_weight,
        "allow_short": params.allow_short,
    }


def params_from_dict(data: dict[str, Any]) -> SameClockIntradaySeasonalityParams:
    return SameClockIntradaySeasonalityParams(
        bars_per_session=int(data.get("bars_per_session", 13)),
        lookback_sessions=int(data.get("lookback_sessions", 20)),
        min_same_clock_mean_return=float(data.get("min_same_clock_mean_return", 0.0)),
        skip_opening_bars=int(data.get("skip_opening_bars", 1)),
        exit_before_close_bars=int(data.get("exit_before_close_bars", 1)),
        min_price=float(data.get("min_price", 5.0)),
        min_bar_volume=float(data.get("min_bar_volume", 100_000.0)),
        max_gross=float(data.get("max_gross", 1.0)),
        max_symbol_weight=float(data.get("max_symbol_weight", 0.50)),
        allow_short=bool(data.get("allow_short", False)),
    )


def warmup_bars(params: SameClockIntradaySeasonalityParams | None = None) -> int:
    params = params or default_params()
    return params.lookback_sessions * params.bars_per_session


def _minimum_session_bars(params: SameClockIntradaySeasonalityParams) -> int:
    return params.skip_opening_bars + params.exit_before_close_bars + 1


def _session_groups(index: pd.DatetimeIndex) -> list[tuple[pd.Timestamp, pd.DatetimeIndex]]:
    groups: list[tuple[pd.Timestamp, pd.DatetimeIndex]] = []
    for session, positions in pd.Series(np.arange(len(index)), index=index).groupby(index.normalize()):
        groups.append((session, index[positions.to_numpy()]))
    return groups


def _session_slot_returns(
    close: pd.DataFrame,
    session_index: pd.DatetimeIndex,
    symbols: tuple[str, ...],
) -> dict[int, pd.Series]:
    returns: dict[int, pd.Series] = {}
    for slot_no in range(1, len(session_index)):
        current_ts = session_index[slot_no]
        previous_ts = session_index[slot_no - 1]
        slot_return = close.loc[current_ts].reindex(symbols) / close.loc[previous_ts].reindex(symbols) - 1.0
        returns[slot_no] = slot_return.astype(float)
    return returns


def _eligible_symbols(
    close: pd.Series,
    volume: pd.Series,
    params: SameClockIntradaySeasonalityParams,
) -> pd.Series:
    close = close.astype(float)
    price_ok = close >= params.min_price
    volume_ok = volume >= params.min_bar_volume
    valid_close = close.replace(0.0, np.nan).notna()
    return price_ok & volume_ok & valid_close


def _target_weights(
    selected: tuple[str, ...],
    score: pd.Series,
    symbols: tuple[str, ...],
    params: SameClockIntradaySeasonalityParams,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    weights = pd.Series(0.0, index=symbols, dtype=float)
    ranks = pd.Series(np.nan, index=symbols)
    buckets = pd.Series("", index=symbols, dtype=object)
    ranked = score.sort_values(ascending=False, kind="mergesort")
    for rank, symbol in enumerate(ranked.index, start=1):
        ranks.loc[str(symbol)] = rank
    if not selected:
        return weights, ranks, buckets
    target_gross = min(params.max_gross, params.max_symbol_weight * len(selected))
    weight = target_gross / len(selected)
    weights.loc[list(selected)] = weight
    buckets.loc[list(selected)] = "long"
    return weights, ranks, buckets
