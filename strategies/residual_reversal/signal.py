"""ResidualReversalStatArb v1 signal construction.

Frozen hypothesis: recent idiosyncratic residual losers revert relative to recent
idiosyncratic residual winners after common market/factor movement is removed.
The strategy forms a daily dollar-neutral long/short portfolio using only data
available before the rebalance timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from strategies.cross_sectional import (
    empty_signal_result,
    formation_frame,
    panel_symbols,
    validate_panel_inputs,
    write_signal_details,
    write_skip,
    write_weights,
)


@dataclass(frozen=True)
class ResidualReversalParams:
    """Frozen ResidualReversalStatArb v1 hypothesis parameters."""

    regression_lookback_days: int = 60
    residual_vol_lookback_days: int = 20
    liquidity_lookback_days: int = 20
    min_history_days: int = 120
    min_regression_obs: int = 45
    min_price: float = 5.0
    min_median_dollar_volume: float = 20_000_000.0
    min_eligible_symbols: int = 60
    selection_count: int = 10
    long_gross: float = 1.0
    short_gross: float = 1.0
    max_symbol_weight: float = 0.10
    factor_symbols: tuple[str, ...] = field(default_factory=lambda: ("SPY", "QQQ", "IWM"))


def generate_signals(df: pd.DataFrame, params: ResidualReversalParams) -> pd.DataFrame:
    """Generate daily residual-reversal target portfolio weights.

    Signals at timestamp ``t`` use only ``df.iloc[:t]`` via ``formation_frame``;
    the shared backtester then applies target weights from the next bar.
    """
    validate_inputs(df)
    symbols = panel_symbols(df)
    result = empty_signal_result(df.index, symbols)
    current_weights = pd.Series(0.0, index=symbols, dtype=float)
    score_frame = residual_reversal_score_frame(df, params)

    for ts in df.index:
        result.loc[ts, ("portfolio", "is_rebalance")] = True
        formation = formation_frame(df, ts)
        if len(formation) < _minimum_lookback(params):
            write_skip(result, ts, current_weights, "insufficient_history", 0)
            continue

        scores = score_frame.loc[ts].reindex(symbols)
        eligible = _eligible_symbols(formation, scores, params)
        eligible = eligible & ~pd.Series(
            {symbol: symbol in params.factor_symbols for symbol in eligible.index},
            dtype=bool,
        )
        eligible_scores = scores[eligible].replace([np.inf, -np.inf], np.nan).dropna()
        result.loc[ts, ("portfolio", "eligible_count")] = int(len(eligible_scores))

        if len(eligible_scores) < params.min_eligible_symbols:
            write_skip(
                result,
                ts,
                current_weights,
                "insufficient_eligible_universe",
                len(eligible_scores),
            )
            continue

        next_weights, ranks, buckets = _target_weights(eligible_scores, symbols, params)
        trades = next_weights - current_weights
        write_weights(result, ts, next_weights, trades)
        write_signal_details(result, ts, symbols, scores, eligible_scores, ranks, buckets)
        current_weights = next_weights

    return result


def residual_reversal_scores(
    formation: pd.DataFrame,
    params: ResidualReversalParams,
) -> pd.Series:
    """Return latest residual z-scores for all symbols in ``formation``."""
    close = formation.xs("close", axis=1, level=1).astype(float)
    returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    factor_symbols = [symbol for symbol in params.factor_symbols if symbol in returns.columns]
    if not factor_symbols:
        return pd.Series(np.nan, index=close.columns, dtype=float)

    factor_returns = returns[factor_symbols]
    scores = pd.Series(np.nan, index=close.columns, dtype=float)
    lookback = max(params.regression_lookback_days, params.residual_vol_lookback_days)

    for symbol in close.columns:
        if symbol in factor_symbols:
            continue
        window = pd.concat([returns[symbol].rename("asset"), factor_returns], axis=1).dropna()
        window = window.tail(lookback)
        if len(window) < params.min_regression_obs:
            continue
        regression_window = window.tail(params.regression_lookback_days)
        if len(regression_window) < params.min_regression_obs:
            continue
        y = regression_window["asset"].to_numpy(dtype=float)
        x = regression_window[factor_symbols].to_numpy(dtype=float)
        design = np.column_stack([np.ones(len(x)), x])
        try:
            beta, *_ = np.linalg.lstsq(design, y, rcond=None)
        except np.linalg.LinAlgError:
            continue
        residuals = y - design @ beta
        vol_window = residuals[-params.residual_vol_lookback_days :]
        if len(vol_window) < min(params.residual_vol_lookback_days, params.min_regression_obs):
            continue
        residual_vol = float(np.std(vol_window, ddof=1))
        if not np.isfinite(residual_vol) or residual_vol <= 1e-12:
            continue
        latest_residual = float(residuals[-1])
        scores.loc[str(symbol)] = latest_residual / residual_vol

    return scores


def residual_reversal_score_frame(
    df: pd.DataFrame,
    params: ResidualReversalParams,
) -> pd.DataFrame:
    """Return residual z-scores for each rebalance timestamp without lookahead."""
    close = df.xs("close", axis=1, level=1).astype(float)
    returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    factor_symbols = [symbol for symbol in params.factor_symbols if symbol in returns.columns]
    scores = pd.DataFrame(np.nan, index=df.index, columns=close.columns, dtype=float)
    if not factor_symbols:
        return scores

    factor_values = returns[factor_symbols].to_numpy(dtype=float)
    lookback = max(params.regression_lookback_days, params.residual_vol_lookback_days)
    start_pos = _minimum_lookback(params)

    for symbol in close.columns:
        if symbol in factor_symbols:
            continue
        y_values = returns[symbol].to_numpy(dtype=float)
        for pos in range(start_pos, len(df)):
            start = max(0, pos - lookback)
            y_window = y_values[start:pos]
            x_window = factor_values[start:pos]
            valid = np.isfinite(y_window) & np.isfinite(x_window).all(axis=1)
            if int(valid.sum()) < params.min_regression_obs:
                continue
            y_valid = y_window[valid]
            x_valid = x_window[valid]
            if len(y_valid) > params.regression_lookback_days:
                y_valid = y_valid[-params.regression_lookback_days :]
                x_valid = x_valid[-params.regression_lookback_days :]
            if len(y_valid) < params.min_regression_obs:
                continue
            design = np.column_stack([np.ones(len(x_valid)), x_valid])
            try:
                beta, *_ = np.linalg.lstsq(design, y_valid, rcond=None)
            except np.linalg.LinAlgError:
                continue
            residuals = y_valid - design @ beta
            vol_window = residuals[-params.residual_vol_lookback_days :]
            if len(vol_window) < min(params.residual_vol_lookback_days, params.min_regression_obs):
                continue
            residual_vol = float(np.std(vol_window, ddof=1))
            if not np.isfinite(residual_vol) or residual_vol <= 1e-12:
                continue
            scores.iat[pos, scores.columns.get_loc(symbol)] = float(residuals[-1]) / residual_vol

    return scores


def validate_inputs(df: pd.DataFrame) -> None:
    validate_panel_inputs(df, "ResidualReversalStatArb")


def default_params() -> ResidualReversalParams:
    return ResidualReversalParams()


def sweep_grid() -> list[ResidualReversalParams]:
    """No tuning grid for v1; adjacent hypotheses become new Experiments."""
    return [default_params()]


def compact_sweep_grid() -> list[ResidualReversalParams]:
    return [default_params()]


def params_to_dict(params: ResidualReversalParams) -> dict[str, int | float | list[str]]:
    return {
        "regression_lookback_days": params.regression_lookback_days,
        "residual_vol_lookback_days": params.residual_vol_lookback_days,
        "liquidity_lookback_days": params.liquidity_lookback_days,
        "min_history_days": params.min_history_days,
        "min_regression_obs": params.min_regression_obs,
        "min_price": params.min_price,
        "min_median_dollar_volume": params.min_median_dollar_volume,
        "min_eligible_symbols": params.min_eligible_symbols,
        "selection_count": params.selection_count,
        "long_gross": params.long_gross,
        "short_gross": params.short_gross,
        "max_symbol_weight": params.max_symbol_weight,
        "factor_symbols": list(params.factor_symbols),
    }


def params_from_dict(data: dict[str, Any]) -> ResidualReversalParams:
    factor_symbols = data.get("factor_symbols", ("SPY", "QQQ", "IWM"))
    return ResidualReversalParams(
        regression_lookback_days=int(data.get("regression_lookback_days", 60)),
        residual_vol_lookback_days=int(data.get("residual_vol_lookback_days", 20)),
        liquidity_lookback_days=int(data.get("liquidity_lookback_days", 20)),
        min_history_days=int(data.get("min_history_days", 120)),
        min_regression_obs=int(data.get("min_regression_obs", 45)),
        min_price=float(data.get("min_price", 5.0)),
        min_median_dollar_volume=float(data.get("min_median_dollar_volume", 20_000_000.0)),
        min_eligible_symbols=int(data.get("min_eligible_symbols", 60)),
        selection_count=int(data.get("selection_count", 10)),
        long_gross=float(data.get("long_gross", 1.0)),
        short_gross=float(data.get("short_gross", 1.0)),
        max_symbol_weight=float(data.get("max_symbol_weight", 0.10)),
        factor_symbols=tuple(str(symbol) for symbol in factor_symbols),
    )


def warmup_bars(params: ResidualReversalParams | None = None) -> int:
    return _minimum_lookback(params or default_params())


def _minimum_lookback(params: ResidualReversalParams) -> int:
    return max(
        params.min_history_days,
        params.regression_lookback_days + 1,
        params.residual_vol_lookback_days + 1,
        params.liquidity_lookback_days,
    )


def _eligible_symbols(
    formation: pd.DataFrame,
    signal: pd.Series,
    params: ResidualReversalParams,
) -> pd.Series:
    close = formation.xs("close", axis=1, level=1)
    volume = formation.xs("volume", axis=1, level=1)
    dollar_volume = close * volume
    history_ok = close.notna().sum() >= params.min_history_days
    price_ok = close.iloc[-1] >= params.min_price
    liquidity_ok = (
        dollar_volume.tail(params.liquidity_lookback_days).median()
        >= params.min_median_dollar_volume
    )
    signal_ok = signal.replace([np.inf, -np.inf], np.nan).notna()
    return history_ok & price_ok & liquidity_ok & signal_ok


def _target_weights(
    eligible_scores: pd.Series,
    all_symbols: tuple[str, ...],
    params: ResidualReversalParams,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    ranked = eligible_scores.sort_values(ascending=True, kind="mergesort")
    selection_count = min(params.selection_count, len(ranked) // 2)
    long_symbols = tuple(str(symbol) for symbol in ranked.head(selection_count).index)
    short_symbols = tuple(str(symbol) for symbol in ranked.tail(selection_count).index)

    weights = pd.Series(0.0, index=all_symbols, dtype=float)
    if long_symbols:
        weights.loc[list(long_symbols)] = min(
            params.max_symbol_weight,
            params.long_gross / len(long_symbols),
        )
    if short_symbols:
        weights.loc[list(short_symbols)] = -min(
            params.max_symbol_weight,
            params.short_gross / len(short_symbols),
        )

    ranks = pd.Series(np.nan, index=all_symbols)
    buckets = pd.Series("", index=all_symbols, dtype=object)
    for rank, symbol in enumerate(ranked.index, start=1):
        ranks.loc[str(symbol)] = rank
    buckets.loc[list(long_symbols)] = "long"
    buckets.loc[list(short_symbols)] = "short"
    middle_symbols = {str(symbol) for symbol in ranked.index} - set(long_symbols) - set(short_symbols)
    if middle_symbols:
        buckets.loc[sorted(middle_symbols)] = "middle"
    return weights, ranks, buckets
