"""ETF tactical absolute/relative momentum v1 signal construction.

Canonical hypothesis: liquid ETFs with positive medium-term absolute momentum
continue to outperform, while a simple SPY risk-off filter shifts selection away
from equity beta and into defensive ETFs.
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

RISK_ASSETS = ("SPY", "QQQ", "IWM")
DEFENSIVE_ASSETS = ("IEF", "GLD", "SHY")
CASH_PROXY = "SHY"


@dataclass(frozen=True)
class ETFTacticalParams:
    """Frozen ETF tactical momentum v1 parameters."""

    short_lookback_days: int = 126
    long_lookback_days: int = 252
    trend_ma_days: int = 200
    vol_lookback_days: int = 63
    liquidity_lookback_days: int = 20
    min_history_days: int = 252
    min_price: float = 5.0
    min_median_dollar_volume: float = 5_000_000.0
    min_eligible_symbols: int = 4
    top_n: int = 3
    defensive_top_n: int = 2
    long_gross: float = 1.0
    max_symbol_weight: float = 0.60


def generate_signals(df: pd.DataFrame, params: ETFTacticalParams) -> pd.DataFrame:
    """Generate long-only ETF tactical target weights.

    Formation uses data strictly before the rebalance date. The strategy is
    monthly, long-only, and never shorts. If no positive-momentum assets are
    available, it falls back to the cash proxy if eligible.
    """

    validate_inputs(df)
    symbols = panel_symbols(df)
    result = empty_signal_result(df.index, symbols)
    current_weights = pd.Series(0.0, index=symbols)

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

        score = _momentum_score(formation, params)
        eligible = eligible_symbols(
            formation,
            min_history_days=params.min_history_days,
            min_price=params.min_price,
            liquidity_lookback_days=params.liquidity_lookback_days,
            min_median_dollar_volume=params.min_median_dollar_volume,
            signal=score,
        )
        eligible_score = score[eligible]
        result.loc[ts, ("portfolio", "eligible_count")] = int(len(eligible_score))
        if len(eligible_score) < params.min_eligible_symbols:
            write_skip(
                result,
                ts,
                current_weights,
                "insufficient_eligible_universe",
                len(eligible_score),
            )
            continue

        risk_off = _risk_off(formation, params)
        allowed = _allowed_symbols(symbols, risk_off)
        candidate_score = eligible_score[eligible_score.index.isin(allowed)]
        positive = candidate_score[candidate_score > 0.0].sort_values(ascending=False, kind="mergesort")
        top_n = params.defensive_top_n if risk_off else params.top_n
        selected = tuple(str(symbol) for symbol in positive.head(top_n).index)
        if not selected and CASH_PROXY in eligible_score.index:
            selected = (CASH_PROXY,)

        next_weights, ranks, buckets = _target_weights(
            selected,
            score,
            formation,
            symbols,
            params=params,
        )
        trades = next_weights - current_weights
        write_weights(result, ts, next_weights, trades)
        write_signal_details(result, ts, symbols, score, eligible_score, ranks, buckets)
        current_weights = next_weights

    return result


def validate_inputs(df: pd.DataFrame) -> None:
    validate_panel_inputs(df, "ETFTacticalMomentum")
    symbols = set(panel_symbols(df))
    missing = {"SPY", CASH_PROXY} - symbols
    if missing:
        raise ValueError(f"ETFTacticalMomentum missing required symbols: {sorted(missing)}")


def default_params() -> ETFTacticalParams:
    return ETFTacticalParams()


def sweep_grid() -> list[ETFTacticalParams]:
    """Small predeclared stability grid; not selected after results."""

    return [
        default_params(),
        ETFTacticalParams(short_lookback_days=84, long_lookback_days=252),
        ETFTacticalParams(short_lookback_days=126, long_lookback_days=189),
        ETFTacticalParams(top_n=2, defensive_top_n=2),
    ]


def compact_sweep_grid() -> list[ETFTacticalParams]:
    return [default_params()]


def params_to_dict(params: ETFTacticalParams) -> dict[str, int | float]:
    return {
        "short_lookback_days": params.short_lookback_days,
        "long_lookback_days": params.long_lookback_days,
        "trend_ma_days": params.trend_ma_days,
        "vol_lookback_days": params.vol_lookback_days,
        "liquidity_lookback_days": params.liquidity_lookback_days,
        "min_history_days": params.min_history_days,
        "min_price": params.min_price,
        "min_median_dollar_volume": params.min_median_dollar_volume,
        "min_eligible_symbols": params.min_eligible_symbols,
        "top_n": params.top_n,
        "defensive_top_n": params.defensive_top_n,
        "long_gross": params.long_gross,
        "max_symbol_weight": params.max_symbol_weight,
    }


def params_from_dict(data: dict[str, Any]) -> ETFTacticalParams:
    return ETFTacticalParams(
        short_lookback_days=int(data.get("short_lookback_days", 126)),
        long_lookback_days=int(data.get("long_lookback_days", 252)),
        trend_ma_days=int(data.get("trend_ma_days", 200)),
        vol_lookback_days=int(data.get("vol_lookback_days", 63)),
        liquidity_lookback_days=int(data.get("liquidity_lookback_days", 20)),
        min_history_days=int(data.get("min_history_days", 252)),
        min_price=float(data.get("min_price", 5.0)),
        min_median_dollar_volume=float(data.get("min_median_dollar_volume", 5_000_000.0)),
        min_eligible_symbols=int(data.get("min_eligible_symbols", 4)),
        top_n=int(data.get("top_n", 3)),
        defensive_top_n=int(data.get("defensive_top_n", 2)),
        long_gross=float(data.get("long_gross", 1.0)),
        max_symbol_weight=float(data.get("max_symbol_weight", 0.60)),
    )


def _minimum_lookback(params: ETFTacticalParams) -> int:
    return max(
        params.min_history_days,
        params.long_lookback_days + 1,
        params.trend_ma_days,
        params.vol_lookback_days + 1,
    )


def _momentum_score(formation: pd.DataFrame, params: ETFTacticalParams) -> pd.Series:
    close = formation.xs("close", axis=1, level=1).astype(float)
    short_return = close.iloc[-1] / close.iloc[-(params.short_lookback_days + 1)] - 1.0
    long_return = close.iloc[-1] / close.iloc[-(params.long_lookback_days + 1)] - 1.0
    return 0.5 * short_return + 0.5 * long_return


def _risk_off(formation: pd.DataFrame, params: ETFTacticalParams) -> bool:
    close = formation.xs("close", axis=1, level=1).astype(float)
    spy = close["SPY"].dropna()
    if len(spy) < params.trend_ma_days:
        return False
    return bool(float(spy.iloc[-1]) < float(spy.tail(params.trend_ma_days).mean()))


def _allowed_symbols(symbols: tuple[str, ...], risk_off: bool) -> tuple[str, ...]:
    if risk_off:
        defensive = set(DEFENSIVE_ASSETS)
        return tuple(symbol for symbol in symbols if symbol in defensive)
    return symbols


def _target_weights(
    selected: tuple[str, ...],
    score: pd.Series,
    formation: pd.DataFrame,
    symbols: tuple[str, ...],
    *,
    params: ETFTacticalParams,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    weights = pd.Series(0.0, index=symbols)
    ranks = pd.Series(np.nan, index=symbols)
    buckets = pd.Series("", index=symbols, dtype=object)
    ranked = score.sort_values(ascending=False, kind="mergesort")
    for rank, symbol in enumerate(ranked.index, start=1):
        ranks.loc[str(symbol)] = rank
    if not selected:
        return weights, ranks, buckets

    vols = _volatility(formation, params).reindex(selected).replace([np.inf, -np.inf], np.nan)
    inv_vol = (1.0 / vols.clip(lower=1e-8)).dropna()
    if inv_vol.empty:
        side_weights = pd.Series(1.0 / len(selected), index=selected)
    else:
        side_weights = inv_vol / inv_vol.sum()
    side_weights = (side_weights * params.long_gross).clip(upper=params.max_symbol_weight)
    if side_weights.sum() > 0:
        # Renormalize only if the cap did not make the requested gross impossible.
        max_possible = params.max_symbol_weight * len(side_weights)
        target_gross = min(params.long_gross, max_possible)
        side_weights = side_weights / side_weights.sum() * target_gross
    weights.loc[list(side_weights.index)] = side_weights
    buckets.loc[list(side_weights.index)] = "long"
    return weights, ranks, buckets


def _volatility(formation: pd.DataFrame, params: ETFTacticalParams) -> pd.Series:
    close = formation.xs("close", axis=1, level=1).astype(float)
    returns = close.pct_change(fill_method=None)
    return returns.tail(params.vol_lookback_days).std(ddof=0)
