"""OpeningRangeBreakoutETF-v1 signal construction.

Frozen hypothesis: liquid index ETFs that close above their first-hour regular-session
range can show same-day continuation. Version 1 is long/flat only, uses 30-minute
bars, enters no earlier than the next bar after breakout confirmation, and exits
before the close.
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
class OpeningRangeBreakoutParams:
    """Frozen OpeningRangeBreakoutETF-v1 parameters."""

    bars_per_session: int = 13
    opening_range_bars: int = 2
    exit_before_close_bars: int = 1
    breakout_buffer_pct: float = 0.0
    min_price: float = 5.0
    min_opening_range_volume: float = 100_000.0
    max_gross: float = 1.0
    max_symbol_weight: float = 0.50
    allow_short: bool = False


def generate_signals(
    df: pd.DataFrame,
    params: OpeningRangeBreakoutParams,
) -> pd.DataFrame:
    """Generate long/flat opening-range breakout target weights.

    Target weights written at timestamp ``t`` are held by the shared vectorized
    backtester from ``t + 1`` because the backtester shifts weights by one bar.
    Breakout decisions therefore use the current bar close and execute no
    earlier than the next 30-minute bar.
    """

    validate_inputs(df, params)
    symbols = panel_symbols(df)
    result = empty_signal_result(df.index, symbols)
    current_weights = pd.Series(0.0, index=symbols, dtype=float)

    close = df.xs("close", axis=1, level=1).astype(float)
    high = df.xs("high", axis=1, level=1).astype(float)
    volume = df.xs("volume", axis=1, level=1).astype(float)

    for _session, session_index in _session_groups(df.index):
        triggered_symbols: set[str] = set()
        opening_high = pd.Series(np.nan, index=symbols, dtype=float)
        opening_volume = pd.Series(0.0, index=symbols, dtype=float)
        session_score = pd.Series(np.nan, index=symbols, dtype=float)

        for bar_no, ts in enumerate(session_index):
            result.loc[ts, ("portfolio", "is_rebalance")] = True
            if len(session_index) < _minimum_session_bars(params):
                write_weights(result, ts, current_weights, current_weights * 0.0)
                result.loc[ts, ("portfolio", "rebalance_skipped")] = True
                result.loc[ts, ("portfolio", "skip_reason")] = "incomplete_session"
                continue

            if bar_no < params.opening_range_bars:
                window = session_index[: bar_no + 1]
                opening_high = high.loc[window].max().reindex(symbols).astype(float)
                opening_volume = volume.loc[window].sum().reindex(symbols).astype(float)
                write_weights(result, ts, current_weights, current_weights * 0.0)
                continue

            should_flatten = bar_no >= max(0, len(session_index) - params.exit_before_close_bars - 1)
            if should_flatten:
                next_weights = pd.Series(0.0, index=symbols, dtype=float)
                trades = next_weights - current_weights
                write_weights(result, ts, next_weights, trades)
                current_weights = next_weights
                continue

            threshold = opening_high * (1.0 + params.breakout_buffer_pct)
            session_score = close.loc[ts].reindex(symbols).astype(float) / threshold - 1.0
            eligible = _eligible_symbols(close.loc[ts], opening_high, opening_volume, params)
            breakout = (close.loc[ts].reindex(symbols).astype(float) > threshold) & eligible
            for symbol in breakout[breakout].index:
                triggered_symbols.add(str(symbol))

            next_weights, ranks, buckets = _target_weights(
                tuple(sorted(triggered_symbols)),
                session_score,
                symbols,
                params,
            )
            trades = next_weights - current_weights
            active_score = session_score.loc[list(triggered_symbols)] if triggered_symbols else session_score.iloc[0:0]
            write_weights(result, ts, next_weights, trades)
            write_signal_details(result, ts, symbols, session_score, active_score, ranks, buckets)
            result.loc[ts, ("portfolio", "eligible_count")] = int(len(triggered_symbols))
            current_weights = next_weights

    return result


def validate_inputs(df: pd.DataFrame, params: OpeningRangeBreakoutParams | None = None) -> None:
    validate_panel_inputs(df, "OpeningRangeBreakout")
    if params is None:
        return
    if params.bars_per_session <= 2:
        raise ValueError("bars_per_session must be > 2")
    if params.opening_range_bars < 1:
        raise ValueError("opening_range_bars must be >= 1")
    if params.exit_before_close_bars < 1:
        raise ValueError("exit_before_close_bars must be >= 1")
    if params.opening_range_bars + params.exit_before_close_bars >= params.bars_per_session:
        raise ValueError("opening range and exit windows leave no tradable intraday bars")
    if params.breakout_buffer_pct < 0:
        raise ValueError("breakout_buffer_pct must be >= 0")
    if params.allow_short:
        raise ValueError("OpeningRangeBreakoutETF-v1 is frozen as long/flat only")


def default_params() -> OpeningRangeBreakoutParams:
    return OpeningRangeBreakoutParams()


def sweep_grid() -> list[OpeningRangeBreakoutParams]:
    """No tuning grid for v1; the candidate is source-frozen."""
    return [default_params()]


def compact_sweep_grid() -> list[OpeningRangeBreakoutParams]:
    return [default_params()]


def params_to_dict(params: OpeningRangeBreakoutParams) -> dict[str, int | float | bool]:
    return {
        "bars_per_session": params.bars_per_session,
        "opening_range_bars": params.opening_range_bars,
        "exit_before_close_bars": params.exit_before_close_bars,
        "breakout_buffer_pct": params.breakout_buffer_pct,
        "min_price": params.min_price,
        "min_opening_range_volume": params.min_opening_range_volume,
        "max_gross": params.max_gross,
        "max_symbol_weight": params.max_symbol_weight,
        "allow_short": params.allow_short,
    }


def params_from_dict(data: dict[str, Any]) -> OpeningRangeBreakoutParams:
    return OpeningRangeBreakoutParams(
        bars_per_session=int(data.get("bars_per_session", 13)),
        opening_range_bars=int(data.get("opening_range_bars", 2)),
        exit_before_close_bars=int(data.get("exit_before_close_bars", 1)),
        breakout_buffer_pct=float(data.get("breakout_buffer_pct", 0.0)),
        min_price=float(data.get("min_price", 5.0)),
        min_opening_range_volume=float(data.get("min_opening_range_volume", 100_000.0)),
        max_gross=float(data.get("max_gross", 1.0)),
        max_symbol_weight=float(data.get("max_symbol_weight", 0.50)),
        allow_short=bool(data.get("allow_short", False)),
    )


def warmup_bars(params: OpeningRangeBreakoutParams | None = None) -> int:
    params = params or default_params()
    return params.opening_range_bars


def _minimum_session_bars(params: OpeningRangeBreakoutParams) -> int:
    return params.opening_range_bars + params.exit_before_close_bars + 1


def _session_groups(index: pd.DatetimeIndex) -> list[tuple[pd.Timestamp, pd.DatetimeIndex]]:
    groups: list[tuple[pd.Timestamp, pd.DatetimeIndex]] = []
    for session, positions in pd.Series(np.arange(len(index)), index=index).groupby(index.normalize()):
        groups.append((session, index[positions.to_numpy()]))
    return groups


def _eligible_symbols(
    close: pd.Series,
    opening_high: pd.Series,
    opening_volume: pd.Series,
    params: OpeningRangeBreakoutParams,
) -> pd.Series:
    close = close.astype(float)
    price_ok = close >= params.min_price
    volume_ok = opening_volume >= params.min_opening_range_volume
    valid_range = opening_high.replace(0.0, np.nan).notna()
    valid_close = close.replace(0.0, np.nan).notna()
    return price_ok & volume_ok & valid_range & valid_close


def _target_weights(
    selected: tuple[str, ...],
    score: pd.Series,
    symbols: tuple[str, ...],
    params: OpeningRangeBreakoutParams,
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
