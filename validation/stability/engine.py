"""Parameter stability analysis.

Checks that the selected parameters are on a stable plateau, not an isolated peak.

Tests:
  1. No isolated peak — neighbors of the best params perform similarly
  2. Stable plateau — top parameter region within 20-30% of selected
  3. Consistent across WFA windows — parameters work in multiple folds
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)


@dataclass
class StabilityResult:
    """Results of parameter stability analysis."""

    best_params: dict[str, Any]
    best_sharpe: float
    plateau_sharpe_range: tuple[float, float]  # (min, max) of top region
    plateau_size: int  # number of params in the stable region
    plateau_within_pct: float  # how close top region is to best
    has_isolated_peak: bool
    passed: bool = False
    failure_reasons: list[str] = field(default_factory=list)
    param_sensitivity: dict[str, float] = field(default_factory=dict)


def analyze_stability(
    results_df: pd.DataFrame,
    param_columns: list[str],
    *,
    sharpe_column: str = "sharpe",
    plateau_pct: float = 0.20,  # top 20% of results form the plateau
    max_drop_from_best: float = 0.30,  # plateau must be within 30% of best
) -> StabilityResult:
    """Analyze parameter stability from a sweep results DataFrame.

    Args:
        results_df: DataFrame with parameter columns and a Sharpe column.
        param_columns: Columns representing the swept parameters.
        sharpe_column: Column name for the Sharpe ratio.
        plateau_pct: Fraction of top results defining the plateau.
        max_drop_from_best: Max allowed drop from best Sharpe in the plateau.

    Returns:
        StabilityResult with pass/fail and diagnostics.
    """
    if results_df.empty or sharpe_column not in results_df.columns:
        return StabilityResult(
            best_params={},
            best_sharpe=0.0,
            plateau_sharpe_range=(0, 0),
            plateau_size=0,
            plateau_within_pct=0.0,
            has_isolated_peak=True,
            failure_reasons=["empty_results"],
        )

    df = results_df.copy()
    df = df.sort_values(sharpe_column, ascending=False).reset_index(drop=True)

    best_idx = 0
    best_sharpe = float(df.loc[best_idx, sharpe_column])
    best_params = {col: df.loc[best_idx, col] for col in param_columns}

    # Define plateau: top plateau_pct of results
    plateau_size = max(int(len(df) * plateau_pct), 1)
    plateau = df.head(plateau_size)
    plateau_sharpes = plateau[sharpe_column].values
    plateau_min = float(plateau_sharpes.min())
    plateau_max = float(plateau_sharpes.max())

    # Check: plateau within max_drop_from_best of best
    drop_from_best = (best_sharpe - plateau_min) / best_sharpe if best_sharpe > 0 else 0.0
    plateau_within_pct = float(1.0 - drop_from_best)

    # Check for isolated peak: is the best point surrounded by similar values?
    has_isolated_peak = _check_isolated_peak(df, param_columns, sharpe_column, best_idx)

    # Parameter sensitivity: how much does Sharpe change when each param changes?
    sensitivity = _compute_sensitivity(df, param_columns, sharpe_column)

    # Evaluate pass/fail
    failures: list[str] = []

    if has_isolated_peak:
        failures.append("isolated_peak_detected — best params not on a stable plateau")

    if plateau_within_pct < (1.0 - max_drop_from_best):
        failures.append(
            f"plateau_within_pct {plateau_within_pct:.2f} < required {1.0 - max_drop_from_best:.2f}"
        )

    if plateau_max > 0 and plateau_min < 0:
        failures.append("plateau contains negative Sharpe values — unstable region")

    passed = len(failures) == 0

    return StabilityResult(
        best_params=best_params,
        best_sharpe=best_sharpe,
        plateau_sharpe_range=(plateau_min, plateau_max),
        plateau_size=plateau_size,
        plateau_within_pct=plateau_within_pct,
        has_isolated_peak=has_isolated_peak,
        passed=passed,
        failure_reasons=failures,
        param_sensitivity=sensitivity,
    )


def _check_isolated_peak(
    df: pd.DataFrame,
    param_columns: list[str],
    sharpe_column: str,
    best_idx: int,
) -> bool:
    """Check if the best result is an isolated peak (neighbors are much worse).

    An isolated peak is one where changing any single parameter by one step
    causes a dramatic drop in Sharpe.
    """
    best = df.loc[best_idx]
    best_sharpe = best[sharpe_column]
    if best_sharpe <= 0:
        return False  # Can't be an isolated peak if not positive

    # For each parameter, find neighbors (values within 1 step)
    neighbor_sharpes: list[float] = []

    for col in param_columns:
        best_val = best[col]
        # Find rows where this param is "close" to best
        if pd.api.types.is_numeric_dtype(df[col]):
            # Numeric: within 10% or next value
            step = _estimate_step_size(df, col)
            neighbors = df[(df[col] - best_val).abs() <= step * 1.5]
            neighbors = neighbors[neighbors.index != best_idx]
        else:
            # Categorical: same value but other params differ slightly
            neighbors = df[df[col] == best_val]
            neighbors = neighbors[neighbors.index != best_idx]

        if not neighbors.empty:
            neighbor_sharpes.extend(neighbors[sharpe_column].tolist())

    if not neighbor_sharpes:
        return True  # No neighbors at all — isolated

    # If neighbors are much worse, it's an isolated peak
    avg_neighbor = float(np.mean(neighbor_sharpes))
    if best_sharpe > 0 and avg_neighbor > 0:
        ratio = best_sharpe / avg_neighbor
        return bool(ratio > 3.0)  # best is 3x better than average neighbor
    elif avg_neighbor <= 0 and best_sharpe > 0:
        return True  # neighbors are negative, best is positive — isolated

    return False


def _estimate_step_size(df: pd.DataFrame, col: str) -> float:
    """Estimate the step size for a numeric parameter column."""
    vals = df[col].dropna().sort_values().unique()
    if len(vals) < 2:
        return 1.0
    diffs = np.diff(vals)
    return float(np.median(diffs)) if len(diffs) > 0 else 1.0


def _compute_sensitivity(
    df: pd.DataFrame, param_columns: list[str], sharpe_column: str
) -> dict[str, float]:
    """Compute how sensitive Sharpe is to each parameter.

    Returns a dict {param: sensitivity_score} where higher = more sensitive.
    """
    sensitivity: dict[str, float] = {}

    for col in param_columns:
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        # Group by param value, compute Sharpe variance
        grouped = df.groupby(col)[sharpe_column]
        if len(grouped) > 1:
            # Sensitivity = range of mean Sharpe across param values
            means = grouped.mean()
            sensitivity[col] = float(means.max() - means.min())
        else:
            sensitivity[col] = 0.0

    return sensitivity


def check_wfa_consistency(
    wfa_folds: list[dict[str, Any]],
    param_columns: list[str],
    *,
    consistency_threshold: float = 0.70,
) -> dict[str, Any]:
    """Check if the same parameter region performs well across WFA folds.

    Args:
        wfa_folds: List of fold results, each with 'fitted_params' and 'sharpe'.
        param_columns: Parameters to check for consistency.
        consistency_threshold: Fraction of folds that must agree.

    Returns:
        Dict with consistency analysis.
    """
    if not wfa_folds:
        return {"consistent": False, "reason": "no_folds"}

    # For each fold, identify the top parameter region
    top_params_per_fold: list[dict[str, Any]] = []
    for fold in wfa_folds:
        params = fold.get("fitted_params", {})
        if params:
            top_params_per_fold.append({k: params.get(k) for k in param_columns})

    if not top_params_per_fold:
        return {"consistent": False, "reason": "no_params_in_folds"}

    # Check how often the same param values appear in top folds
    consistency_scores: dict[str, float] = {}
    for col in param_columns:
        values = [p.get(col) for p in top_params_per_fold if p.get(col) is not None]
        if values:
            # Most common value's frequency
            from collections import Counter

            counts = Counter(values)
            most_common_freq = counts.most_common(1)[0][1] / len(values)
            consistency_scores[col] = most_common_freq

    avg_consistency = float(np.mean(list(consistency_scores.values()))) if consistency_scores else 0.0
    consistent = avg_consistency >= consistency_threshold

    return {
        "consistent": consistent,
        "avg_consistency": avg_consistency,
        "per_param": consistency_scores,
        "reason": "" if consistent else "params_inconsistent_across_folds",
    }
