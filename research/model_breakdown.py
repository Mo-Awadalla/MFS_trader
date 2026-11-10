"""Utilities for comparing regular-state and breakdown-state forecasts."""

from __future__ import annotations

import numpy as np


def regression_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    """Return level-space error metrics and signed underprediction."""
    error = np.asarray(actual, dtype=float) - np.asarray(predicted, dtype=float)
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "mean_underprediction": float(np.mean(error)),
        "tail_mae_top_actual_decile": float(np.mean(np.abs(error)[actual >= np.quantile(actual, 0.9)])),
    }


def block_bootstrap_mean(values: list[float], seed: int = 20260913) -> dict[str, object]:
    """Bootstrap a mean over already-computed dependence blocks."""
    array = np.asarray(values, dtype=float)
    if not len(array):
        return {"mean": None, "block_bootstrap_95pct_ci": [None, None], "eligible_blocks": 0}
    rng = np.random.default_rng(seed)
    boot = np.asarray([rng.choice(array, len(array), replace=True).mean() for _ in range(1000)])
    return {
        "mean": float(array.mean()),
        "block_bootstrap_95pct_ci": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))],
        "eligible_blocks": len(array),
    }
