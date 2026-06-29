"""ETF time-series momentum with volatility targeting v1 signal construction.

Frozen hypothesis: liquid ETFs with positive 12-month absolute momentum
continue to trend. A monthly top-N absolute-momentum portfolio, inverse-vol
weighted and scaled toward a fixed realized-volatility target, should improve
risk-adjusted downside behavior versus fixed-gross ETF rotation.
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
    is_first_trading_session,
    panel_symbols,
    validate_panel_inputs,
    write_signal_details,
    write_skip,
    write_weights,
)

FALLBACK_SYMBOL = "SHY"


@dataclass(frozen=True)
class ETFTimeSeriesMomentumParams:
    """Frozen ETF time-series momentum v1 parameters."""

    momentum_lookback_days: int = 252
    vol_lookback_days: int = 63
    liquidity_lookback_days: int = 20
    min_history_days: int = 252
    min_price: float = 5.0
    min_median_dollar_volume: float = 5_000_000.0
    min_eligible_symbols: int = 1
    top_n: int = 3
    fallback_symbol: str = FALLBACK_SYMBOL
    target_volatility_annual: float = 0.10
    min_gross: float = 0.25
    max_gross: float = 1.0
    max_symbol_weight: float = 0.50


def generate_signals(df: pd.DataFrame, params: ETFTimeSeriesMomentumParams) -> pd.DataFrame:
    """Generate long-only ETF absolute-momentum target weights.

    Signals at a monthly rebalance use only the formation frame strictly before
    the rebalance timestamp. Target weights are consumed by the shared
    cross-sectional backtester with a one-bar shift.
    """

    validate_inputs(df)
    symbols = panel_symbols(df)
    result = empty_signal_result(df.index, symbols)
    current_weights = pd.Series(0.0, index=symbols, dtype=float)

    for ts in df.index:
        is_rebalance = is_first_trading_session(ts, df.index, "monthly")
        result.loc[ts, ("portfolio", "is_rebalance")] = is_rebalance
        if not is_rebalance:
            write_weights(result, ts, current_weights, current_weights * 0.0)
            continue

        formation = formation_frame(df, ts)
        if len(formation) < _minimum_lookback(params):
            write_skip(result, ts, current_weights, "insufficient_history", 0)
            continue

        score = _absolute_momentum_score(formation, params)
        tradable_mask = eligible_symbols(
            formation,
            min_history_days=params.min_history_days,
            min_price=params.min_price,
            liquidity_lookback_days=params.liquidity_lookback_days,
            min_median_dollar_volume=params.min_median_dollar_volume,
            signal=score,
        )
        tradable_score = score[tradable_mask]
        result.loc[ts, ("portfolio", "eligible_count")] = int(len(tradable_score))
        if len(tradable_score) < params.min_eligible_symbols:
            write_skip(
                result,
                ts,
                current_weights,
                "insufficient_eligible_universe",
                len(tradable_score),
            )
            continue

        positive = tradable_score[tradable_score > 0.0].sort_values(ascending=False, kind="mergesort")
        selected = tuple(str(symbol) for symbol in positive.head(params.top_n).index)
        bucket_label = "long"
        if not selected:
            if params.fallback_symbol in tradable_score.index:
                selected = (params.fallback_symbol,)
                bucket_label = "fallback"
            else:
                next_weights = pd.Series(0.0, index=symbols, dtype=float)
                trades = next_weights - current_weights
                ranks, buckets = _ranks_and_buckets(score, selected, symbols, bucket_label)
                write_weights(result, ts, next_weights, trades)
                write_signal_details(result, ts, symbols, score, tradable_score, ranks, buckets)
                current_weights = next_weights
                continue

        next_weights, ranks, buckets = _target_weights(
            selected,
            score,
            formation,
            symbols,
            params=params,
            bucket_label=bucket_label,
        )
        trades = next_weights - current_weights
        write_weights(result, ts, next_weights, trades)
        write_signal_details(result, ts, symbols, score, tradable_score, ranks, buckets)
        current_weights = next_weights

    return result


def validate_inputs(df: pd.DataFrame) -> None:
    validate_panel_inputs(df, "ETFTimeSeriesMomentum")
    symbols = set(panel_symbols(df))
    if FALLBACK_SYMBOL not in symbols:
        raise ValueError(f"ETFTimeSeriesMomentum missing fallback symbol: {FALLBACK_SYMBOL}")


def default_params() -> ETFTimeSeriesMomentumParams:
    return ETFTimeSeriesMomentumParams()


def sweep_grid() -> list[ETFTimeSeriesMomentumParams]:
    """Predeclared stability grid; canonical selection is not changed after results."""

    return [
        default_params(),
        ETFTimeSeriesMomentumParams(momentum_lookback_days=189, vol_lookback_days=63),
        ETFTimeSeriesMomentumParams(momentum_lookback_days=252, vol_lookback_days=126),
        ETFTimeSeriesMomentumParams(top_n=2, max_symbol_weight=0.60),
    ]


def compact_sweep_grid() -> list[ETFTimeSeriesMomentumParams]:
    return [default_params()]


def params_to_dict(params: ETFTimeSeriesMomentumParams) -> dict[str, int | float | str]:
    return {
        "momentum_lookback_days": params.momentum_lookback_days,
        "vol_lookback_days": params.vol_lookback_days,
        "liquidity_lookback_days": params.liquidity_lookback_days,
        "min_history_days": params.min_history_days,
        "min_price": params.min_price,
        "min_median_dollar_volume": params.min_median_dollar_volume,
        "min_eligible_symbols": params.min_eligible_symbols,
        "top_n": params.top_n,
        "fallback_symbol": params.fallback_symbol,
        "target_volatility_annual": params.target_volatility_annual,
        "min_gross": params.min_gross,
        "max_gross": params.max_gross,
        "max_symbol_weight": params.max_symbol_weight,
    }


def params_from_dict(data: dict[str, Any]) -> ETFTimeSeriesMomentumParams:
    return ETFTimeSeriesMomentumParams(
        momentum_lookback_days=int(data.get("momentum_lookback_days", 252)),
        vol_lookback_days=int(data.get("vol_lookback_days", 63)),
        liquidity_lookback_days=int(data.get("liquidity_lookback_days", 20)),
        min_history_days=int(data.get("min_history_days", 252)),
        min_price=float(data.get("min_price", 5.0)),
        min_median_dollar_volume=float(data.get("min_median_dollar_volume", 5_000_000.0)),
        min_eligible_symbols=int(data.get("min_eligible_symbols", 1)),
        top_n=int(data.get("top_n", 3)),
        fallback_symbol=str(data.get("fallback_symbol", FALLBACK_SYMBOL)),
        target_volatility_annual=float(data.get("target_volatility_annual", 0.10)),
        min_gross=float(data.get("min_gross", 0.25)),
        max_gross=float(data.get("max_gross", 1.0)),
        max_symbol_weight=float(data.get("max_symbol_weight", 0.50)),
    )


def _minimum_lookback(params: ETFTimeSeriesMomentumParams) -> int:
    return max(
        params.min_history_days,
        params.momentum_lookback_days + 1,
        params.vol_lookback_days + 1,
    )


def _absolute_momentum_score(
    formation: pd.DataFrame,
    params: ETFTimeSeriesMomentumParams,
) -> pd.Series:
    close = formation.xs("close", axis=1, level=1).astype(float)
    end = close.iloc[-1]
    start = close.iloc[-(params.momentum_lookback_days + 1)]
    return end / start - 1.0


def _target_weights(
    selected: tuple[str, ...],
    score: pd.Series,
    formation: pd.DataFrame,
    symbols: tuple[str, ...],
    *,
    params: ETFTimeSeriesMomentumParams,
    bucket_label: str,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    weights = pd.Series(0.0, index=symbols, dtype=float)
    if not selected:
        ranks, buckets = _ranks_and_buckets(score, selected, symbols, bucket_label)
        return weights, ranks, buckets

    asset_returns = _asset_returns(formation)
    vols = asset_returns.tail(params.vol_lookback_days).std(ddof=0).reindex(selected)
    inv_vol = (1.0 / vols.replace([np.inf, -np.inf], np.nan).clip(lower=1e-8)).dropna()
    if inv_vol.empty:
        base = pd.Series(1.0 / len(selected), index=selected, dtype=float)
    else:
        base = inv_vol / inv_vol.sum()

    base = _cap_and_normalize(base, target_gross=1.0, max_symbol_weight=params.max_symbol_weight)
    realized_vol = _portfolio_realized_vol(asset_returns, base, params.vol_lookback_days)
    target_gross = _target_gross(realized_vol, params)
    side_weights = _cap_and_normalize(
        base,
        target_gross=target_gross,
        max_symbol_weight=params.max_symbol_weight,
    )
    weights.loc[list(side_weights.index)] = side_weights
    ranks, buckets = _ranks_and_buckets(score, tuple(side_weights.index), symbols, bucket_label)
    return weights, ranks, buckets


def _asset_returns(formation: pd.DataFrame) -> pd.DataFrame:
    close = formation.xs("close", axis=1, level=1).astype(float)
    return close.pct_change(fill_method=None)


def _portfolio_realized_vol(
    returns: pd.DataFrame,
    weights: pd.Series,
    lookback_days: int,
) -> float:
    aligned = returns.tail(lookback_days).reindex(columns=weights.index).dropna(how="all")
    if aligned.empty:
        return 0.0
    portfolio_returns = aligned.fillna(0.0).dot(weights.reindex(aligned.columns).fillna(0.0))
    return float(portfolio_returns.std(ddof=0) * np.sqrt(252.0))


def _target_gross(realized_vol_annual: float, params: ETFTimeSeriesMomentumParams) -> float:
    if realized_vol_annual <= 0.0 or not np.isfinite(realized_vol_annual):
        return params.max_gross
    raw = params.target_volatility_annual / realized_vol_annual
    return float(np.clip(raw, params.min_gross, params.max_gross))


def _cap_and_normalize(
    weights: pd.Series,
    *,
    target_gross: float,
    max_symbol_weight: float,
) -> pd.Series:
    if weights.empty or target_gross <= 0.0:
        return weights * 0.0
    clean = weights.astype(float).clip(lower=0.0)
    if clean.sum() <= 0.0:
        clean = pd.Series(1.0 / len(clean), index=clean.index)
    else:
        clean = clean / clean.sum()

    target = min(float(target_gross), float(max_symbol_weight) * len(clean))
    capped = pd.Series(0.0, index=clean.index, dtype=float)
    remaining = set(clean.index)
    remaining_target = target
    while remaining:
        sub = clean.loc[sorted(remaining)]
        sub = sub / sub.sum() * remaining_target if sub.sum() > 0 else sub + remaining_target / len(sub)
        over = sub[sub > max_symbol_weight]
        if over.empty:
            capped.loc[sub.index] = sub
            break
        capped.loc[over.index] = max_symbol_weight
        remaining -= set(over.index)
        remaining_target = target - float(capped.sum())
        if remaining_target <= 1e-12:
            break
    return capped[capped > 1e-12]


def _ranks_and_buckets(
    score: pd.Series,
    selected: tuple[str, ...],
    symbols: tuple[str, ...],
    bucket_label: str,
) -> tuple[pd.Series, pd.Series]:
    ranks = pd.Series(np.nan, index=symbols)
    buckets = pd.Series("", index=symbols, dtype=object)
    ranked = score.sort_values(ascending=False, kind="mergesort")
    for rank, symbol in enumerate(ranked.index, start=1):
        ranks.loc[str(symbol)] = rank
    if selected:
        buckets.loc[list(selected)] = bucket_label
    return ranks, buckets
