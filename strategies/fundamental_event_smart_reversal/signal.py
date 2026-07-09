"""FundamentalEventSmartReversal v1 signal construction.

Frozen hypothesis: extreme five-session relative moves are more likely to reverse
when no recent point-in-time SEC material filing is visible. Stateful median-cross
exits reduce boundary churn. Targets use only completed prior sessions; the shared
research backtester applies them with its one-bar execution lag.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from strategies.cross_sectional import (
    eligible_symbols,
    empty_signal_result,
    formation_frame,
    panel_symbols,
    validate_panel_inputs,
    write_signal_details,
    write_weights,
)

EVENT_FIELD = "fundamental_event"


@dataclass(frozen=True)
class FundamentalEventSmartReversalParams:
    """Frozen FundamentalEventSmartReversal v1 parameters."""

    lookback_days: int = 5
    event_veto_sessions: int = 6
    entry_fraction: float = 0.20
    exit_percentile: float = 0.50
    liquidity_lookback_days: int = 20
    min_history_days: int = 60
    min_price: float = 5.0
    min_median_dollar_volume: float = 20_000_000.0
    min_eligible_symbols: int = 100
    long_gross: float = 1.0
    short_gross: float = 1.0
    max_symbol_weight: float = 0.05
    benchmark_symbol: str = "SPY"


def generate_signals(
    df: pd.DataFrame,
    params: FundamentalEventSmartReversalParams,
) -> pd.DataFrame:
    """Generate daily event-vetoed smart-reversal target weights without lookahead."""
    validate_inputs(df)
    symbols = panel_symbols(df)
    result = empty_signal_result(df.index, symbols)
    result[("portfolio", "event_vetoed_count")] = 0
    result[("portfolio", "event_forced_exit_count")] = 0
    current_weights = pd.Series(0.0, index=symbols, dtype=float)

    score_frame = _score_frame(df, params.lookback_days)
    recent_event_frame = _recent_event_frame(df, params.event_veto_sessions)

    for ts in df.index:
        result.loc[ts, ("portfolio", "is_rebalance")] = True
        formation = formation_frame(df, ts)
        if len(formation) < _minimum_lookback(params):
            _write_flat_skip(result, ts, current_weights, "insufficient_history", 0)
            current_weights[:] = 0.0
            continue

        scores = score_frame.loc[ts].reindex(symbols)
        market_eligible = eligible_symbols(
            formation,
            min_history_days=params.min_history_days,
            min_price=params.min_price,
            liquidity_lookback_days=params.liquidity_lookback_days,
            min_median_dollar_volume=params.min_median_dollar_volume,
            signal=scores,
        )
        market_eligible &= _complete_liquidity_history(
            formation,
            symbols,
            params.liquidity_lookback_days,
        )
        if params.benchmark_symbol in market_eligible.index:
            market_eligible.loc[params.benchmark_symbol] = False

        recent_events = recent_event_frame.loc[ts].reindex(symbols).fillna(False).astype(bool)
        event_vetoed = market_eligible & recent_events
        eligible = market_eligible & ~recent_events
        eligible_scores = scores[eligible].replace([np.inf, -np.inf], np.nan).dropna()

        held = current_weights != 0.0
        result.loc[ts, ("portfolio", "eligible_count")] = int(len(eligible_scores))
        result.loc[ts, ("portfolio", "event_vetoed_count")] = int(event_vetoed.sum())
        result.loc[ts, ("portfolio", "event_forced_exit_count")] = int(
            (held & recent_events).sum()
        )

        if len(eligible_scores) < params.min_eligible_symbols:
            _write_flat_skip(
                result,
                ts,
                current_weights,
                "insufficient_eligible_universe",
                len(eligible_scores),
            )
            current_weights[:] = 0.0
            continue

        next_weights, ranks, buckets = _smart_target_weights(
            eligible_scores,
            symbols,
            current_weights,
            params,
        )
        trades = next_weights - current_weights
        write_weights(result, ts, next_weights, trades)
        write_signal_details(result, ts, symbols, scores, eligible_scores, ranks, buckets)
        current_weights = next_weights

    return result.sort_index(axis=1)


def _score_frame(df: pd.DataFrame, lookback_days: int) -> pd.DataFrame:
    close = df.xs("close", axis=1, level=1).astype(float)
    # Row t uses the five-session return ending at t-1. The shared backtester
    # shifts the target one bar, providing the source-motivated skipped session.
    return close.pct_change(lookback_days, fill_method=None).shift(1)


def _recent_event_frame(df: pd.DataFrame, sessions: int) -> pd.DataFrame:
    events = df.xs(EVENT_FIELD, axis=1, level=1).fillna(0.0).astype(bool)
    # Row t sees only completed sessions through t-1.
    visible = events.shift(1).fillna(False).astype(float)
    return visible.rolling(sessions, min_periods=1).max().fillna(0.0).astype(bool)


def _smart_target_weights(
    eligible_scores: pd.Series,
    all_symbols: tuple[str, ...],
    current_weights: pd.Series,
    params: FundamentalEventSmartReversalParams,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Apply extreme-quintile entries and median-cross stateful exits."""
    rank_frame = pd.DataFrame(
        {
            "symbol": [str(symbol) for symbol in eligible_scores.index],
            "score": eligible_scores.to_numpy(dtype=float),
        }
    ).sort_values(["score", "symbol"], ascending=[True, True], kind="mergesort")
    ranked_symbols = tuple(str(symbol) for symbol in rank_frame["symbol"])
    count = len(ranked_symbols)
    selection_count = max(1, int(np.floor(count * params.entry_fraction)))

    rank_number = pd.Series(
        np.arange(1, count + 1, dtype=float),
        index=ranked_symbols,
        dtype=float,
    )
    percentile = rank_number / float(count)
    eligible_set = set(ranked_symbols)

    retained_longs = [
        symbol
        for symbol in ranked_symbols
        if current_weights.get(symbol, 0.0) > 0.0
        and symbol in eligible_set
        and percentile.loc[symbol] <= params.exit_percentile
    ]
    retained_shorts = [
        symbol
        for symbol in reversed(ranked_symbols)
        if current_weights.get(symbol, 0.0) < 0.0
        and symbol in eligible_set
        and percentile.loc[symbol] > params.exit_percentile
    ]

    long_symbols = retained_longs.copy()
    for symbol in ranked_symbols[:selection_count]:
        if len(long_symbols) >= selection_count:
            break
        if symbol not in long_symbols:
            long_symbols.append(symbol)

    short_symbols = retained_shorts.copy()
    for symbol in reversed(ranked_symbols[-selection_count:]):
        if len(short_symbols) >= selection_count:
            break
        if symbol not in short_symbols and symbol not in long_symbols:
            short_symbols.append(symbol)

    weights = pd.Series(0.0, index=all_symbols, dtype=float)
    if long_symbols:
        long_weight = min(params.max_symbol_weight, params.long_gross / len(long_symbols))
        weights.loc[long_symbols] = long_weight
    if short_symbols:
        short_weight = min(params.max_symbol_weight, params.short_gross / len(short_symbols))
        weights.loc[short_symbols] = -short_weight

    ranks = pd.Series(np.nan, index=all_symbols, dtype=float)
    ranks.loc[list(rank_number.index)] = rank_number
    buckets = pd.Series("", index=all_symbols, dtype=object)
    buckets.loc[long_symbols] = "long"
    buckets.loc[short_symbols] = "short"
    middle = eligible_set - set(long_symbols) - set(short_symbols)
    if middle:
        buckets.loc[sorted(middle)] = "middle"
    return weights, ranks, buckets


