"""Registered strategy templates."""

from __future__ import annotations

from typing import Any

from strategies.bb.strategy import get_strategy as get_bb_strategy
from strategies.contract import StrategyTemplate
from strategies.csmr.strategy import get_strategy as get_csmr_strategy
from strategies.etf_time_series_momentum.strategy import get_strategy as get_etf_tsm_strategy
from strategies.ma.strategy import get_strategy as get_ma_strategy
from strategies.market_intraday_momentum.strategy import (
    get_strategy as get_market_intraday_momentum_strategy,
)
from strategies.momentum.strategy import get_strategy as get_momentum_strategy
from strategies.pairs.strategy import get_strategy as get_pairs_strategy
from strategies.residual_reversal.strategy import get_strategy as get_residual_reversal_strategy

_REGISTRY: dict[str, StrategyTemplate[Any]] = {
    "bollinger_bands": get_bb_strategy(),
    "cross_sectional_mean_reversion": get_csmr_strategy(),
    "cross_sectional_momentum": get_momentum_strategy(),
    "dual_ma_crossover": get_ma_strategy(),
    "etf_time_series_momentum": get_etf_tsm_strategy(),
    "market_intraday_momentum": get_market_intraday_momentum_strategy(),
    "pairs_trading": get_pairs_strategy(),
    "residual_reversal_stat_arb": get_residual_reversal_strategy(),
}

# Raw exit column used by exit-contract tests per strategy.
RAW_EXIT_COLUMNS: dict[str, str] = {
    "bollinger_bands": "cross_above_middle",
    "dual_ma_crossover": "cross_below",
}


def get_strategy(name: str) -> StrategyTemplate[Any]:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown strategy template: {name}")
    return _REGISTRY[name]


def registered_strategies() -> dict[str, StrategyTemplate[Any]]:
    return dict(_REGISTRY)


def strategy_template_version(name: str) -> str:
    return get_strategy(name).strategy_template_version
