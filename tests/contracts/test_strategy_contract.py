"""Parametrized strategy contract suite — all registered strategies inherit these tests."""

from __future__ import annotations

import pytest

from strategies.registry import registered_strategies
from tests.contracts.helpers import run_contract_suite


@pytest.mark.parametrize("strategy_name", list(registered_strategies().keys()))
def test_strategy_contract_suite(strategy_name: str) -> None:
    run_contract_suite(registered_strategies()[strategy_name])


def test_bb_is_reference_implementation() -> None:
    from strategies.bb.strategy import TEMPLATE_VERSION, BollingerBandsStrategy
    from strategies.registry import get_strategy, strategy_template_version

    strategy = get_strategy("bollinger_bands")
    assert isinstance(strategy, BollingerBandsStrategy)
    assert strategy.metadata()["reference_implementation"] is True
    assert strategy_template_version("bollinger_bands") == f"bollinger_bands:{TEMPLATE_VERSION}"


def test_csmr_is_registered_canonical_v1() -> None:
    from strategies.csmr.strategy import TEMPLATE_VERSION, CrossSectionalMeanReversionStrategy
    from strategies.registry import get_strategy, strategy_template_version

    strategy = get_strategy("cross_sectional_mean_reversion")
    assert isinstance(strategy, CrossSectionalMeanReversionStrategy)
    assert strategy.metadata()["hypothesis"] == "recent_losers_outperform_recent_winners"
    assert strategy.metadata()["dollar_neutral"] is True
    assert strategy.metadata()["long_only"] is False
    assert (
        strategy_template_version("cross_sectional_mean_reversion")
        == f"cross_sectional_mean_reversion:{TEMPLATE_VERSION}"
    )


def test_momentum_is_registered_canonical_v1() -> None:
    from strategies.momentum.strategy import TEMPLATE_VERSION, CrossSectionalMomentumStrategy
    from strategies.registry import get_strategy, strategy_template_version

    strategy = get_strategy("cross_sectional_momentum")
    assert isinstance(strategy, CrossSectionalMomentumStrategy)
    assert strategy.metadata()["hypothesis"] == "recent_winners_outperform_recent_losers"
    assert strategy.metadata()["formation"] == "12-1"
    assert strategy.metadata()["dollar_neutral"] is True
    assert strategy.metadata()["long_only"] is False
    assert (
        strategy_template_version("cross_sectional_momentum")
        == f"cross_sectional_momentum:{TEMPLATE_VERSION}"
    )


def test_pairs_is_registered_canonical_v1() -> None:
    from strategies.pairs.strategy import TEMPLATE_VERSION, PairsTradingStrategy
    from strategies.registry import get_strategy, strategy_template_version

    strategy = get_strategy("pairs_trading")
    assert isinstance(strategy, PairsTradingStrategy)
    assert strategy.metadata()["hypothesis"] == "cointegrated_spreads_mean_revert"
    assert strategy.metadata()["asset_class"] == "us_equities"
    assert strategy.metadata()["crypto_included"] is False
    assert strategy.metadata()["pair_test"] == "engle_granger"
    assert strategy.metadata()["formation_window_days"] == 252
    assert strategy.metadata()["min_eligible_universe"] == 100
    assert strategy.metadata()["entry_zscore"] == 2.0
    assert strategy.metadata()["exit_zscore"] == 0.5
    assert strategy.metadata()["stop_zscore"] == 4.0
    assert strategy.metadata()["dollar_neutral"] is True
    assert strategy.metadata()["long_only"] is False
    assert strategy.metadata()["tuning"] == "none"
    assert strategy_template_version("pairs_trading") == f"pairs_trading:{TEMPLATE_VERSION}"