def _complete_liquidity_history(
    formation: pd.DataFrame,
    symbols: tuple[str, ...],
    lookback_days: int,
) -> pd.Series:
    """Require a finite, positive close and volume on every liquidity session."""
    close = formation.xs("close", axis=1, level=1).reindex(columns=symbols).tail(lookback_days)
    volume = formation.xs("volume", axis=1, level=1).reindex(columns=symbols).tail(
        lookback_days
    )
    valid = (
        close.notna()
        & volume.notna()
        & np.isfinite(close)
        & np.isfinite(volume)
        & (close > 0.0)
        & (volume > 0.0)
    )
    return valid.sum(axis=0).eq(lookback_days).reindex(symbols, fill_value=False)


def validate_inputs(df: pd.DataFrame) -> None:
    validate_panel_inputs(df, "FundamentalEventSmartReversal")
    fields = {str(field) for field in df.columns.get_level_values(1)}
    if EVENT_FIELD not in fields:
        raise ValueError(f"Missing required FundamentalEventSmartReversal field: {EVENT_FIELD}")
    for symbol in panel_symbols(df):
        if EVENT_FIELD not in {str(field) for field in df[symbol].columns}:
            raise ValueError(f"FundamentalEventSmartReversal symbol {symbol} missing field: {EVENT_FIELD}")


