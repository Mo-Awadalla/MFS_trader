"""Integration tests for Global Dual Momentum validation plumbing."""

from __future__ import annotations

import numpy as np
import pandas as pd

from experiments.models import PromotionStatus
from experiments.registry import ExperimentRegistry
from research.global_dual_momentum_pipeline import run_global_dual_momentum_validation_gauntlet
from research.universes.global_dual_momentum_v1 import all_symbols
from strategies.global_dual_momentum.signal import GlobalDualMomentumParams
from strategies.registry import get_strategy, strategy_template_version

SYMBOLS = all_symbols()


def _make_panel(n: int = 520) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC")
    frames: dict[str, pd.DataFrame] = {}
    for i, symbol in enumerate(SYMBOLS):
        returns = np.full(n, 0.00010 + i * 0.00002)
        close = 100.0 * np.cumprod(1.0 + returns)
        frames[symbol] = pd.DataFrame(
            {
                "open": close * 0.999,
                "high": close * 1.003,
                "low": close * 0.997,
                "close": close,
                "volume": np.full(n, 1_500_000.0),
            },
            index=index,
        )
    panel = pd.concat(frames, axis=1)
    panel.columns = pd.MultiIndex.from_tuples(
        [(str(symbol), str(field)) for symbol, field in panel.columns],
        names=["symbol", "field"],
    )
    return panel


def test_global_dual_momentum_strategy_is_registered():
    strategy = get_strategy("global_dual_momentum")

    assert strategy.name == "global_dual_momentum"
    assert strategy_template_version("global_dual_momentum") == "global_dual_momentum:v1"
    assert strategy.supports_short() is False


def test_global_dual_momentum_validation_registers_experiment(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    params = GlobalDualMomentumParams(
        momentum_lookback_days=126,
        min_history_days=126,
        min_median_dollar_volume=1.0,
    )
    try:
        report = run_global_dual_momentum_validation_gauntlet(
            _make_panel(),
            params=params,
            registry=registry,
            experiment_label="global-dual-momentum-test",
            data_source="synthetic",
            seed=42,
            mc_num_paths=200,
        )
        assert report.experiment_uuid is not None
        experiment = registry.get(report.experiment_uuid)
        assert experiment.label == "global-dual-momentum-test"
        assert experiment.snapshot.strategy_template_version == "global_dual_momentum:v1"
        assert experiment.promotion_status in {
            PromotionStatus.VALIDATION_FAILED,
            PromotionStatus.VALIDATION_PASSED,
        }
    finally:
        registry.close()
