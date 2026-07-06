"""Integration tests for ETF tactical validation plumbing."""

from __future__ import annotations

import numpy as np
import pandas as pd

from experiments.models import PromotionStatus
from experiments.registry import ExperimentRegistry
from research.etf_tactical_pipeline import run_etf_tactical_validation_gauntlet
from strategies.etf_tactical.signal import ETFTacticalParams
from strategies.registry import get_strategy, strategy_template_version

SYMBOLS = ("SPY", "QQQ", "IWM", "IEF", "GLD", "SHY", "DBC")


def _make_panel(n: int = 460) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC")
    frames: dict[str, pd.DataFrame] = {}
    for i, symbol in enumerate(SYMBOLS):
        returns = np.full(n, 0.00015 + i * 0.00002)
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


def test_etf_tactical_strategy_is_registered():
    strategy = get_strategy("etf_tactical_momentum")

    assert strategy.name == "etf_tactical_momentum"
    assert strategy_template_version("etf_tactical_momentum") == "etf_tactical_momentum:v1"
    assert strategy.supports_short() is False


def test_etf_tactical_validation_registers_experiment(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    params = ETFTacticalParams(
        short_lookback_days=63,
        long_lookback_days=126,
        trend_ma_days=100,
        vol_lookback_days=42,
        min_history_days=126,
        min_median_dollar_volume=1.0,
        min_eligible_symbols=4,
    )
    try:
        report = run_etf_tactical_validation_gauntlet(
            _make_panel(),
            params=params,
            registry=registry,
            experiment_label="etf-tactical-test",
            data_source="synthetic",
            seed=42,
            mc_num_paths=200,
        )
        assert report.experiment_uuid is not None
        experiment = registry.get(report.experiment_uuid)
        assert experiment.label == "etf-tactical-test"
        assert experiment.snapshot.strategy_template_version == "etf_tactical_momentum:v1"
        assert experiment.promotion_status in {
            PromotionStatus.VALIDATION_FAILED,
            PromotionStatus.VALIDATION_PASSED,
        }
    finally:
        registry.close()
