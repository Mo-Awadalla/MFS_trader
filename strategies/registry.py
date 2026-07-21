"""Registered strategy templates."""

from __future__ import annotations

from typing import Any

from strategies.bb.strategy import get_strategy as get_bb_strategy
from strategies.contract import StrategyTemplate
from strategies.csmr.strategy import get_strategy as get_csmr_strategy
from strategies.etf_time_series_momentum.strategy import get_strategy as get_etf_tsm_strategy
from strategies.ftre.strategy import get_strategy as get_ftre_strategy
from strategies.fundamental_event_smart_reversal.strategy import (
    get_strategy as get_fundamental_event_smart_reversal_strategy,
)
from strategies.global_dual_momentum.strategy import (
    get_strategy as get_global_dual_momentum_strategy,
)
from strategies.ma.strategy import get_strategy as get_ma_strategy
from strategies.market_intraday_momentum.strategy import (
    get_strategy as get_market_intraday_momentum_strategy,
)
from strategies.momentum.strategy import get_strategy as get_momentum_strategy
from strategies.opening_range_breakout.strategy import (
    get_strategy as get_opening_range_breakout_strategy,
)
from strategies.pairs.strategy import get_strategy as get_pairs_strategy
from strategies.residual_reversal.strategy import get_strategy as get_residual_reversal_strategy

_REGISTRY: dict[str, StrategyTemplate[Any]] = {
    "bollinger_bands": get_bb_strategy(),
    "cross_sectional_mean_reversion": get_csmr_strategy(),
    "cross_sectional_momentum": get_momentum_strategy(),
    "dual_ma_crossover": get_ma_strategy(),
    "etf_time_series_momentum": get_etf_tsm_strategy(),
    "fundamental_event_smart_reversal": get_fundamental_event_smart_reversal_strategy(),
    "global_dual_momentum": get_global_dual_momentum_strategy(),
    "market_intraday_momentum": get_market_intraday_momentum_strategy(),
    "opening_range_breakout": get_opening_range_breakout_strategy(),
    "pairs_trading": get_pairs_strategy(),
    "residual_reversal_stat_arb": get_residual_reversal_strategy(),
}

# Binance-only (USDⓈ-M perpetual funding); shelved after the Coinbase migration.
_SHELVED: dict[str, StrategyTemplate[Any]] = {
    "funding_time_reversal": get_ftre_strategy(),
}

# Raw exit column used by exit-contract tests per strategy.
RAW_EXIT_COLUMNS: dict[str, str] = {
    "bollinger_bands": "cross_above_middle",
    "dual_ma_crossover": "cross_below",
    "funding_time_reversal": "raw_exit",
}


def get_strategy(name: str) -> StrategyTemplate[Any]:
    strategy = _REGISTRY.get(name) or _SHELVED.get(name)
    if strategy is None:
        raise KeyError(f"Unknown strategy template: {name}")
    return strategy


def registered_strategies() -> dict[str, StrategyTemplate[Any]]:
    return dict(_REGISTRY)


def strategy_template_version(name: str) -> str:
    return get_strategy(name).strategy_template_version
