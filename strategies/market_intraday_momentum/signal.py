"""Market intraday momentum v1 signal construction.

Frozen hypothesis: for liquid US index ETFs, the first regular-session 30-minute
return predicts later-session continuation. Version 1 is long/flat only, enters
after the opening bar closes, and exits before the close with no overnight
exposure.
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
class MarketIntradayMomentumParams:
    """Frozen market intraday momentum v1 parameters."""

    bars_per_session: int = 13
    opening_signal_bars: int = 1
    exit_before_close_bars: int = 1
    min_opening_return: float = 0.0
    min_price: float = 5.0
    min_opening_bar_volume: float = 100_000.0
    max_gross: float = 1.0
    max_symbol_weight: float = 0.50
    allow_short: bool = False


def generate_signals(
    df: pd.DataFrame,
    params: MarketIntradayMomentumParams,
) -> pd.DataFrame:
    """Generate long/flat intraday momentum target weights.

    Signals at timestamp ``t`` are consumed by the shared vectorized backtester
    through a one-bar shift. Therefore weights written at the opening signal bar
    are held beginning on the next 30-minute bar; zero weights written at the
    penultimate tradable bar make the strategy flat on the closing bar.
    """

    validate_inputs(df, params)
    symbols = panel_symbols(df)
    result = empty_signal_result(df.index, symbols)
    current_weights = pd.Series(0.0, index=symbols, dtype=float)

    close = df.xs("close", axis=1, level=1).astype(float)
    open_ = df.xs("open", axis=1, level=1).astype(float)
    volume = df.xs("volume", axis=1, level=1).astype(float)

    for _session, session_index in _session_groups(df.index):
        session_symbols_seen = False
        session_score = pd.Series(np.nan, index=symbols, dtype=float)
        for bar_no, ts in enumerate(session_index):
            result.loc[ts, ("portfolio", "is_rebalance")] = True
            if bar_no == params.opening_signal_bars - 1:
                opening_return = close.loc[ts] / open_.loc[ts] - 1.0
                session_score = opening_return.reindex(symbols).astype(float)
                eligible = _eligible_symbols(open_.loc[ts], close.loc[ts], volume.loc[ts], params)
                positive = session_score[(session_score > params.min_opening_return) & eligible]
                positive = positive.sort_values(ascending=False, kind="mergesort")
                selected = tuple(str(symbol) for symbol in positive.index)
                next_weights, ranks, buckets = _target_weights(selected, session_score, symbols, params)
                trades = next_weights - current_weights
                write_weights(result, ts, next_weights, trades)
                write_signal_details(result, ts, symbols, session_score, positive, ranks, buckets)
                result.loc[ts, ("portfolio", "eligible_count")] = int(len(positive))
                current_weights = next_weights
                session_symbols_seen = True
                continue

            should_flatten = bar_no >= max(0, len(session_index) - params.exit_before_close_bars - 1)
            if should_flatten:
                next_weights = pd.Series(0.0, index=symbols, dtype=float)
                trades = next_weights - current_weights
                write_weights(result, ts, next_weights, trades)
                current_weights = next_weights
                continue

            write_weights(result, ts, current_weights, current_weights * 0.0)
            if session_symbols_seen:
                result.loc[ts, pd.IndexSlice[:, "signal_return"]] = session_score.reindex(symbols).to_numpy()

    return result


def validate_inputs(df: pd.DataFrame, params: MarketIntradayMomentumParams | None = None) -> None:
    validate_panel_inputs(df, "MarketIntradayMomentum")
    if params is None:
        return
    if params.bars_per_session <= 1:
        raise ValueError("bars_per_session must be > 1")
    if params.opening_signal_bars < 1:
        raise ValueError("opening_signal_bars must be >= 1")
    if params.exit_before_close_bars < 1:
        raise ValueError("exit_before_close_bars must be >= 1")
    if params.opening_signal_bars + params.exit_before_close_bars >= params.bars_per_session:
        raise ValueError("opening/exit windows leave no tradable intraday bars")
    if params.allow_short:
        raise ValueError("market_intraday_momentum_v1 is frozen as long/flat only")


def default_params() -> MarketIntradayMomentumParams:
    return MarketIntradayMomentumParams()


def sweep_grid() -> list[MarketIntradayMomentumParams]:
    """No tuning grid for v1; the candidate is source-frozen."""
    return [default_params()]


def compact_sweep_grid() -> list[MarketIntradayMomentumParams]:
    return [default_params()]


def params_to_dict(params: MarketIntradayMomentumParams) -> dict[str, int | float | bool]:
    return {
        "bars_per_session": params.bars_per_session,
        "opening_signal_bars": params.opening_signal_bars,
        "exit_before_close_bars": params.exit_before_close_bars,
        "min_opening_return": params.min_opening_return,
        "min_price": params.min_price,
        "min_opening_bar_volume": params.min_opening_bar_volume,
        "max_gross": params.max_gross,
        "max_symbol_weight": params.max_symbol_weight,
        "allow_short": params.allow_short,
    }


def params_from_dict(data: dict[str, Any]) -> MarketIntradayMomentumParams:
    return MarketIntradayMomentumParams(
        bars_per_session=int(data.get("bars_per_session", 13)),
        opening_signal_bars=int(data.get("opening_signal_bars", 1)),
        exit_before_close_bars=int(data.get("exit_before_close_bars", 1)),
        min_opening_return=float(data.get("min_opening_return", 0.0)),
        min_price=float(data.get("min_price", 5.0)),
        min_opening_bar_volume=float(data.get("min_opening_bar_volume", 100_000.0)),
        max_gross=float(data.get("max_gross", 1.0)),
        max_symbol_weight=float(data.get("max_symbol_weight", 0.50)),
        allow_short=bool(data.get("allow_short", False)),
    )


def warmup_bars(params: MarketIntradayMomentumParams | None = None) -> int:
    params = params or default_params()
    return params.opening_signal_bars


def _session_groups(index: pd.DatetimeIndex) -> list[tuple[pd.Timestamp, pd.DatetimeIndex]]:
    groups: list[tuple[pd.Timestamp, pd.DatetimeIndex]] = []
    for session, positions in pd.Series(np.arange(len(index)), index=index).groupby(index.normalize()):
        groups.append((session, index[positions.to_numpy()]))
    return groups


def _eligible_symbols(
    open_: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    params: MarketIntradayMomentumParams,
) -> pd.Series:
    price_ok = close >= params.min_price
    volume_ok = volume >= params.min_opening_bar_volume
    valid_bar = open_.replace(0.0, np.nan).notna() & close.replace(0.0, np.nan).notna()
    return price_ok & volume_ok & valid_bar


def _target_weights(
    selected: tuple[str, ...],
    score: pd.Series,
    symbols: tuple[str, ...],
    params: MarketIntradayMomentumParams,
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
