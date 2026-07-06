"""VS-ICSM v1 signal construction.

Frozen hypothesis: volatility-standardized 1-hour momentum persists across the
liquid US equity cross-section because institutional parent orders are sliced
through VWAP/TWAP execution schedules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from strategies.cross_sectional import (
    empty_signal_result,
    is_first_trading_session,
    panel_symbols,
    validate_panel_inputs,
    write_signal_details,
    write_skip,
    write_weights,
)


@dataclass(frozen=True)
class VSICSMParams:
    """Frozen VS-ICSM v1 hypothesis parameters."""

    momentum_lookback_bars: int = 6
    volatility_lookback_bars: int = 13
    atr_lookback_bars: int = 13
    top_k: int = 15
    universe_size: int = 200
    transition_buffer_rank: int = 220
    min_price: float = 5.0
    price_lookback_sessions: int = 5
    liquidity_lookback_sessions: int = 60
    min_median_dollar_volume: float = 0.0
    min_hourly_volume: float = 10_000.0
    min_history_sessions: int = 60
    min_eligible_symbols: int = 15
    gross_exposure: float = 0.98
    max_position_weight: float = 0.15
    trailing_stop_atr_multiple: float = 3.0
    max_holding_bars: int = 39


def generate_signals(df: pd.DataFrame, params: VSICSMParams) -> pd.DataFrame:
    """Generate hourly long-only VS-ICSM target weights.

    Input columns must be a MultiIndex of ``(symbol, field)`` with each symbol
    carrying open/high/low/close/volume. Signals at timestamp ``t`` use data
    available at that bar close and are therefore held by the shared backtester
    from the next bar via its one-bar target-weight shift.
    """
    validate_inputs(df)
    symbols = panel_symbols(df)
    result = empty_signal_result(df.index, symbols)
    current_weights = pd.Series(0.0, index=symbols, dtype=float)
    current_universe: tuple[str, ...] = ()
    entry_bar: dict[str, int] = {}
    peak_close: dict[str, float] = {}

    close = df.xs("close", axis=1, level=1).astype(float)
    high = df.xs("high", axis=1, level=1).astype(float)
    low = df.xs("low", axis=1, level=1).astype(float)
    volume = df.xs("volume", axis=1, level=1).astype(float)
    score = _vs_icsm_score(close, params)
    atr = _atr(high, low, close, params.atr_lookback_bars)
    normalized_atr = atr / close.replace(0.0, np.nan)

    for pos, ts in enumerate(df.index):
        result.loc[ts, ("portfolio", "is_rebalance")] = True
        _update_trailing_peaks(current_weights, close.loc[ts], peak_close)

        if pos < warmup_bars(params):
            write_skip(result, ts, current_weights, "insufficient_history", 0)
            continue

        if is_first_trading_session(ts, df.index, "monthly") or not current_universe:
            prior = df.iloc[:pos]
            next_universe = _build_monthly_universe(prior, current_universe, params)
            if len(next_universe) >= params.min_eligible_symbols:
                current_universe = next_universe

        if len(current_universe) < params.min_eligible_symbols:
            write_skip(result, ts, current_weights, "insufficient_eligible_universe", 0)
            continue

        stopped = _risk_exit_symbols(
            current_weights,
            pos,
            entry_bar,
            peak_close,
            low.loc[ts],
            atr.loc[ts],
            params,
        )
        risk_adjusted_weights = _liquidate_symbols(current_weights, stopped)
        eligible_score = _eligible_scores(
            current_universe,
            score.loc[ts],
            close.loc[ts],
            volume.loc[ts],
            normalized_atr.loc[ts],
            stopped,
            params,
        )
        result.loc[ts, ("portfolio", "eligible_count")] = int(len(eligible_score))

        if len(eligible_score) < params.top_k:
            skip_weights = risk_adjusted_weights if stopped else current_weights
            write_skip(
                result,
                ts,
                skip_weights,
                "insufficient_eligible_universe",
                len(eligible_score),
            )
            if stopped:
                trades = risk_adjusted_weights - current_weights
                write_weights(result, ts, risk_adjusted_weights, trades)
                _update_holding_state(current_weights, risk_adjusted_weights, pos, entry_bar, peak_close)
                current_weights = risk_adjusted_weights
            continue

        selected = _rank_symbols(eligible_score).iloc[: params.top_k]
        next_weights, ranks, buckets = _inverse_atr_weights(
            selected.index,
            eligible_score,
            normalized_atr.loc[ts],
            symbols,
            params,
        )
        trades = next_weights - current_weights
        write_weights(result, ts, next_weights, trades)
        write_signal_details(result, ts, symbols, score.loc[ts], eligible_score, ranks, buckets)
        _update_holding_state(current_weights, next_weights, pos, entry_bar, peak_close)
        current_weights = next_weights

    return result


def validate_inputs(df: pd.DataFrame) -> None:
    validate_panel_inputs(df, "VS-ICSM")


def default_params() -> VSICSMParams:
    return VSICSMParams()


def sweep_grid() -> list[VSICSMParams]:
    """No tuning grid for v1; the report parameters are frozen."""
    return [default_params()]


def compact_sweep_grid() -> list[VSICSMParams]:
    return [default_params()]


def params_to_dict(params: VSICSMParams) -> dict[str, int | float]:
    return {
        "momentum_lookback_bars": params.momentum_lookback_bars,
        "volatility_lookback_bars": params.volatility_lookback_bars,
        "atr_lookback_bars": params.atr_lookback_bars,
        "top_k": params.top_k,
        "universe_size": params.universe_size,
        "transition_buffer_rank": params.transition_buffer_rank,
        "min_price": params.min_price,
        "price_lookback_sessions": params.price_lookback_sessions,
        "liquidity_lookback_sessions": params.liquidity_lookback_sessions,
        "min_median_dollar_volume": params.min_median_dollar_volume,
        "min_hourly_volume": params.min_hourly_volume,
        "min_history_sessions": params.min_history_sessions,
        "min_eligible_symbols": params.min_eligible_symbols,
        "gross_exposure": params.gross_exposure,
        "max_position_weight": params.max_position_weight,
        "trailing_stop_atr_multiple": params.trailing_stop_atr_multiple,
        "max_holding_bars": params.max_holding_bars,
    }


def params_from_dict(data: dict[str, Any]) -> VSICSMParams:
    return VSICSMParams(
        momentum_lookback_bars=int(data.get("momentum_lookback_bars", 6)),
        volatility_lookback_bars=int(data.get("volatility_lookback_bars", 13)),
        atr_lookback_bars=int(data.get("atr_lookback_bars", 13)),
        top_k=int(data.get("top_k", 15)),
        universe_size=int(data.get("universe_size", 200)),
        transition_buffer_rank=int(data.get("transition_buffer_rank", 220)),
        min_price=float(data.get("min_price", 5.0)),
        price_lookback_sessions=int(data.get("price_lookback_sessions", 5)),
        liquidity_lookback_sessions=int(data.get("liquidity_lookback_sessions", 60)),
        min_median_dollar_volume=float(data.get("min_median_dollar_volume", 0.0)),
        min_hourly_volume=float(data.get("min_hourly_volume", 10_000.0)),
        min_history_sessions=int(data.get("min_history_sessions", 60)),
        min_eligible_symbols=int(data.get("min_eligible_symbols", 15)),
        gross_exposure=float(data.get("gross_exposure", 0.98)),
        max_position_weight=float(data.get("max_position_weight", 0.15)),
        trailing_stop_atr_multiple=float(data.get("trailing_stop_atr_multiple", 3.0)),
        max_holding_bars=int(data.get("max_holding_bars", 39)),
    )


def warmup_bars(params: VSICSMParams) -> int:
    return max(
        params.momentum_lookback_bars + 1,
        params.volatility_lookback_bars + 1,
        params.atr_lookback_bars + 1,
        params.price_lookback_sessions,
        params.liquidity_lookback_sessions,
        params.min_history_sessions,
    )


def _vs_icsm_score(close: pd.DataFrame, params: VSICSMParams) -> pd.DataFrame:
    returns = np.log(close / close.shift(1))
    momentum = returns.rolling(params.momentum_lookback_bars).sum()
    realized_vol = returns.rolling(params.volatility_lookback_bars).std(ddof=1)
    return momentum / realized_vol.replace(0.0, np.nan)


def _atr(
    high: pd.DataFrame,
    low: pd.DataFrame,
    close: pd.DataFrame,
    lookback_bars: int,
) -> pd.DataFrame:
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        keys=["range", "high_prev", "low_prev"],
    ).groupby(level=1).max()
    return true_range.rolling(lookback_bars).mean()


def _build_monthly_universe(
    prior: pd.DataFrame,
    current_universe: tuple[str, ...],
    params: VSICSMParams,
) -> tuple[str, ...]:
    if prior.empty:
        return current_universe

    close = prior.xs("close", axis=1, level=1).astype(float)
    volume = prior.xs("volume", axis=1, level=1).astype(float)
    session_key = prior.index.normalize()
    daily_close = close.groupby(session_key).last()
    if len(daily_close) < params.min_history_sessions:
        return current_universe

    daily_dollar_volume = (close * volume).groupby(session_key).sum()
    price_avg = daily_close.tail(params.price_lookback_sessions).mean()
    median_dollar_volume = daily_dollar_volume.tail(params.liquidity_lookback_sessions).median()
    history_count = daily_close.notna().sum()
    candidates = pd.DataFrame(
        {
            "symbol": [str(symbol) for symbol in median_dollar_volume.index],
            "median_dollar_volume": median_dollar_volume.to_numpy(dtype=float),
            "price_avg": price_avg.reindex(median_dollar_volume.index).to_numpy(dtype=float),
            "history_count": history_count.reindex(median_dollar_volume.index).to_numpy(dtype=float),
        }
    )
    candidates = candidates[
        (candidates["price_avg"] >= params.min_price)
        & (candidates["median_dollar_volume"] >= params.min_median_dollar_volume)
        & (candidates["history_count"] >= params.min_history_sessions)
    ]
    if candidates.empty:
        return current_universe

    ranked = candidates.sort_values(
        ["median_dollar_volume", "symbol"],
        ascending=[False, True],
        kind="mergesort",
    )["symbol"].tolist()
    rank_map = {symbol: rank for rank, symbol in enumerate(ranked, start=1)}
    selected: list[str] = []
    for symbol in current_universe:
        if rank_map.get(symbol, params.transition_buffer_rank + 1) <= params.transition_buffer_rank:
            selected.append(symbol)
    for symbol in ranked:
        if symbol not in selected:
            selected.append(symbol)
        if len(selected) >= params.universe_size:
            break
    return tuple(selected[: params.universe_size])


def _eligible_scores(
    current_universe: tuple[str, ...],
    score: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    normalized_atr: pd.Series,
    excluded_symbols: set[str],
    params: VSICSMParams,
) -> pd.Series:
    active = [symbol for symbol in current_universe if symbol in score.index and symbol not in excluded_symbols]
    if not active:
        return pd.Series(dtype=float)
    active_score = score.reindex(active).replace([np.inf, -np.inf], np.nan)
    mask = (
        active_score.notna()
        & (close.reindex(active) >= params.min_price)
        & (volume.reindex(active) >= params.min_hourly_volume)
        & normalized_atr.reindex(active).replace([np.inf, -np.inf], np.nan).gt(0.0)
    )
    return active_score[mask]


def _rank_symbols(signal: pd.Series) -> pd.Series:
    ranked = pd.DataFrame({"symbol": signal.index.astype(str), "score": signal.to_numpy(dtype=float)})
    ranked = ranked.sort_values(["score", "symbol"], ascending=[False, True], kind="mergesort")
    return pd.Series(ranked["score"].to_numpy(dtype=float), index=ranked["symbol"].tolist())


def _inverse_atr_weights(
    selected_symbols: pd.Index,
    eligible_score: pd.Series,
    normalized_atr: pd.Series,
    all_symbols: tuple[str, ...],
    params: VSICSMParams,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    selected = [str(symbol) for symbol in selected_symbols]
    weights = pd.Series(0.0, index=all_symbols, dtype=float)
    inverse_atr = 1.0 / normalized_atr.reindex(selected).astype(float)
    raw_weights = inverse_atr / inverse_atr.sum() * params.gross_exposure
    capped_weights = raw_weights.clip(upper=params.max_position_weight)
    weights.loc[selected] = capped_weights

    ranks = pd.Series(np.nan, index=all_symbols, dtype=float)
    buckets = pd.Series("", index=all_symbols, dtype=object)
    for rank, symbol in enumerate(_rank_symbols(eligible_score).index, start=1):
        ranks.loc[str(symbol)] = rank
        buckets.loc[str(symbol)] = "long" if str(symbol) in selected else "middle"
    return weights, ranks, buckets


def _update_trailing_peaks(
    current_weights: pd.Series,
    close: pd.Series,
    peak_close: dict[str, float],
) -> None:
    held_symbols = current_weights[current_weights > 0.0].index
    for symbol in held_symbols:
        close_value = close.get(symbol, np.nan)
        if pd.isna(close_value):
            continue
        peak_close[str(symbol)] = max(float(close_value), peak_close.get(str(symbol), float(close_value)))


def _risk_exit_symbols(
    current_weights: pd.Series,
    pos: int,
    entry_bar: dict[str, int],
    peak_close: dict[str, float],
    low: pd.Series,
    atr: pd.Series,
    params: VSICSMParams,
) -> set[str]:
    stopped: set[str] = set()
    for symbol in current_weights[current_weights > 0.0].index:
        symbol_str = str(symbol)
        entry_pos = entry_bar.get(symbol_str)
        if entry_pos is not None and pos - entry_pos + 1 > params.max_holding_bars:
            stopped.add(symbol_str)
            continue
        atr_value = atr.get(symbol, np.nan)
        low_value = low.get(symbol, np.nan)
        peak_value = peak_close.get(symbol_str)
        if peak_value is None or pd.isna(atr_value) or pd.isna(low_value):
            continue
        stop_price = peak_value - params.trailing_stop_atr_multiple * float(atr_value)
        if float(low_value) < stop_price:
            stopped.add(symbol_str)
    return stopped


def _liquidate_symbols(current_weights: pd.Series, symbols: set[str]) -> pd.Series:
    next_weights = current_weights.copy()
    for symbol in symbols:
        if symbol in next_weights.index:
            next_weights.loc[symbol] = 0.0
    return next_weights


def _update_holding_state(
    current_weights: pd.Series,
    next_weights: pd.Series,
    pos: int,
    entry_bar: dict[str, int],
    peak_close: dict[str, float],
) -> None:
    for symbol in next_weights.index:
        symbol_str = str(symbol)
        was_held = current_weights.loc[symbol] > 0.0
        will_hold = next_weights.loc[symbol] > 0.0
        if not was_held and will_hold:
            entry_bar[symbol_str] = pos + 1
            peak_close.pop(symbol_str, None)
        elif not will_hold:
            entry_bar.pop(symbol_str, None)
            peak_close.pop(symbol_str, None)
