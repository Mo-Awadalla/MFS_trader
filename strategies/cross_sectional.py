"""Shared helpers for cross-sectional strategy templates."""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

SYMBOL_FIELD_NAMES = ("weight", "signal_return", "rank", "bucket", "eligible", "trade")
PORTFOLIO_FIELD_NAMES = ("is_rebalance", "rebalance_skipped", "skip_reason", "eligible_count")
RebalanceFrequency = Literal["weekly", "monthly"]


def validate_panel_inputs(df: pd.DataFrame, strategy_name: str) -> None:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(f"{strategy_name} input must have a DatetimeIndex")
    if not isinstance(df.columns, pd.MultiIndex):
        raise ValueError(f"{strategy_name} input columns must be a MultiIndex of (symbol, field)")
    if df.columns.nlevels != 2:
        raise ValueError(f"{strategy_name} input columns must have exactly two levels: symbol, field")

    fields = {str(field) for field in df.columns.get_level_values(1)}
    required = {"open", "high", "low", "close", "volume"}
    missing = required - fields
    if missing:
        raise ValueError(f"Missing required {strategy_name} OHLCV fields: {sorted(missing)}")

    for symbol in df.columns.get_level_values(0).unique():
        symbol_fields = {str(field) for field in df[symbol].columns}
        missing_for_symbol = required - symbol_fields
        if missing_for_symbol:
            raise ValueError(
                f"{strategy_name} symbol {symbol} missing fields: {sorted(missing_for_symbol)}"
            )


def panel_symbols(df: pd.DataFrame) -> tuple[str, ...]:
    return tuple(sorted(str(symbol) for symbol in df.columns.get_level_values(0).unique()))


def empty_signal_result(index: pd.DatetimeIndex, symbols: tuple[str, ...]) -> pd.DataFrame:
    symbol_columns = pd.MultiIndex.from_product(
        [symbols, SYMBOL_FIELD_NAMES],
        names=["symbol", "field"],
    )
    portfolio_columns = pd.MultiIndex.from_product(
        [["portfolio"], PORTFOLIO_FIELD_NAMES],
        names=["symbol", "field"],
    )
    result = pd.DataFrame(index=index, columns=symbol_columns.append(portfolio_columns))
    result.loc[:, pd.IndexSlice[:, "weight"]] = 0.0
    result.loc[:, pd.IndexSlice[:, "trade"]] = 0.0
    result.loc[:, pd.IndexSlice[:, "eligible"]] = False
    result.loc[:, ("portfolio", "is_rebalance")] = False
    result.loc[:, ("portfolio", "rebalance_skipped")] = False
    result.loc[:, ("portfolio", "skip_reason")] = ""
    result.loc[:, ("portfolio", "eligible_count")] = 0
    return result


def is_first_trading_session(
    ts: pd.Timestamp,
    index: pd.DatetimeIndex,
    frequency: RebalanceFrequency,
) -> bool:
    pos = index.get_loc(ts)
    if not isinstance(pos, int):
        raise ValueError("Cross-sectional index must not contain duplicate timestamps")
    if pos == 0:
        return True
    previous = index[pos - 1]
    if frequency == "weekly":
        return _week_key(ts) != _week_key(previous)
    if frequency == "monthly":
        return (ts.year, ts.month) != (previous.year, previous.month)
    raise ValueError(f"Unsupported rebalance frequency: {frequency}")


def formation_frame(df: pd.DataFrame, ts: pd.Timestamp) -> pd.DataFrame:
    pos = df.index.get_loc(ts)
    if not isinstance(pos, int):
        raise ValueError("Cross-sectional index must not contain duplicate timestamps")
    return df.iloc[:pos]


