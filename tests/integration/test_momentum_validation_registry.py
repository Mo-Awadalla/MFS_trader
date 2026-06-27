"""Integration tests for Momentum registry, artifacts, and validation pipeline."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from experiments.artifacts import ArtifactKind, ArtifactManager
from experiments.models import PromotionStatus
from experiments.registry import ExperimentRegistry
from research.momentum_pipeline import backtest_momentum, run_momentum_validation_gauntlet
from strategies.momentum.signal import MomentumParams


def momentum_panel(n_days: int = 620, n_symbols: int = 120) -> pd.DataFrame:
    idx = pd.bdate_range("2020-01-02", periods=n_days, tz="UTC")
    symbols = tuple(f"S{i:03d}" for i in range(n_symbols))
    columns = pd.MultiIndex.from_product(
        [symbols, ("open", "high", "low", "close", "volume")],
        names=["symbol", "field"],
    )
    df = pd.DataFrame(index=idx, columns=columns, dtype=float)
    for i, symbol in enumerate(symbols):
        base = 30.0 + i
        drift = (i - n_symbols / 2) / n_symbols * 0.0003
        noise = np.sin(np.arange(n_days) / 11.0 + i) * 0.001
        close = base * (1.0 + np.cumsum(drift + noise))
        df[(symbol, "open")] = close
        df[(symbol, "high")] = close * 1.01
        df[(symbol, "low")] = close * 0.99
        df[(symbol, "close")] = close
        df[(symbol, "volume")] = 2_000_000.0
    return df


def test_momentum_backtest_is_deterministic() -> None:
    df = momentum_panel()
    params = MomentumParams()

    first = backtest_momentum(df, params)
    second = backtest_momentum(df, params)

    pd.testing.assert_series_equal(first.returns, second.returns)
    pd.testing.assert_frame_equal(first.weights, second.weights)
    assert first.rebalance_count > 0


def test_momentum_validation_registers_experiment_and_writes_artifacts(tmp_path: Path) -> None:
    df = momentum_panel()
    registry = ExperimentRegistry(tmp_path / "experiments")
    artifacts = ArtifactManager(registry.root)
    try:
        report = run_momentum_validation_gauntlet(
            df,
            registry=registry,
            artifacts=artifacts,
            experiment_label="Momentum-v1-synthetic-validation",
            data_source="synthetic",
            seed=7,
            mc_num_paths=200,
        )

        assert report.experiment_uuid is not None
        experiment = registry.get(report.experiment_uuid)
        assert experiment.snapshot.strategy == "cross_sectional_momentum"
        assert experiment.snapshot.parameters["formation_lookback_days"] == 252
        assert experiment.snapshot.parameters["skip_recent_days"] == 21
        assert experiment.promotion_status in {
            PromotionStatus.VALIDATION_FAILED,
            PromotionStatus.VALIDATION_PASSED,
        }

        validation_report = artifacts.read_json(
            experiment.uuid,
            ArtifactKind.VALIDATION_REPORT_JSON,
        )
        replay_attribution = artifacts.read_json(
            experiment.uuid,
            ArtifactKind.REPLAY_ATTRIBUTION_JSON,
        )
        assert validation_report["experiment_uuid"] == experiment.uuid
        assert validation_report["strategy"] == "cross_sectional_momentum"
        assert artifacts.exists(experiment.uuid, ArtifactKind.VALIDATION_REPORT_MD)
        assert artifacts.exists(experiment.uuid, ArtifactKind.VALIDATION_VERDICT_TXT)
        assert replay_attribution["mode"] == "vectorized_cross_sectional_replay"
    finally:
        registry.close()
