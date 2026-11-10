from __future__ import annotations

import numpy as np

from research.model_breakdown import block_bootstrap_mean, regression_metrics


def test_regression_metrics_measure_underprediction() -> None:
    result = regression_metrics(np.array([1.0, 2.0, 3.0]), np.array([0.0, 1.0, 2.0]))
    assert result["mae"] == 1.0
    assert result["mean_underprediction"] == 1.0


def test_block_bootstrap_is_deterministic_and_positive() -> None:
    first = block_bootstrap_mean([1.0, 2.0, 3.0])
    second = block_bootstrap_mean([1.0, 2.0, 3.0])
    assert first == second
    assert first["block_bootstrap_95pct_ci"][0] > 0
