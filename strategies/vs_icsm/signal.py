"""VS-ICSM signal construction.

Frozen Candidate 1:
- hourly long-only cross-sectional momentum
- rank top-200 liquid names by 6-hour return sum over 13-hour return volatility
- buy top 15, inverse ATR-13 weighted to 98% gross
- trailing stop at 3x ATR-13, time stop at 39 bars
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
)


@dataclass(frozen=True)
class VSICSMParams:
    liquidity_lookback_bars: int = 390
    universe_size: int = 200
    momentum_lookback_bars: int = 6
    volatility_lookback_bars: int = 13
    atr_lookback_bars: int = 13
    k_names: int = 15
    gross_exposure: float = 0.98
    min_price: float = 5.0
    min_history_bars: int = 390
    trailing_stop_atr_multiple: float = 3.0
    time_stop_bars: int = 39


def default_params() -> VSICSMParams:
    return VSICSMParams()


def params_to_dict(params: VSICSMParams) -> dict[str, int | float]:
    return {
        "liquidity_lookback_bars": params.liquidity_lookback_bars,
        "universe_size": params.universe_size,
        "momentum_lookback_bars": params.momentum_lookback_bars,
        "volatility_lookback_bars": params.volatility_lookback_bars,
        "atr_lookback_bars": params.atr_lookback_bars,
        "k_names": params.k_names,
        "gross_exposure": params.gross_exposure,
        "min_price": params.min_price,
        "min_history_bars": params.min_history_bars,
        "trailing_stop_atr_multiple": params.trailing_stop_atr_multiple,
        "time_stop_bars": params.time_stop_bars,
    }


def params_from_dict(data: dict[str, Any]) -> VSICSMParams:
    return VSICSMParams(
        liquidity_lookback_bars=int(data.get("liquidity_lookback_bars", 390)),
        universe_size=int(data.get("universe_size", 200)),
        momentum_lookback_bars=int(data.get("momentum_lookback_bars", 6)),
        volatility_lookback_bars=int(data.get("volatility_lookback_bars", 13)),
        atr_lookback_bars=int(data.get("atr_lookback_bars", 13)),
        k_names=int(data.get("k_names", 15)),
        gross_exposure=float(data.get("gross_exposure", 0.98)),
        min_price=float(data.get("min_price", 5.0)),
        min_history_bars=int(data.get("min_history_bars", 390)),
        trailing_stop_atr_multiple=float(data.get("trailing_stop_atr_multiple", 3.0)),
        time_stop_bars=int(data.get("time_stop_bars", 39)),
    )


def sweep_grid() -> list[VSICSMParams]:
    return [default_params()]


def compact_sweep_grid() -> list[VSICSMParams]:
    return [default_params()]


def generate_signals(df: pd.DataFrame, params: VSICSMParams | None = None) -> pd.DataFrame:
    """Generate hourly target weights for VS-ICSM."""
    weights, trades, portfolio = generate_weight_signals(df, params)
    symbols = tuple(weights.columns)
    result = empty_signal_result(df.index, symbols)
    for symbol in symbols:
        result[(symbol, "weight")] = weights[symbol].to_numpy(dtype=float)
        result[(symbol, "trade")] = trades[symbol].to_numpy(dtype=float)
    result[("portfolio", "is_rebalance")] = portfolio["is_rebalance"].to_numpy(dtype=bool)
    result[("portfolio", "rebalance_skipped")] = portfolio["rebalance_skipped"].to_numpy(dtype=bool)
    result[("portfolio", "skip_reason")] = portfolio["skip_reason"].to_numpy(dtype=object)
    result[("portfolio", "eligible_count")] = portfolio["eligible_count"].to_numpy(dtype=int)
    return result


def generate_weight_signals(
    df: pd.DataFrame,
    params: VSICSMParams | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate hourly target weights, trades, and portfolio flags for VS-ICSM."""
    params = params or default_params()
    validate_inputs(df)
    symbols = panel_symbols(df)
    symbol_list = list(symbols)
    symbol_count = len(symbols)
    bar_count = len(df.index)
    close = df.xs("close", axis=1, level=1).astype(float)
    high = df.xs("high", axis=1, level=1).astype(float)
    low = df.xs("low", axis=1, level=1).astype(float)
    volume = df.xs("volume", axis=1, level=1).astype(float)
    returns = close.pct_change(fill_method=None)
    score = returns.rolling(params.momentum_lookback_bars).sum() / returns.rolling(
        params.volatility_lookback_bars
    ).std()
    atr = average_true_range(high, low, close, params.atr_lookback_bars)
    dollar_volume = close * volume
    median_dollar_volume = dollar_volume.rolling(params.liquidity_lookback_bars).median()
    history_counts = close.notna().cumsum()
    weights_out = np.zeros((bar_count, symbol_count), dtype=float)
    trades_out = np.zeros((bar_count, symbol_count), dtype=float)
    is_rebalance = np.ones(bar_count, dtype=bool)
    rebalance_skipped = np.zeros(bar_count, dtype=bool)
    skip_reason = np.full(bar_count, "", dtype=object)
    eligible_count = np.zeros(bar_count, dtype=int)

    current_weights = pd.Series(0.0, index=symbols)
    entry_price = pd.Series(np.nan, index=symbols)
    highest_close = pd.Series(np.nan, index=symbols)
    bars_held = pd.Series(0, index=symbols, dtype=int)

    for row_index, ts in enumerate(df.index):
        eligible = _eligible_symbols(close, median_dollar_volume, history_counts, score, atr, ts, params)
        eligible_count[row_index] = int(eligible.sum())
        if int(eligible.sum()) < params.k_names:
            rebalance_skipped[row_index] = True
            skip_reason[row_index] = "insufficient_eligible_universe"
            weights_out[row_index] = current_weights.reindex(symbol_list).to_numpy(dtype=float)
            continue

        ranked = score.loc[ts, eligible].sort_values(ascending=False, kind="mergesort")
        selected = list(ranked.head(params.k_names).index)
        desired = _inverse_atr_weights(atr.loc[ts, selected], symbols, params.gross_exposure)

        previous_weights = current_weights.copy()
        current_weights, entry_price, highest_close, bars_held = _apply_stops(
            desired=desired,
            current=current_weights,
            close_row=close.loc[ts],
            atr_row=atr.loc[ts],
            entry_price=entry_price,
            highest_close=highest_close,
            bars_held=bars_held,
            params=params,
        )
        trades = current_weights - previous_weights
        weights_out[row_index] = current_weights.reindex(symbol_list).to_numpy(dtype=float)
        trades_out[row_index] = trades.reindex(symbol_list).fillna(0.0).to_numpy(dtype=float)
    weights = pd.DataFrame(weights_out, index=df.index, columns=symbols)
    trades = pd.DataFrame(trades_out, index=df.index, columns=symbols)
    portfolio = pd.DataFrame(
        {
            "is_rebalance": is_rebalance,
            "rebalance_skipped": rebalance_skipped,
            "skip_reason": skip_reason,
            "eligible_count": eligible_count,
        },
        index=df.index,
    )
    return weights, trades, portfolio


