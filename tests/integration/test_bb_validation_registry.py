"""Integration: BB validation pipeline registers experiments when registry provided."""

from __future__ import annotations

import numpy as np
import pandas as pd

from experiments.models import PromotionStatus
from experiments.registry import ExperimentRegistry
from research.bb_pipeline import run_bb_validation_gauntlet
from strategies.bb.signal import BBParams, compact_sweep_grid


def _make_ohlcv(n: int = 400, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="1D", tz="UTC")
    close = 150.0 + 8.0 * np.sin(np.linspace(0, 20, n)) + np.cumsum(rng.normal(0, 0.2, n))
    return pd.DataFrame(
        {
            "open": close - 0.3,
            "high": close + 0.6,
            "low": close - 0.6,
            "close": close,
            "volume": rng.integers(500_000, 2_000_000, n).astype(float),
        },
        index=idx,
    )


class TestBBValidationRegistry:
    def test_validation_registers_experiment(self, tmp_path):
        registry = ExperimentRegistry(tmp_path / "experiments")
        try:
            df = _make_ohlcv()
            grid = compact_sweep_grid()
            report = run_bb_validation_gauntlet(
                df,
                params=BBParams(window=10, std_mult=1.5, width_mode="none", width_lookback=30),
                sweep_grid_override=grid,
                wfa_grid_override=grid,
                registry=registry,
                experiment_label="bb-test-registry",
                data_source="synthetic",
                seed=42,
            )
            assert report.experiment_uuid is not None
            experiment = registry.get(report.experiment_uuid)
            assert experiment.label == "bb-test-registry"
            assert experiment.promotion_status in (
                PromotionStatus.VALIDATION_PASSED,
                PromotionStatus.VALIDATION_FAILED,
            )
            assert experiment.snapshot.strategy_template_version == "bollinger_bands:v2"
        finally:
            registry.close()
