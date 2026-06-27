"""Integration tests for Pairs v1 registry, artifacts, and validation pipeline."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from experiments.artifacts import ArtifactKind, ArtifactManager
from experiments.models import PromotionStatus
from experiments.registry import ExperimentRegistry
from research.pairs_pipeline import backtest_pairs, run_pairs_validation_gauntlet
from strategies.pairs.signal import PairsParams


def pairs_panel(n_days: int = 620, n_symbols: int = 6) -> pd.DataFrame:
    idx = pd.bdate_range("2020-01-02", periods=n_days, tz="UTC")
    symbols = tuple(f"S{i:03d}" for i in range(n_symbols))
    columns = pd.MultiIndex.from_product(
        [symbols, ("open", "high", "low", "close", "volume")],
        names=["symbol", "field"],
    )
    df = pd.DataFrame(index=idx, columns=columns, dtype=float)

    rng = np.random.default_rng(11)
    log_base = np.log(50.0) + np.cumsum(rng.normal(0.0, 0.01, n_days))
    stationary = rng.normal(0.0, 0.002, n_days)
    for pos in range(100, n_days, 90):
        stationary[pos] += 0.004

    for i, symbol in enumerate(symbols):
        if symbol == "S000":
            close = np.exp(log_base)
        elif symbol == "S001":
            close = np.exp(log_base + 0.04 + stationary)
        else:
            independent = np.log(30.0 + i) + np.cumsum(rng.normal(0.0, 0.02 + i * 0.003, n_days))
            close = np.exp(independent)
        df[(symbol, "open")] = close
        df[(symbol, "high")] = close * 1.01
        df[(symbol, "low")] = close * 0.99
        df[(symbol, "close")] = close
        df[(symbol, "volume")] = 2_000_000.0 - i * 100_000.0
    return df


def fast_pairs_params() -> PairsParams:
    return PairsParams(
        candidate_pool_size=6,
        formation_window_days=80,
        min_history_days=60,
        min_eligible_universe=4,
        min_median_dollar_volume=1.0,
        max_active_pairs=2,
    )


def test_pairs_backtest_is_deterministic() -> None:
    df = pairs_panel()
    params = fast_pairs_params()

    first = backtest_pairs(df, params)
    second = backtest_pairs(df, params)

    pd.testing.assert_series_equal(first.returns, second.returns)
    pd.testing.assert_frame_equal(first.weights, second.weights)
    assert first.rebalance_count > 0


def test_pairs_validation_registers_experiment_and_writes_artifacts(tmp_path: Path) -> None:
    df = pairs_panel()
    params = fast_pairs_params()
    registry = ExperimentRegistry(tmp_path / "experiments")
    artifacts = ArtifactManager(registry.root)
    try:
        report = run_pairs_validation_gauntlet(
            df,
            params=params,
            registry=registry,
            artifacts=artifacts,
            experiment_label="Pairs-v1-synthetic-validation",
            data_source="synthetic",
            seed=7,
            mc_num_paths=200,
        )

        assert report.experiment_uuid is not None
        experiment = registry.get(report.experiment_uuid)
        assert experiment.snapshot.strategy == "pairs_trading"
        assert experiment.snapshot.parameters["formation_window_days"] == 80
        assert experiment.snapshot.parameters["entry_zscore"] == 2.0
        assert experiment.snapshot.universe.filters["crypto_included"] is False
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
        diagnostics = artifacts.read_json(
            experiment.uuid,
            ArtifactKind.DIAGNOSTICS_SIGNALS_JSON,
        )
        assert validation_report["experiment_uuid"] == experiment.uuid
        assert validation_report["strategy"] == "pairs_trading"
        assert artifacts.exists(experiment.uuid, ArtifactKind.VALIDATION_REPORT_MD)
        assert artifacts.exists(experiment.uuid, ArtifactKind.VALIDATION_VERDICT_TXT)
        assert replay_attribution["mode"] == "vectorized_cross_sectional_replay"
        assert replay_attribution["engine_replay_available"] is False
        assert "single-symbol" in replay_attribution["reason"]
        assert diagnostics["strategy"] == "pairs_trading"
        assert "signal_activity" in diagnostics
    finally:
        registry.close()