def eligible_symbols(
    formation: pd.DataFrame,
    *,
    min_history_days: int,
    min_price: float,
    liquidity_lookback_days: int,
    min_median_dollar_volume: float,
    signal: pd.Series,
) -> pd.Series:
    close = formation.xs("close", axis=1, level=1)
    volume = formation.xs("volume", axis=1, level=1)
    dollar_volume = close * volume
    history_ok = close.notna().sum() >= min_history_days
    price_ok = close.iloc[-1] >= min_price
    liquidity_ok = (
        dollar_volume.tail(liquidity_lookback_days).median()
        >= min_median_dollar_volume
    )
    signal_ok = signal.replace([np.inf, -np.inf], np.nan).notna()
    return history_ok & price_ok & liquidity_ok & signal_ok


def quartile_target_weights(
    signal: pd.Series,
    all_symbols: tuple[str, ...],
    *,
    ranking: Literal["ascending", "descending"],
    long_gross: float,
    short_gross: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    rank_frame = pd.DataFrame(
        {
            "symbol": [str(symbol) for symbol in signal.index],
            "signal": signal.to_numpy(),
        }
    ).sort_values(
        ["signal", "symbol"],
        ascending=[ranking == "ascending", True],
        kind="mergesort",
    )
    ranked_symbols = rank_frame["symbol"].to_numpy()
    buckets = np.array_split(ranked_symbols, 4)
    long_symbols = tuple(str(symbol) for symbol in buckets[0])
    short_symbols = tuple(str(symbol) for symbol in buckets[-1])

    weights = pd.Series(0.0, index=all_symbols)
    if long_symbols:
        weights.loc[list(long_symbols)] = long_gross / len(long_symbols)
    if short_symbols:
        weights.loc[list(short_symbols)] = -short_gross / len(short_symbols)

    ranks = pd.Series(np.nan, index=all_symbols)
    bucket_labels = pd.Series("", index=all_symbols, dtype=object)
    for rank, symbol in enumerate(ranked_symbols, start=1):
        ranks.loc[str(symbol)] = rank
    bucket_labels.loc[list(long_symbols)] = "long"
    bucket_labels.loc[list(short_symbols)] = "short"
    middle_symbols = {str(symbol) for symbol in ranked_symbols} - set(long_symbols) - set(short_symbols)
    if middle_symbols:
        bucket_labels.loc[sorted(middle_symbols)] = "middle"
    return weights, ranks, bucket_labels


def write_weights(
    result: pd.DataFrame,
    ts: pd.Timestamp,
    weights: pd.Series,
    trades: pd.Series,
) -> None:
    for symbol, weight in weights.items():
        result.loc[ts, (symbol, "weight")] = float(weight)
        result.loc[ts, (symbol, "trade")] = float(trades.loc[symbol])


def write_skip(
    result: pd.DataFrame,
    ts: pd.Timestamp,
    current_weights: pd.Series,
    reason: str,
    eligible_count: int,
) -> None:
    result.loc[ts, ("portfolio", "rebalance_skipped")] = True
    result.loc[ts, ("portfolio", "skip_reason")] = reason
    result.loc[ts, ("portfolio", "eligible_count")] = eligible_count
    write_weights(result, ts, current_weights, current_weights * 0.0)


def write_signal_details(
    result: pd.DataFrame,
    ts: pd.Timestamp,
    symbols: tuple[str, ...],
    signal: pd.Series,
    eligible_signal: pd.Series,
    ranks: pd.Series,
    buckets: pd.Series,
) -> None:
    for symbol in symbols:
        result.loc[ts, (symbol, "signal_return")] = signal.get(symbol, np.nan)
        result.loc[ts, (symbol, "eligible")] = bool(symbol in eligible_signal.index)
        result.loc[ts, (symbol, "rank")] = ranks.get(symbol, np.nan)
        result.loc[ts, (symbol, "bucket")] = buckets.get(symbol, "")


def _week_key(ts: pd.Timestamp) -> tuple[int, int]:
    calendar = ts.date().isocalendar()
    return int(calendar.year), int(calendar.week)
