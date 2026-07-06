"""Global Dual Momentum Defensive v1 signal construction.

Frozen hypothesis: hold the strongest risk ETF when its 12-month absolute
momentum is positive; otherwise rotate into the strongest defensive ETF.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from research.universes.global_dual_momentum_v1 import DEFENSIVE_ASSETS, RISK_ASSETS
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


@dataclass(frozen=True)
class GlobalDualMomentumParams:
    """Frozen Global Dual Momentum Defensive v1 parameters."""

    momentum_lookback_days: int = 252
    liquidity_lookback_days: int = 20
    min_history_days: int = 252
    min_price: float = 5.0
    min_median_dollar_volume: float = 5_000_000.0
    top_risk_n: int = 1
    defensive_n: int = 1
    target_gross: float = 1.0


def generate_signals(df: pd.DataFrame, params: GlobalDualMomentumParams) -> pd.DataFrame:
    """Generate monthly Global Dual Momentum target weights."""

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

        score = _momentum_score(formation, params)
        tradable = eligible_symbols(
            formation,
            min_history_days=params.min_history_days,
            min_price=params.min_price,
            liquidity_lookback_days=params.liquidity_lookback_days,
            min_median_dollar_volume=params.min_median_dollar_volume,
            signal=score,
        )
        eligible_score = score[tradable]
        result.loc[ts, ("portfolio", "eligible_count")] = int(len(eligible_score))
        if eligible_score.empty:
            write_skip(result, ts, current_weights, "insufficient_eligible_universe", 0)
            continue

        selected, bucket_label = _select_symbols(eligible_score, params)
        next_weights, ranks, buckets = _target_weights(selected, score, symbols, params, bucket_label)
        trades = next_weights - current_weights
        write_weights(result, ts, next_weights, trades)
        write_signal_details(result, ts, symbols, score, eligible_score, ranks, buckets)
        current_weights = next_weights

    return result


def validate_inputs(df: pd.DataFrame) -> None:
    validate_panel_inputs(df, "GlobalDualMomentum")
    symbols = set(panel_symbols(df))
    missing = (set(RISK_ASSETS) | set(DEFENSIVE_ASSETS)) - symbols
    if missing:
        raise ValueError(f"GlobalDualMomentum missing required symbols: {sorted(missing)}")


def default_params() -> GlobalDualMomentumParams:
    return GlobalDualMomentumParams()


def sweep_grid() -> list[GlobalDualMomentumParams]:
    """Predeclared stability grid; canonical selection is not changed after results."""

    return [
        default_params(),
        GlobalDualMomentumParams(momentum_lookback_days=189),
        GlobalDualMomentumParams(momentum_lookback_days=252, top_risk_n=2),
        GlobalDualMomentumParams(momentum_lookback_days=189, top_risk_n=2),
    ]


def compact_sweep_grid() -> list[GlobalDualMomentumParams]:
    return [default_params()]


def params_to_dict(params: GlobalDualMomentumParams) -> dict[str, int | float]:
    return {
        "momentum_lookback_days": params.momentum_lookback_days,
        "liquidity_lookback_days": params.liquidity_lookback_days,
        "min_history_days": params.min_history_days,
        "min_price": params.min_price,
        "min_median_dollar_volume": params.min_median_dollar_volume,
        "top_risk_n": params.top_risk_n,
        "defensive_n": params.defensive_n,
        "target_gross": params.target_gross,
    }


def params_from_dict(data: dict[str, Any]) -> GlobalDualMomentumParams:
    return GlobalDualMomentumParams(
        momentum_lookback_days=int(data.get("momentum_lookback_days", 252)),
        liquidity_lookback_days=int(data.get("liquidity_lookback_days", 20)),
        min_history_days=int(data.get("min_history_days", 252)),
        min_price=float(data.get("min_price", 5.0)),
        min_median_dollar_volume=float(data.get("min_median_dollar_volume", 5_000_000.0)),
        top_risk_n=int(data.get("top_risk_n", 1)),
        defensive_n=int(data.get("defensive_n", 1)),
        target_gross=float(data.get("target_gross", 1.0)),
    )


def _minimum_lookback(params: GlobalDualMomentumParams) -> int:
    return max(params.min_history_days, params.momentum_lookback_days + 1)


def _momentum_score(formation: pd.DataFrame, params: GlobalDualMomentumParams) -> pd.Series:
    close = formation.xs("close", axis=1, level=1).astype(float)
    end = close.iloc[-1]
    start = close.iloc[-(params.momentum_lookback_days + 1)]
    return end / start - 1.0


def _select_symbols(
    eligible_score: pd.Series,
    params: GlobalDualMomentumParams,
) -> tuple[tuple[str, ...], str]:
    risk_scores = eligible_score[eligible_score.index.isin(RISK_ASSETS)].sort_values(
        ascending=False,
        kind="mergesort",
    )
    positive_risk = risk_scores[risk_scores > 0.0]
    if not positive_risk.empty:
        return tuple(str(symbol) for symbol in positive_risk.head(params.top_risk_n).index), "risk_on"

    defensive_scores = eligible_score[eligible_score.index.isin(DEFENSIVE_ASSETS)].sort_values(
        ascending=False,
        kind="mergesort",
    )
    if not defensive_scores.empty:
        return tuple(str(symbol) for symbol in defensive_scores.head(params.defensive_n).index), "defensive"
    return (), "cash"


def _target_weights(
    selected: tuple[str, ...],
    score: pd.Series,
    symbols: tuple[str, ...],
    params: GlobalDualMomentumParams,
    bucket_label: str,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    weights = pd.Series(0.0, index=symbols, dtype=float)
    ranks = pd.Series(pd.NA, index=symbols, dtype="Float64")
    buckets = pd.Series("", index=symbols, dtype=object)
    ranked = score.sort_values(ascending=False, kind="mergesort")
    for rank, symbol in enumerate(ranked.index, start=1):
        ranks.loc[str(symbol)] = rank
    if selected:
        weights.loc[list(selected)] = params.target_gross / len(selected)
        buckets.loc[list(selected)] = bucket_label
    return weights, ranks, buckets