def default_params() -> FundamentalEventSmartReversalParams:
    return FundamentalEventSmartReversalParams()


def sweep_grid() -> list[FundamentalEventSmartReversalParams]:
    """No tuning: adjacent hypotheses require new source memos and Experiments."""
    return [default_params()]


def compact_sweep_grid() -> list[FundamentalEventSmartReversalParams]:
    return [default_params()]


def params_to_dict(params: FundamentalEventSmartReversalParams) -> dict[str, Any]:
    return {
        "lookback_days": params.lookback_days,
        "event_veto_sessions": params.event_veto_sessions,
        "entry_fraction": params.entry_fraction,
        "exit_percentile": params.exit_percentile,
        "liquidity_lookback_days": params.liquidity_lookback_days,
        "min_history_days": params.min_history_days,
        "min_price": params.min_price,
        "min_median_dollar_volume": params.min_median_dollar_volume,
        "min_eligible_symbols": params.min_eligible_symbols,
        "long_gross": params.long_gross,
        "short_gross": params.short_gross,
        "max_symbol_weight": params.max_symbol_weight,
        "benchmark_symbol": params.benchmark_symbol,
    }


def params_from_dict(data: dict[str, Any]) -> FundamentalEventSmartReversalParams:
    defaults = default_params()
    return FundamentalEventSmartReversalParams(
        lookback_days=int(data.get("lookback_days", defaults.lookback_days)),
        event_veto_sessions=int(data.get("event_veto_sessions", defaults.event_veto_sessions)),
        entry_fraction=float(data.get("entry_fraction", defaults.entry_fraction)),
        exit_percentile=float(data.get("exit_percentile", defaults.exit_percentile)),
        liquidity_lookback_days=int(
            data.get("liquidity_lookback_days", defaults.liquidity_lookback_days)
        ),
        min_history_days=int(data.get("min_history_days", defaults.min_history_days)),
        min_price=float(data.get("min_price", defaults.min_price)),
        min_median_dollar_volume=float(
            data.get("min_median_dollar_volume", defaults.min_median_dollar_volume)
        ),
        min_eligible_symbols=int(
            data.get("min_eligible_symbols", defaults.min_eligible_symbols)
        ),
        long_gross=float(data.get("long_gross", defaults.long_gross)),
        short_gross=float(data.get("short_gross", defaults.short_gross)),
        max_symbol_weight=float(data.get("max_symbol_weight", defaults.max_symbol_weight)),
        benchmark_symbol=str(data.get("benchmark_symbol", defaults.benchmark_symbol)),
    )


def warmup_bars(params: FundamentalEventSmartReversalParams | None = None) -> int:
    return _minimum_lookback(params or default_params())


def _minimum_lookback(params: FundamentalEventSmartReversalParams) -> int:
    return max(
        params.min_history_days,
        params.liquidity_lookback_days,
        params.lookback_days + 1,
        params.event_veto_sessions + 1,
    )


def _write_flat_skip(
    result: pd.DataFrame,
    ts: pd.Timestamp,
    current_weights: pd.Series,
    reason: str,
    eligible_count: int,
) -> None:
    next_weights = current_weights * 0.0
    result.loc[ts, ("portfolio", "rebalance_skipped")] = True
    result.loc[ts, ("portfolio", "skip_reason")] = reason
    result.loc[ts, ("portfolio", "eligible_count")] = eligible_count
    write_weights(result, ts, next_weights, next_weights - current_weights)