def validate_inputs(df: pd.DataFrame) -> None:
    validate_panel_inputs(df, "VS-ICSM")


def average_true_range(
    high: pd.DataFrame,
    low: pd.DataFrame,
    close: pd.DataFrame,
    window: int,
) -> pd.DataFrame:
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=0,
        keys=("hl", "hc", "lc"),
    ).groupby(level=1).max()
    true_range.index = high.index
    return true_range.rolling(window).mean()


def _eligible_symbols(
    close: pd.DataFrame,
    median_dollar_volume: pd.DataFrame,
    history_counts: pd.DataFrame,
    score: pd.DataFrame,
    atr: pd.DataFrame,
    ts: pd.Timestamp,
    params: VSICSMParams,
) -> pd.Series:
    loc = close.index.get_loc(ts)
    if not isinstance(loc, int):
        raise ValueError("VS-ICSM index must not contain duplicate timestamps")
    if loc < params.min_history_bars:
        return pd.Series(False, index=close.columns)
    history_ok = history_counts.loc[ts] >= params.min_history_bars
    price_ok = close.loc[ts] >= params.min_price
    liquid = median_dollar_volume.loc[ts].rank(
        ascending=False,
        method="first",
    ) <= params.universe_size
    valid_signal = score.loc[ts].replace([np.inf, -np.inf], np.nan).notna()
    valid_atr = atr.loc[ts].replace([np.inf, -np.inf], np.nan).gt(0)
    return history_ok & price_ok & liquid & valid_signal & valid_atr


def _inverse_atr_weights(
    selected_atr: pd.Series,
    symbols: tuple[str, ...],
    gross_exposure: float,
) -> pd.Series:
    weights = pd.Series(0.0, index=symbols)
    inv = 1.0 / selected_atr.replace(0.0, np.nan).dropna()
    if inv.empty:
        return weights
    weights.loc[list(inv.index)] = gross_exposure * inv / inv.sum()
    return weights


def _apply_stops(
    *,
    desired: pd.Series,
    current: pd.Series,
    close_row: pd.Series,
    atr_row: pd.Series,
    entry_price: pd.Series,
    highest_close: pd.Series,
    bars_held: pd.Series,
    params: VSICSMParams,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    next_weights = desired.copy()
    for symbol in current.index:
        if current.loc[symbol] > 0:
            bars_held.loc[symbol] += 1
            highest_close.loc[symbol] = max(highest_close.loc[symbol], close_row.loc[symbol])
            trail = highest_close.loc[symbol] - params.trailing_stop_atr_multiple * atr_row.loc[symbol]
            stop_hit = close_row.loc[symbol] <= trail
            time_hit = bars_held.loc[symbol] >= params.time_stop_bars
            if stop_hit or time_hit:
                next_weights.loc[symbol] = 0.0
        if current.loc[symbol] <= 0 and next_weights.loc[symbol] > 0:
            entry_price.loc[symbol] = close_row.loc[symbol]
            highest_close.loc[symbol] = close_row.loc[symbol]
            bars_held.loc[symbol] = 0
        elif next_weights.loc[symbol] <= 0:
            entry_price.loc[symbol] = np.nan
            highest_close.loc[symbol] = np.nan
            bars_held.loc[symbol] = 0
    return next_weights, entry_price, highest_close, bars_held
